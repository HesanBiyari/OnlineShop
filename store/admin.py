from django.contrib import admin
from .models import (
    Category,
    Product,
    ProductVariant,
    ProductImage,
    Discount,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock", "created_at")
    list_filter = ("category",)
    search_fields = ("name", "description")
    ordering = ("-created_at",)


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
    list_filter = ("is_active",)
    search_fields = ("name", "sku", "product__name")


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "alt_text", "is_main")
    list_filter = ("is_main",)
    search_fields = ("product__name",)


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "percent",
        "is_active",
        "starts_at",
        "ends_at",
    )
    list_filter = ("is_active",)
    search_fields = ("product__name",)