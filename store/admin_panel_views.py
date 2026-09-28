from __future__ import annotations
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.forms import modelform_factory
from django.db.models import F, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django import forms
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Category, DigitalCode, Discount, Order, OrderItem, Payment, Product, ProductImage, ProductVariant
from .advanced_models import Coupon, CouponRedemption, LoyaltyAccount, LoyaltyTransaction, Notification, RecentlyViewed, Referral, Review, Wishlist

User = get_user_model()



MODEL_MAP = {
    'products': Product,
    'categories': Category,
    'variants': ProductVariant,
    'images': ProductImage,
    'discounts': Discount,
    'codes': DigitalCode,
    'orders': Order,
    'order-items': OrderItem,
    'payments': Payment,
    'coupons': Coupon,
    'coupon-redemptions': CouponRedemption,
    'reviews': Review,
    'referrals': Referral,
    'loyalty': LoyaltyAccount,
    'loyalty-transactions': LoyaltyTransaction,
    'notifications': Notification,
    'recently-viewed': RecentlyViewed,
    'users': User,
    'groups': Group,
}

MODEL_LABELS = {
    'products':'محصولات', 'categories':'دسته‌بندی‌ها', 'variants':'تنوع‌ها', 'images':'تصاویر',
    'discounts':'تخفیف‌ها', 'codes':'کدهای دیجیتال', 'orders':'سفارش‌ها', 'order-items':'آیتم‌های سفارش',
    'payments':'پرداخت‌ها', 'coupons':'کوپن‌ها', 'coupon-redemptions':'مصرف کوپن', 'reviews':'نظرات',
    'referrals':'معرفی‌ها', 'loyalty':'وفاداری', 'loyalty-transactions':'تراکنش امتیاز',
    'notifications':'اعلان‌ها', 'recently-viewed':'بازدیدهای اخیر', 'users':'کاربران', 'groups':'دسترسی‌ها',
}

SUPERUSER_ONLY_KEYS = {"groups"}
READ_ONLY_KEYS = {"payments", "coupon-redemptions", "loyalty-transactions", "recently-viewed"}


def _guard_key(request, key, *, write=False):
    from django.core.exceptions import PermissionDenied
    if key == "groups" and not request.user.is_superuser:
        raise PermissionDenied
    if write and key in READ_ONLY_KEYS:
        raise PermissionDenied


ADMIN_NAV = [
    ('dashboard','داشبورد','📊'),
    ('products','محصولات','🛍️'),
    ('categories','دسته‌بندی‌ها','🗂️'),
    ('variants','تنوع‌ها','🎛️'),
    ('discounts','تخفیف‌ها','🏷️'),
    ('codes','کدهای دیجیتال','🔐'),
    ('orders','سفارش‌ها','📦'),
    ('payments','پرداخت‌ها','💳'),
    ('coupons','کوپن‌ها','🎟️'),
    ('reviews','نظرات','⭐'),
    ('users','کاربران','👥'),
    ('groups','دسترسی‌ها','🛡️'),
]
# ============================================================
# GIFTBAAZ CLEAN ADMIN HELPERS
# ============================================================

def staff_required(view):
    def wrapped(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect(
                "/django-admin/login/"
            )

        if not request.user.is_staff:
            return redirect(
                "/django-admin/login/"
            )

        return view(
            request,
            *args,
            **kwargs,
        )

    return wrapped


def _editable_fields(
    model,
    key,
    user=None,
):

    if key == "users":

        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
        ]

        if (
            user is not None
            and getattr(
                user,
                "is_superuser",
                False,
            )
        ):

            fields.extend(
                [
                    "is_staff",
                    "is_superuser",
                ]
            )

        return fields

    if key == "groups":

        return [
            "name",
            "permissions",
        ]

    fields = []

    blocked = {
        "created_at",
        "updated_at",
        "used_at",
        "final_price",
        "catalog_price",
        "is_used",
    }

    for field in model._meta.get_fields():

        if not getattr(
            field,
            "editable",
            False,
        ):
            continue

        if getattr(
            field,
            "auto_created",
            False,
        ):
            continue

        if getattr(
            field,
            "many_to_many",
            False,
        ):
            continue

        if getattr(
            field,
            "one_to_many",
            False,
        ):
            continue

        if field.name in blocked:
            continue

        if (
            key == "products"
            and field.name == "slug"
        ):
            continue

        if (
            key
            in {
                "orders",
                "payments",
                "order-items",
                "coupon-redemptions",
                "loyalty-transactions",
                "recently-viewed",
            }
            and field.name
            in {
                "user",
                "order",
                "order_item",
                "payment",
                "authority",
            }
        ):
            continue

        fields.append(
            field.name
        )

    return fields


