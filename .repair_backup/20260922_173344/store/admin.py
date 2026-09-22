from django.contrib import admin

from .models import (
    Category,
    DigitalCode,
    Discount,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductVariant,
)


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
    list_display = (
        "name",
        "slug",
    )

    search_fields = (
        "name",
    )

    prepopulated_fields = {
        "slug": ("name",),
    }


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "price",
        "stock",
        "created_at",
    )

    list_filter = (
        "category",
    )

    search_fields = (
        "name",
        "description",
    )

    ordering = (
        "-created_at",
    )

    inlines = [
        ProductVariantInline,
        ProductImageInline,
        DiscountInline,
    ]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "product",
        "price",
        "stock",
        "sku",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "sku",
        "product__name",
    )


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "alt_text",
        "is_main",
    )

    list_filter = (
        "is_main",
    )

    search_fields = (
        "product__name",
    )


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "percent",
        "is_active",
        "starts_at",
        "ends_at",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "product__name",
    )


@admin.register(DigitalCode)
class DigitalCodeAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "variant",
        "code",
        "is_used",
        "order_item",
        "used_at",
    )

    list_filter = (
        "is_used",
        "product",
        "variant",
    )

    search_fields = (
        "code",
        "product__name",
        "variant__name",
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
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
        "status",
        "total_amount",
        "payment_ref",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "user__username",
        "email",
        "phone",
        "payment_ref",
    )

    readonly_fields = (
        "created_at",
        "paid_at",
    )

    inlines = [
        OrderItemInline,
    ]