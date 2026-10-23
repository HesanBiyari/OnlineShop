"""Custom staff panel with explicit forms and least-privilege checks."""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import (
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
)
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from store.forms import (
    CategoryStaffForm,
    CodeStaffForm,
    CouponStaffForm,
    DiscountStaffForm,
    GroupStaffForm,
    ImageStaffForm,
    NotificationStaffForm,
    OrderStaffForm,
    ProductStaffForm,
    ReviewStaffForm,
    UserStaffForm,
    VariantStaffForm,
)
from store.models import (
    AuditLog,
    Category,
    Coupon,
    CouponRedemption,
    DigitalCode,
    Discount,
    LoyaltyAccount,
    LoyaltyTransaction,
    Notification,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductImage,
    ProductVariant,
    RecentlyViewed,
    Referral,
    Review,
    Wishlist,
)
from store.services.audit import client_ip, log_action
from store.services.images import save_product_images, validate_image_upload
from store.services.reporting import local_day_bounds

User = get_user_model()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StaffResource:
    key: str
    model: type
    label: str
    icon: str
    form: type | None
    list_fields: tuple[str, ...]
    search_fields: tuple[str, ...] = ()
    can_create: bool = True
    can_edit: bool = True
    can_delete: bool = True
    superuser_only: bool = False
    sensitive: bool = False