def _model_form(
    key,
    instance=None,
    data=None,
    files=None,
    user=None,
):

    model = MODEL_MAP[key]

    Form = modelform_factory(
        model,
        fields=_editable_fields(
            model,
            key,
            user=user,
        ),
    )

    return Form(
        data=data,
        files=files,
        instance=instance,
    )

# ============================================================
# GIFTBAAZ CLEAN ADMIN HELPERS
# ============================================================








def _qs_for_key(key):
    model = MODEL_MAP.get(key)
    if model is None:
        return None
    return model.objects.all()






class ProductImageUploadForm(forms.Form):
    image=forms.ImageField(required=True)

def _validate_product_images(files):
    errors=[]
    for uploaded in files:
        f=ProductImageUploadForm(files={'image': uploaded})
        if not f.is_valid():
            name=getattr(uploaded,'name','تصویر')
            errors.append(f'{name}: ' + '; '.join(str(e) for e in f.errors.get('image',[])))
    return errors

def _save_product_images(product, request):
    uploads=request.FILES.getlist('product_images')
    if not uploads:
        single=request.FILES.get('product_images')
        uploads=[single] if single else []
    if not uploads:
        return []
    errors=_validate_product_images(uploads)
    if errors:
        return errors
    make_main=request.POST.get('make_main_image') == '1'
    alt_text=request.POST.get('image_alt_text','').strip()[:200]
    has_main=ProductImage.objects.filter(product=product,is_main=True).exists()
    with transaction.atomic():
        if make_main:
            ProductImage.objects.filter(product=product,is_main=True).update(is_main=False)
        for index,uploaded in enumerate(uploads):
            ProductImage.objects.create(
                product=product,
                image=uploaded,
                alt_text=alt_text or getattr(uploaded,'name','').rsplit('.',1)[0][:200],
                is_main=(index == 0 and (make_main or not has_main)),
            )
    return []

def dashboard(request):
    if not request.user.is_authenticated:
        return redirect("/django-admin/login/")

    if not request.user.is_staff:
        return redirect("/django-admin/login/")

    today = timezone.localdate()
    paid_statuses = ("paid", "processing", "completed")
    orders_today = Order.objects.filter(created_at__date=today).count()
    sales_today = Order.objects.filter(status__in=paid_statuses, created_at__date=today).aggregate(v=Sum("total_amount"))["v"] or 0
    revenue = Order.objects.filter(status__in=paid_statuses).aggregate(v=Sum("total_amount"))["v"] or 0
    pending = Order.objects.filter(status="pending").count()
    processing = Order.objects.filter(status="processing").count()
    failed_payments = Payment.objects.filter(status="failed").count()

    lowest_variant_stock = Subquery(
        ProductVariant.objects.filter(product_id=OuterRef("pk"), is_active=True)
        .order_by("stock", "id")
        .values("stock")[:1],
        output_field=IntegerField(),
    )
    effective_stock_expr = Coalesce(
        lowest_variant_stock,
        F("stock"),
        output_field=IntegerField(),
    )
    stock_products = Product.objects.annotate(effective_stock=effective_stock_expr)
    low_stock = stock_products.filter(effective_stock__lte=3).count()
    available_codes = DigitalCode.objects.filter(is_used=False).count()

    chart = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        amount = Order.objects.filter(
            status__in=paid_statuses, created_at__date=day
        ).aggregate(v=Sum("total_amount"))["v"] or 0
        chart.append({"label": day.strftime("%m/%d"), "value": int(amount)})
    max_value = max((item["value"] for item in chart), default=0) or 1
    for item in chart:
        item["height"] = max(8, int(item["value"] * 100 / max_value))

    context = {
        "stats": {
            "sales_today": sales_today,
            "orders_today": orders_today,
            "pending": pending,
            "processing": processing,
            "revenue": revenue,
            "failed_payments": failed_payments,
            "low_stock": low_stock,
            "available_codes": available_codes,
        },
        "chart": chart,
        "recent_orders": Order.objects.select_related("user").order_by("-created_at", "-id")[:8],
        "recent_payments": Payment.objects.select_related("order").order_by("-created_at", "-id")[:8],
        "attention_orders": Order.objects.select_related("user").filter(status="processing").order_by("-created_at")[:6],
        "low_stock_products": stock_products.filter(effective_stock__lte=3).order_by("effective_stock", "name")[:6],
        "nav": ADMIN_NAV,
        "active": "dashboard",
    }
    return render(request, "admin_panel/dashboard.html", context)

