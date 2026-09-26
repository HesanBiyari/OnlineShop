from django.contrib import admin

from .models import Category, DigitalCode, Discount, Order, OrderItem, Payment, Product, ProductImage, ProductVariant

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
        ("اطلاعات اصلی", {
            "fields": ("name", "category", "description", "price", "stock"),
        }),
        ("نمایش و فروش", {
            "fields": ("is_bestseller", "bestseller_priority"),
            "description": "کنترل مستقیم نمایش محصول در بخش پرفروش‌های فروشگاه.",
        }),
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

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product", "variant", "product_name", "variant_name", "quantity", "unit_price", "total_price")

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "phone_display", "status", "total_amount_display", "payment_ref", "created_at", "paid_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "email", "phone", "payment_ref")
    readonly_fields = ("created_at", "paid_at")
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
    list_display = ("id", "order", "gateway", "amount_display", "status", "authority", "reference_id", "created_at", "paid_at")
    list_filter = ("gateway", "status", "created_at")
    search_fields = ("authority", "reference_id", "order__id", "order__phone")
    list_select_related = ("order",)
    readonly_fields = ("created_at", "updated_at", "paid_at")

    @admin.display(description="مبلغ")
    def amount_display(self, obj):
        return f"{obj.amount:,} تومان"