RESOURCES: dict[str, StaffResource] = {
    "products": StaffResource(
        "products", Product, "محصولات", "🛍️", ProductStaffForm,
        ("name", "category", "price", "stock", "is_bestseller"),
        ("name", "description", "category__name"),
    ),
    "categories": StaffResource(
        "categories", Category, "دسته‌بندی‌ها", "🗂️", CategoryStaffForm,
        ("name", "slug"), ("name", "slug"),
    ),
    "variants": StaffResource(
        "variants", ProductVariant, "تنوع‌ها", "🎛️", VariantStaffForm,
        ("product", "name", "price", "stock", "sku", "is_active"),
        ("name", "sku", "product__name"),
    ),
    "images": StaffResource(
        "images", ProductImage, "تصاویر", "🖼️", ImageStaffForm,
        ("product", "alt_text", "is_main"), ("product__name", "alt_text"),
    ),
    "discounts": StaffResource(
        "discounts", Discount, "تخفیف‌ها", "🏷️", DiscountStaffForm,
        ("product", "percent", "is_active", "starts_at", "ends_at"),
        ("product__name",),
    ),
    "codes": StaffResource(
        "codes", DigitalCode, "کدهای دیجیتال", "🔐", CodeStaffForm,
        ("code", "product", "variant", "is_used", "order_item"),
        ("code", "product__name", "variant__name"),
        sensitive=True,
    ),
    "orders": StaffResource(
        "orders", Order, "سفارش‌ها", "📦", OrderStaffForm,
        ("id", "user", "status", "total_amount", "created_at"),
        ("user__username", "phone", "email", "payment_ref"),
        can_create=False, can_delete=False, sensitive=True,
    ),
    "order-items": StaffResource(
        "order-items", OrderItem, "آیتم‌های سفارش", "🧾", None,
        ("order", "product_name", "quantity", "total_price"),
        ("product_name", "order__id"),
        can_create=False, can_edit=False, can_delete=False,
    ),
    "payments": StaffResource(
        "payments", Payment, "پرداخت‌ها", "💳", None,
        ("order", "gateway", "amount", "status", "reference_id", "created_at"),
        ("authority", "reference_id", "order__id", "order__phone"),
        can_create=False, can_edit=False, can_delete=False, sensitive=True,
    ),
    "coupons": StaffResource(
        "coupons", Coupon, "کوپن‌ها", "🎟️", CouponStaffForm,
        ("code", "kind", "value", "used_count", "is_active"),
        ("code",), sensitive=True,
    ),
    "coupon-redemptions": StaffResource(
        "coupon-redemptions", CouponRedemption, "مصرف کوپن", "🧮", None,
        ("coupon", "order", "user", "amount", "created_at"),
        ("coupon__code", "user__username"),
        can_create=False, can_edit=False, can_delete=False,
    ),
    "reviews": StaffResource(
        "reviews", Review, "نظرات", "⭐", ReviewStaffForm,
        ("product", "user", "rating", "is_approved", "created_at"),
        ("product__name", "user__username", "title", "body"),
    ),
    "referrals": StaffResource(
        "referrals", Referral, "معرفی‌ها", "🔗", None,
        ("user", "code", "referred_by", "created_at"),
        ("code", "user__username"),
        can_create=False, can_edit=False, can_delete=False,
    ),
    "loyalty": StaffResource(
        "loyalty", LoyaltyAccount, "وفاداری", "💎", None,
        ("user", "points", "lifetime_points", "updated_at"),
        ("user__username",),
        can_create=False, can_edit=False, can_delete=False,
    ),
    "loyalty-transactions": StaffResource(
        "loyalty-transactions", LoyaltyTransaction, "تراکنش امتیاز", "📈", None,
        ("account", "points", "reason", "order", "created_at"),
        ("reason", "account__user__username"),
        can_create=False, can_edit=False, can_delete=False,
    ),
    "notifications": StaffResource(
        "notifications", Notification, "اعلان‌ها", "🔔", NotificationStaffForm,
        ("user", "title", "is_read", "created_at"),
        ("title", "body", "user__username"),
    ),
    "recently-viewed": StaffResource(
        "recently-viewed", RecentlyViewed, "بازدیدهای اخیر", "👁️", None,
        ("user", "session_key", "product", "viewed_at"),
        ("product__name", "session_key"),
        can_create=False, can_edit=False, can_delete=False,
    ),
    "wishlist": StaffResource(
        "wishlist", Wishlist, "علاقه‌مندی‌ها", "❤️", None,
        ("user", "product", "created_at"), ("user__username", "product__name"),
        can_create=False, can_edit=False, can_delete=False,
    ),
    "users": StaffResource(
        "users", User, "کاربران", "👥", UserStaffForm,
        ("username", "email", "is_active", "is_staff", "last_login"),
        ("username", "email", "first_name", "last_name"),
        sensitive=True,
    ),
    "groups": StaffResource(
        "groups", Group, "دسترسی‌ها", "🛡️", GroupStaffForm,
        ("name",), ("name",), superuser_only=True, sensitive=True,
    ),
    "audit": StaffResource(
        "audit", AuditLog, "گزارش رویدادها", "📝", None,
        ("actor", "action", "target_type", "target_id", "ip_address", "created_at"),
        ("action", "target_type", "target_id"),
        can_create=False, can_edit=False, can_delete=False, superuser_only=True,
    ),
}

ALL_NAV = [
    ("dashboard", "داشبورد", "📊"),
    ("products", "محصولات", "🛍️"),
    ("categories", "دسته‌بندی‌ها", "🗂️"),
    ("variants", "تنوع‌ها", "🎛️"),
    ("discounts", "تخفیف‌ها", "🏷️"),
    ("codes", "کدهای دیجیتال", "🔐"),
    ("orders", "سفارش‌ها", "📦"),
    ("payments", "پرداخت‌ها", "💳"),
    ("coupons", "کوپن‌ها", "🎟️"),
    ("reviews", "نظرات", "⭐"),
    ("users", "کاربران", "👥"),
    ("groups", "دسترسی‌ها", "🛡️"),
    ("audit", "رویدادها", "📝"),
]


# ---------------------------------------------------------------------------
# Authorization helpers
# ---------------------------------------------------------------------------
def _staff_required(view):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect(f"{reverse('admin:login')}?next={request.path}")
        return view(request, *args, **kwargs)

    return wrapped


def can_view_codes(user) -> bool:
    return bool(
        user.is_superuser or user.has_perm("store.export_digitalcode")
    )