def model_list(request,key):
    _guard_key(request, key)
    qs=_qs_for_key(key)
    if qs is None:
        return redirect('admin_dashboard')
    qs=qs.order_by('-pk')
    query=request.GET.get('q','').strip()
    if query:
        q=Q()
        for field in qs.model._meta.get_fields():
            if not getattr(field,'concrete',False):
                continue
            if field.get_internal_type() in {'CharField','TextField','SlugField','EmailField'}:
                q |= Q(**{f'{field.name}__icontains':query})
        if q:
            qs=qs.filter(q)
    paginator=Paginator(qs,15)
    page=paginator.get_page(request.GET.get('page'))
    fields=[]
    for field in qs.model._meta.get_fields():
        if getattr(field,'concrete',False) and not getattr(field,'auto_created',False) and not getattr(field,'many_to_many',False) and not getattr(field,'one_to_many',False):
            fields.append(field)
        if len(fields)>=6:
            break
    return render(request,'admin_panel/model_list.html',{
        'key':key, 'title':MODEL_LABELS.get(key,key), 'page':page, 'fields':fields,
        'nav':ADMIN_NAV, 'active':key, 'query':query,
    })

model_list = staff_required(model_list)


def model_create(request,key):
    _guard_key(request, key, write=True)
    if key not in MODEL_MAP:
        return redirect('admin_dashboard')
    form=_model_form(key, user=request.user)
    image_errors=[]
    if request.method=='POST':
        form=_model_form(key,data=request.POST,files=request.FILES,user=request.user)
        if form.is_valid():
            if key=='products':
                image_errors=_validate_product_images(request.FILES.getlist('product_images'))
            if not image_errors:
                obj=form.save()
                if key=='products':
                    image_errors=_save_product_images(obj,request)
                    if image_errors:
                        obj.delete()
                        return render(request,'admin_panel/model_form.html',{
                            'key':key,'title':'افزودن '+MODEL_LABELS.get(key,key),'form':form,'nav':ADMIN_NAV,'active':key,'image_errors':image_errors,
                        })
                messages.success(request,'مورد جدید با موفقیت ایجاد شد.')
                return redirect('admin_model_edit',key=key,pk=obj.pk)
    return render(request,'admin_panel/model_form.html',{
        'key':key,'title':'افزودن '+MODEL_LABELS.get(key,key),'form':form,'nav':ADMIN_NAV,'active':key,'image_errors':image_errors,
    })

model_create = staff_required(model_create)


def model_edit(request,key,pk):
    _guard_key(request, key, write=True)
    qs=_qs_for_key(key)
    if qs is None:
        return redirect('admin_dashboard')
    obj=get_object_or_404(qs,pk=pk)
    form=_model_form(key,instance=obj,user=request.user)
    image_errors=[]
    if request.method=='POST':
        form=_model_form(key,instance=obj,data=request.POST,files=request.FILES,user=request.user)
        if form.is_valid():
            if key=='products':
                image_errors=_validate_product_images(request.FILES.getlist('product_images'))
            if not image_errors:
                form.save()
                if key=='products':
                    image_errors=_save_product_images(obj,request)
                    if image_errors:
                        messages.error(request,'تصویر اضافه نشد؛ اطلاعات محصول ذخیره شد.')
                        image_errors=[]
                if not image_errors:
                    messages.success(request,'تغییرات با موفقیت ذخیره شد.')
                    return redirect('admin_model_list',key=key)
    return render(request,'admin_panel/model_form.html',{
        'key':key,'title':'ویرایش '+MODEL_LABELS.get(key,key),'form':form,'object':obj,'nav':ADMIN_NAV,'active':key,'image_errors':image_errors,
    })

model_edit = staff_required(model_edit)


def model_delete(request,key,pk):
    _guard_key(request, key, write=True)
    if request.method != "POST":
        return redirect("admin_model_list", key=key)
    qs=_qs_for_key(key)
    if qs is None:
        return redirect('admin_dashboard')
    obj=get_object_or_404(qs,pk=pk)
    if key=='users' and obj.pk==request.user.pk:
        messages.error(request,'حساب مدیر فعلی قابل حذف نیست.')
    elif key=='users' and obj.is_superuser and not request.user.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    else:
        obj.delete()
        messages.success(request,'مورد با موفقیت حذف شد.')
    return redirect('admin_model_list',key=key)

model_delete = staff_required(model_delete)


def logout_view(request):
    logout(request)
    return redirect('/django-admin/login/')

logout_view = staff_required(logout_view)
