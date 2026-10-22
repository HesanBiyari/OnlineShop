"""Django admin configuration (technical fallback for the custom panel)."""

from __future__ import annotations

import csv

from django.contrib import admin, messages
from django.http import HttpResponse

from .models import (
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
from .services.audit import log_action


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class DiscountInline(admin.StackedInline):
    model = Discount
    extra = 0
    max_num = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "price",
        "stock",
        "is_bestseller",
        "bestseller_priority",
        "created_at",
    )
    list_filter = ("category", "is_bestseller")
    search_fields = ("name", "description")
    ordering = ("is_bestseller", "bestseller_priority", "-created_at")
    list_select_related = ("category",)
    list_editable = ("is_bestseller", "bestseller_priority")
    fieldsets = (
        ("اطلاعات اصلی", {"fields": ("name", "category", "description", "price", "stock")}),
        (
            "نمایش و فروش",
            {
                "fields": ("is_bestseller", "bestseller_priority"),
                "description": "کنترل نمایش محصول در بخش پرفروش‌ها.",
            },
        ),
    )
    inlines = [ProductVariantInline, ProductImageInline, DiscountInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("name", "product", "final_price_admin", "stock", "sku", "is_active")
    list_filter = ("is_active", "product")
    search_fields = ("name", "sku", "product__name")
    list_select_related = ("product",)

    @admin.display(description="قیمت نهایی")
    def final_price_admin(self, obj):
        return f"{obj.final_price:,} تومان"


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "alt_text", "is_main")
    list_filter = ("is_main",)
    search_fields = ("product__name",)
    list_select_related = ("product",)


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ("product", "percent", "is_active", "starts_at", "ends_at")
    list_filter = ("is_active",)
    search_fields = ("product__name",)
    list_select_related = ("product",)


@admin.register(DigitalCode)
class DigitalCodeAdmin(admin.ModelAdmin):
    list_display = ("product", "variant", "code", "is_used", "order_item", "used_at")
    list_filter = ("is_used", "product", "variant")
    search_fields = ("code", "product__name", "variant__name")
    list_select_related = ("product", "variant", "order_item")
    readonly_fields = ("used_at",)
    actions = ("export_selected",)

    def has_export_permission(self, request) -> bool:
        return request.user.is_superuser or request.user.has_perm(
            "store.export_digitalcode"
        )

    # Codes and PINs are saleable secrets. Django admin's default
    # view/change permissions are not enough: only users who may export codes
    # may open the code screens at all.
    def has_module_permission(self, request):
        return self.has_export_permission(request)

    def has_view_permission(self, request, obj=None):
        return self.has_export_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_export_permission(request)

    def has_add_permission(self, request):
        return request.user.is_superuser or request.user.has_perm(
            "store.add_digitalcode"
        )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.has_perm(
            "store.delete_digitalcode"
        )

    @admin.action(description="خروجی CSV کدهای انتخاب‌شده (محدود و ثبت‌شده)")
    def export_selected(self, request, queryset):
        if not self.has_export_permission(request):
            self.message_user(
                request, "شما اجازه خروجی کدها را ندارید.", level=messages.ERROR
            )
            return None

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            'attachment; filename="giftbaaz-selected-codes.csv"'
        )
        response["Cache-Control"] = "no-store"
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["code", "pin", "product_id", "variant_id", "is_used"])
        count = 0
        for item in queryset.iterator():
            writer.writerow(
                [item.code, item.pin, item.product_id, item.variant_id or "", int(item.is_used)]
            )
            count += 1
        log_action(
            action=AuditLog.ACTION_DIGITAL_EXPORT,
            actor=request.user,
            target_type="store.digitalcode",
            details={"rows": count, "source": "django_admin"},
            request=request,
        )
        return response


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "product",
        "variant",
        "product_name",
        "variant_name",
        "quantity",
        "unit_price",
        "total_price",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "phone_display",
        "status",
        "total_amount_display",
        "payment_ref",
        "created_at",
        "paid_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "email", "phone", "payment_ref")
    readonly_fields = (
        "user",
        "total_amount",
        "payment_ref",
        "created_at",
        "paid_at",
    )
    list_select_related = ("user",)
    inlines = [OrderItemInline]

    @admin.display(description="موبایل")
    def phone_display(self, obj):
        return obj.phone

    @admin.display(description="مبلغ")
    def total_amount_display(self, obj):
        return f"{obj.total_amount:,} تومان"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "gateway",
        "amount_display",
        "status",
        "authority",
        "reference_id",
        "created_at",
        "paid_at",
    )
    list_filter = ("gateway", "status", "created_at")
    search_fields = ("authority", "reference_id", "order__id", "order__phone")
    list_select_related = ("order",)
    readonly_fields = (
        "order",
        "gateway",
        "amount",
        "currency",
        "authority",
        "reference_id",
        "status",
        "gateway_code",
        "gateway_message",
        "created_at",
        "updated_at",
        "paid_at",
    )

    @admin.display(description="مبلغ")
    def amount_display(self, obj):
        return f"{obj.amount:,} تومان"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "target_type", "target_id", "ip_address")
    list_filter = ("action", "created_at")
    search_fields = ("action", "target_type", "target_id", "actor__username")
    readonly_fields = (
        "actor",
        "action",
        "target_type",
        "target_id",
        "details",
        "ip_address",
        "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


for _model in (
    Coupon,
    CouponRedemption,
    LoyaltyAccount,
    LoyaltyTransaction,
    Notification,
    RecentlyViewed,
    Referral,
    Review,
    Wishlist,
):
    try:
        admin.site.register(_model)
    except admin.sites.AlreadyRegistered:
        pass