def _can_write_codes(user, action: str) -> bool:
    if user.is_superuser:
        return True
    return user.has_perm(f"store.{action}_digitalcode")


def _nav_for(user):
    allow_codes = can_view_codes(user)
    return [
        (key, label, icon)
        for key, label, icon in ALL_NAV
        if key != "audit" or user.is_superuser
        if key != "groups" or user.is_superuser
        if key != "codes" or allow_codes
    ]


def _guard_resource(request, resource: StaffResource, *, write: bool = False):
    """Return an error response when the actor may not use this resource."""

    if resource.superuser_only and not request.user.is_superuser:
        raise PermissionDenied
    if resource.key == "codes":
        if write:
            url_name = getattr(request.resolver_match, "url_name", "")
            if url_name == "admin_model_create":
                action = "add"
            elif url_name == "admin_model_delete":
                action = "delete"
            else:
                action = "change"
            if action in {"change", "delete"} and not can_view_codes(request.user):
                raise PermissionDenied
            if not _can_write_codes(request.user, action):
                raise PermissionDenied
        elif not can_view_codes(request.user):
            raise PermissionDenied
    return None


def _can_create_resource(resource: StaffResource, user) -> bool:
    if resource.key == "codes":
        return _can_write_codes(user, "add")
    return True


def _can_edit_resource(resource: StaffResource, user) -> bool:
    if resource.key == "codes":
        return can_view_codes(user) and _can_write_codes(user, "change")
    return True


def _can_delete_resource(resource: StaffResource, user) -> bool:
    if resource.key == "codes":
        return can_view_codes(user) and _can_write_codes(user, "delete")
    return True


FIELD_LABELS = {
    "name": "نام",
    "slug": "نشانی",
    "category": "دسته‌بندی",
    "price": "قیمت",
    "stock": "موجودی",
    "is_bestseller": "پرفروش",
    "bestseller_priority": "اولویت",
    "product": "محصول",
    "variant": "تنوع",
    "sku": "کد کالا",
    "is_active": "فعال",
    "percent": "درصد",
    "starts_at": "شروع",
    "ends_at": "پایان",
    "code": "کد",
    "pin": "پین",
    "is_used": "استفاده‌شده",
    "used_at": "زمان استفاده",
    "order_item": "آیتم سفارش",
    "user": "کاربر",
    "status": "وضعیت",
    "total_amount": "مبلغ کل",
    "payment_ref": "شماره پرداخت",
    "created_at": "تاریخ ایجاد",
    "paid_at": "زمان پرداخت",
    "phone": "موبایل",
    "email": "ایمیل",
    "full_name": "نام گیرنده",
    "product_name": "نام محصول",
    "variant_name": "نام تنوع",
    "quantity": "تعداد",
    "unit_price": "قیمت واحد",
    "total_price": "مبلغ کل",
    "order": "سفارش",
    "gateway": "درگاه",
    "amount": "مبلغ",
    "reference_id": "کد مرجع",
    "kind": "نوع",
    "value": "مقدار",
    "used_count": "تعداد استفاده",
    "coupon": "کوپن",
    "rating": "امتیاز",
    "is_approved": "تأییدشده",
    "title": "عنوان",
    "body": "متن",
    "referred_by": "معرف",
    "points": "امتیاز",
    "lifetime_points": "امتیاز کل",
    "updated_at": "آخرین به‌روزرسانی",
    "account": "حساب",
    "reason": "دلیل",
    "session_key": "نشست",
    "viewed_at": "زمان بازدید",
    "username": "نام کاربری",
    "is_staff": "مدیر",
    "is_superuser": "مدیر ارشد",
    "last_login": "آخرین ورود",
    "action": "رویداد",
    "target_type": "نوع هدف",
    "target_id": "شناسه هدف",
    "ip_address": "آی‌پی",
    "alt_text": "متن جایگزین",
    "is_main": "تصویر اصلی",
    "is_read": "خوانده‌شده",
}


def _columns(resource: StaffResource):
    columns = []
    for name in resource.list_fields:
        try:
            field = resource.model._meta.get_field(name)
            label = getattr(field, "verbose_name", name)
            if label == name and label in FIELD_LABELS:
                label = FIELD_LABELS[name]
        except Exception:
            label = FIELD_LABELS.get(name, name)
        columns.append(SimpleNamespace(name=name, verbose_name=label))
    return columns


def _search(resource: StaffResource, queryset, query: str):
    if not query:
        return queryset
    condition = Q()
    for field in resource.search_fields:
        condition |= Q(**{f"{field}__icontains": query})
    if query.isdigit() and resource.key in {"orders", "payments"}:
        pk_field = "pk" if resource.key == "orders" else "order_id"
        condition |= Q(**{pk_field: int(query)})
    return queryset.filter(condition) if condition else queryset


def _form(resource: StaffResource, request, instance=None):
    if resource.form is None:
        return None
    kwargs = {
        "data": request.POST if request.method == "POST" else None,
        "files": request.FILES if request.method == "POST" else None,
        "instance": instance,
        "actor": request.user,
    }
    if resource.key == "groups":
        return GroupStaffForm(
            data=request.POST if request.method == "POST" else None,
            initial=(
                {
                    "name": instance.name,
                    "permissions": instance.permissions.all(),
                }
                if instance
                else None
            ),
        )
    return resource.form(**kwargs)


def _audit(
    request,
    action: str,
    resource: StaffResource,
    obj,
    details=None,
    *,
    required: bool = False,
):
    try:
        log_action(
            action=action,
            actor=request.user,
            target_type=resource.model._meta.label_lower,
            target_id=getattr(obj, "pk", ""),
            details=details or {},
            request=request,
        )
    except Exception:
        logger.exception(
            "Audit log write failed action=%s resource=%s", action, resource.key
        )
        if required:
            raise


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@login_required
def dashboard(request):
    if not request.user.is_staff:
        return redirect(f"{reverse('admin:login')}?next={request.path}")

    today = timezone.localdate()
    today_start, today_end = local_day_bounds(today)
    paid_statuses = Order.PAID_STATUSES

    orders_today = Order.objects.filter(
        created_at__gte=today_start, created_at__lt=today_end
    ).count()
    sales_today = (
        Order.objects.filter(
            status__in=paid_statuses,
            paid_at__gte=today_start,
            paid_at__lt=today_end,
        ).aggregate(value=Sum("total_amount"))["value"]
        or 0
    )
    revenue = (
        Order.objects.filter(
            status__in=paid_statuses, paid_at__isnull=False
        ).aggregate(value=Sum("total_amount"))["value"]
        or 0
    )

    lowest_variant_stock = Subquery(
        ProductVariant.objects.filter(product_id=OuterRef("pk"), is_active=True)
        .order_by("stock", "id")
        .values("stock")[:1],
        output_field=IntegerField(),
    )
    stock_products = Product.objects.annotate(
        effective_stock=Coalesce(
            lowest_variant_stock, F("stock"), output_field=IntegerField()
        )
    )

    chart = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        day_start, day_end = local_day_bounds(day)
        amount = (
            Order.objects.filter(
                status__in=paid_statuses,
                paid_at__gte=day_start,
                paid_at__lt=day_end,
            ).aggregate(value=Sum("total_amount"))["value"]
            or 0
        )
        chart.append({"label": day.strftime("%m/%d"), "value": int(amount)})
    max_value = max((item["value"] for item in chart), default=0) or 1
    for item in chart:
        item["height"] = max(8, int(item["value"] * 100 / max_value))

    show_codes = can_view_codes(request.user)
    context = {
        "stats": {
            "sales_today": sales_today,
            "orders_today": orders_today,
            "pending": Order.objects.filter(status=Order.STATUS_PENDING).count(),
            "processing": Order.objects.filter(
                status=Order.STATUS_PROCESSING
            ).count(),
            "revenue": revenue,
            "failed_payments": Payment.objects.filter(
                status=Payment.STATUS_FAILED
            ).count(),
            "low_stock": stock_products.filter(effective_stock__lte=3).count(),
            "available_codes": (
                DigitalCode.objects.filter(is_used=False).count()
                if show_codes
                else None
            ),
        },
        "chart": chart,
        "recent_orders": Order.objects.select_related("user").order_by(
            "-created_at", "-id"
        )[:8],
        "recent_payments": Payment.objects.select_related("order").order_by(
            "-created_at", "-id"
        )[:8],
        "attention_orders": Order.objects.select_related("user")
        .filter(status=Order.STATUS_PROCESSING)
        .order_by("-created_at")[:6],
        "low_stock_products": stock_products.filter(
            effective_stock__lte=3
        ).order_by("effective_stock", "name")[:6],
        "nav": _nav_for(request.user),
        "active": "dashboard",
        "show_codes": show_codes,
    }
    return render(request, "admin_panel/dashboard.html", context)


# ---------------------------------------------------------------------------
# Generic CRUD
# ---------------------------------------------------------------------------
@login_required
def model_list(request, key):
    if not request.user.is_staff:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    resource = RESOURCES.get(key)
    if resource is None:
        return redirect("admin_dashboard")
    _guard_resource(request, resource)

    queryset = resource.model.objects.order_by("-pk")
    query = request.GET.get("q", "").strip()
    queryset = _search(resource, queryset, query)

    page = Paginator(queryset, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "admin_panel/model_list.html",
        {
            "key": key,
            "title": resource.label,
            "page": page,
            "columns": _columns(resource),
            "nav": _nav_for(request.user),
            "active": key,
            "query": query,
            "can_create": (
                resource.can_create
                and resource.form is not None
                and _can_create_resource(resource, request.user)
            ),
            "can_edit": (
                resource.can_edit
                and resource.form is not None
                and _can_edit_resource(resource, request.user)
            ),
            "can_delete": (
                resource.can_delete
                and _can_delete_resource(resource, request.user)
            ),
            "readonly": not resource.can_edit,
        },
    )


def _render_form(request, resource, form, *, obj=None):
    return render(
        request,
        "admin_panel/model_form.html",
        {
            "key": resource.key,
            "title": ("ویرایش " if obj else "افزودن ") + resource.label,
            "form": form,
            "object": obj,
            "nav": _nav_for(request.user),
            "active": resource.key,
            "image_errors": [],
            "can_delete": (
                resource.can_delete
                and obj is not None
                and _can_delete_resource(resource, request.user)
            ),
        },
    )


@login_required
def model_create(request, key):
    if not request.user.is_staff:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    resource = RESOURCES.get(key)
    if resource is None:
        return redirect("admin_dashboard")
    if not resource.can_create or resource.form is None:
        raise PermissionDenied
    _guard_resource(request, resource, write=True)

    form = _form(resource, request)

    if request.method == "POST" and form.is_valid():
        if key == "groups":
            try:
                with transaction.atomic():
                    group = Group.objects.create(name=form.cleaned_data["name"])
                    group.permissions.set(form.cleaned_data["permissions"])
                    _audit(
                        request,
                        AuditLog.ACTION_STAFF_EDIT,
                        resource,
                        group,
                        required=True,
                    )
            except IntegrityError:
                form.add_error("name", "گروهی با این نام وجود دارد.")
                return _render_form(request, resource, form)
            messages.success(request, "گروه دسترسی ایجاد شد.")
            return redirect("admin_model_list", key=key)

        uploads = request.FILES.getlist("product_images")
        if key == "products":
            errors = [
                f"{getattr(upload, 'name', 'تصویر')}: {error}"
                for upload in uploads
                if (error := validate_image_upload(upload))
            ]
            if errors:
                form.add_error(None, "؛ ".join(errors))
                return _render_form(request, resource, form)

        if resource.sensitive:
            try:
                with transaction.atomic():
                    obj = form.save()
                    _audit(
                        request,
                        AuditLog.ACTION_STAFF_EDIT,
                        resource,
                        obj,
                        required=True,
                    )
            except IntegrityError:
                form.add_error(None, "ذخیره‌سازی به دلیل تعارض داده انجام نشد.")
                return _render_form(request, resource, form)
        else:
            obj = form.save()

        if key == "products" and uploads:
            image_errors = save_product_images(
                obj,
                uploads,
                alt_text=request.POST.get("image_alt_text", ""),
                make_main=request.POST.get("make_main_image") == "1",
            )
            if image_errors:
                messages.error(request, "؛ ".join(image_errors))

        if not resource.sensitive:
            _audit(request, AuditLog.ACTION_STAFF_EDIT, resource, obj)
        messages.success(request, "مورد جدید با موفقیت ایجاد شد.")
        return redirect("admin_model_edit", key=key, pk=obj.pk)

    return _render_form(request, resource, form)


@login_required
def model_edit(request, key, pk):
    if not request.user.is_staff:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    resource = RESOURCES.get(key)
    if resource is None:
        return redirect("admin_dashboard")
    if not resource.can_edit or resource.form is None:
        raise PermissionDenied
    _guard_resource(request, resource, write=True)

    obj = get_object_or_404(resource.model.objects.all(), pk=pk)

    if key == "codes" and (obj.is_used or obj.order_item_id):
        raise PermissionDenied

    if key == "users" and not request.user.is_superuser:
        if obj.is_staff or obj.is_superuser:
            raise PermissionDenied

    form = _form(resource, request, instance=obj)
    old_status = obj.status if key == "orders" else None

    if request.method == "POST" and form.is_valid():
        if key == "groups":
            try:
                with transaction.atomic():
                    obj.name = form.cleaned_data["name"]
                    obj.save(update_fields=["name"])
                    obj.permissions.set(form.cleaned_data["permissions"])
                    _audit(
                        request,
                        AuditLog.ACTION_STAFF_EDIT,
                        resource,
                        obj,
                        required=True,
                    )
            except IntegrityError:
                form.add_error("name", "گروهی با این نام وجود دارد.")
                return _render_form(request, resource, form, obj=obj)
            messages.success(request, "تغییرات ذخیره شد.")
            return redirect("admin_model_list", key=key)

        uploads = request.FILES.getlist("product_images")
        if key == "products":
            errors = [
                f"{getattr(upload, 'name', 'تصویر')}: {error}"
                for upload in uploads
                if (error := validate_image_upload(upload))
            ]
            if errors:
                form.add_error(None, "؛ ".join(errors))
                return _render_form(request, resource, form)

        if resource.sensitive:
            try:
                with transaction.atomic():
                    obj = form.save()
                    action = (
                        AuditLog.ACTION_ORDER_STATUS
                        if key == "orders"
                        else AuditLog.ACTION_STAFF_EDIT
                    )
                    details = (
                        {"from": old_status, "to": obj.status}
                        if key == "orders"
                        else {"changed": list(form.changed_data)}
                    )
                    _audit(
                        request,
                        action,
                        resource,
                        obj,
                        details,
                        required=True,
                    )
            except IntegrityError:
                form.add_error(None, "ذخیره‌سازی به دلیل تعارض داده انجام نشد.")
                return _render_form(request, resource, form, obj=obj)
        else:
            obj = form.save()

        if key == "products" and uploads:
            image_errors = save_product_images(
                obj,
                uploads,
                alt_text=request.POST.get("image_alt_text", ""),
                make_main=request.POST.get("make_main_image") == "1",
            )
            if image_errors:
                messages.error(request, "؛ ".join(image_errors))

        if not resource.sensitive:
            _audit(request, AuditLog.ACTION_STAFF_EDIT, resource, obj)

        messages.success(request, "تغییرات با موفقیت ذخیره شد.")
        return redirect("admin_model_list", key=key)

    return _render_form(request, resource, form, obj=obj)


@login_required
@require_POST
def model_delete(request, key, pk):
    if not request.user.is_staff:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    resource = RESOURCES.get(key)
    if resource is None:
        return redirect("admin_dashboard")
    if not resource.can_delete or resource.form is None:
        raise PermissionDenied
    _guard_resource(request, resource, write=True)

    obj = get_object_or_404(resource.model.objects.all(), pk=pk)

    if key == "codes" and (obj.is_used or obj.order_item_id):
        raise PermissionDenied

    if key == "users":
        if obj.pk == request.user.pk:
            messages.error(request, "حساب مدیر فعلی قابل حذف نیست.")
            return redirect("admin_model_list", key=key)
        if (obj.is_staff or obj.is_superuser) and not request.user.is_superuser:
            raise PermissionDenied

    try:
        with transaction.atomic():
            deleted_pk = obj.pk
            details = {"deleted": str(obj)}
            obj.delete()
            _audit(
                request,
                AuditLog.ACTION_STAFF_EDIT,
                resource,
                SimpleNamespace(pk=deleted_pk),
                details,
                required=resource.sensitive,
            )
        messages.success(request, "مورد با موفقیت حذف شد.")
    except ProtectedError:
        messages.error(
            request,
            "این مورد به سفارش یا داده دیگری متصل است و قابل حذف نیست.",
        )
    except Exception as exc:
        # A sensitive deletion must not be committed without its audit row.
        logger.exception("Sensitive staff deletion failed for %s", resource.key)
        messages.error(
            request,
            "حذف انجام نشد؛ ثبت گزارش امنیتی یا حذف داده کامل نشد.",
        )
        if not resource.sensitive:
            raise exc

    return redirect("admin_model_list", key=key)


@login_required
@require_POST
def logout_view(request):
    if not request.user.is_staff:
        raise PermissionDenied
    logout(request)
    return redirect(reverse("admin:login"))


# ---------------------------------------------------------------------------
# Digital codes: restricted export/import
# ---------------------------------------------------------------------------
@require_GET
def codes_export(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    if not can_view_codes(request.user):
        raise PermissionDenied

    # Build the complete CSV before writing the audit row. If auditing fails,
    # no code is ever sent to the browser.
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        [
            "code",
            "pin",
            "product_id",
            "variant_id",
            "is_used",
            "order_item_id",
            "used_at",
        ]
    )
    count = 0
    for item in DigitalCode.objects.order_by("id").iterator():
        writer.writerow(
            [
                item.code,
                item.pin,
                item.product_id,
                item.variant_id or "",
                int(item.is_used),
                item.order_item_id or "",
                item.used_at.isoformat() if item.used_at else "",
            ]
        )
        count += 1

    try:
        _audit(
            request,
            AuditLog.ACTION_DIGITAL_EXPORT,
            RESOURCES["codes"],
            SimpleNamespace(pk=""),
            {"rows": count},
            required=True,
        )
    except Exception:
        return HttpResponse(
            "ثبت گزارش امنیتی خروجی ممکن نشد؛ خروجی ارسال نشد.",
            status=500,
            content_type="text/plain; charset=utf-8",
        )

    response = HttpResponse(
        output.getvalue(), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = 'attachment; filename="giftbaaz-digital-codes.csv"'
    response["Cache-Control"] = "no-store"
    return response


@login_required
def codes_import(request):
    if not request.user.is_staff:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    if not (
        request.user.is_superuser
        or request.user.has_perm("store.add_digitalcode")
    ):
        raise PermissionDenied

    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if uploaded is None:
            messages.error(request, "فایل CSV انتخاب نشده است.")
            return redirect("codes_import")

        max_bytes = int(
            getattr(settings, "DIGITAL_CODE_IMPORT_MAX_BYTES", 2 * 1024 * 1024)
        )
        if uploaded.size > max_bytes:
            messages.error(request, "حجم فایل بیش از حد مجاز است.")
            return redirect("codes_import")

        try:
            decoded = uploaded.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            messages.error(request, "فایل CSV باید UTF-8 باشد.")
            return redirect("codes_import")

        reader = csv.DictReader(io.StringIO(decoded))
        required = {"code", "product_id"}
        if not required.issubset(set(reader.fieldnames or [])):
            messages.error(request, "ستون‌های code و product_id الزامی هستند.")
            return redirect("codes_import")

        max_rows = int(
            getattr(settings, "DIGITAL_CODE_IMPORT_MAX_ROWS", 10000)
        )
        rows = list(reader)
        if len(rows) > max_rows:
            messages.error(request, "تعداد ردیف‌ها بیش از حد مجاز است.")
            return redirect("codes_import")

        product_ids = set(
            Product.objects.values_list("id", flat=True)
        )
        variants = dict(
            ProductVariant.objects.values_list("id", "product_id")
        )
        existing = {
            code.casefold()
            for code in DigitalCode.objects.values_list("code", flat=True)
        }
        seen: set[str] = set()
        to_create: list[DigitalCode] = []
        duplicates = invalid = 0

        for row in rows:
            code = (row.get("code") or "").strip()
            folded = code.casefold()
            if not code or len(code) > 255:
                invalid += 1
                continue
            if folded in existing or folded in seen:
                duplicates += 1
                continue
            try:
                product_id = int(row.get("product_id") or "")
                variant_id = (
                    int(row["variant_id"]) if (row.get("variant_id") or "").strip() else None
                )
            except (TypeError, ValueError):
                invalid += 1
                continue
            if product_id not in product_ids:
                invalid += 1
                continue
            if variant_id is not None and variants.get(variant_id) != product_id:
                invalid += 1
                continue
            pin = (row.get("pin") or "").strip()[:200]
            to_create.append(
                DigitalCode(
                    code=code,
                    pin=pin,
                    product_id=product_id,
                    variant_id=variant_id,
                )
            )
            seen.add(folded)

        try:
            with transaction.atomic():
                if to_create:
                    DigitalCode.objects.bulk_create(to_create, batch_size=500)
                _audit(
                    request,
                    AuditLog.ACTION_DIGITAL_IMPORT,
                    RESOURCES["codes"],
                    SimpleNamespace(pk=""),
                    {
                        "created": len(to_create),
                        "duplicates": duplicates,
                        "invalid": invalid,
                    },
                    required=True,
                )
        except IntegrityError:
            logger.exception("Digital-code import hit a database constraint")
            messages.error(
                request,
                "واردسازی انجام نشد؛ کدها با داده موجود یا یکدیگر تعارض دارند.",
            )
            return redirect("codes_import")
        except Exception:
            logger.exception("Digital-code import failed and was rolled back")
            messages.error(
                request,
                "واردسازی انجام نشد؛ ثبت گزارش امنیتی یا ذخیره داده کامل نشد.",
            )
            return redirect("codes_import")

        messages.success(
            request,
            f"{len(to_create)} کد وارد شد؛ {duplicates} تکراری و {invalid} ردیف نامعتبر نادیده گرفته شد.",
        )
        return redirect("codes_import")

    return render(
        request,
        "admin_tools/codes_import.html",
        {"nav": _nav_for(request.user), "active": "codes"},
    )


@login_required
def analytics(request):
    if not request.user.is_staff:
        return redirect(f"{reverse('admin:login')}?next={request.path}")

    paid = Order.PAID_STATUSES
    revenue = (
        Order.objects.filter(
            status__in=paid, paid_at__isnull=False
        ).aggregate(value=Sum("total_amount"))["value"]
        or 0
    )
    today_start, today_end = local_day_bounds()
    today = (
        Order.objects.filter(
            status__in=paid,
            paid_at__gte=today_start,
            paid_at__lt=today_end,
        ).aggregate(value=Sum("total_amount"))["value"]
        or 0
    )
    return render(
        request,
        "admin_tools/analytics.html",
        {
            "revenue": revenue,
            "today": today,
            "nav": _nav_for(request.user),
            "active": "dashboard",
            "ip": client_ip(request),
        },
    )
