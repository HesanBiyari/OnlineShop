from django.db.models import Prefetch
from django.shortcuts import render

from .models import Category, Product, ProductImage


def home(request):
    # برای هر محصول، عکس اصلی را اول از همه بیاور
    product_images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("-is_main", "id"),
        to_attr="homepage_images",
    )

    products = (
        Product.objects.select_related("category", "discount")
        .prefetch_related(product_images)
        .order_by("-created_at")
    )

    # محصولات ویژه:
    # اول محصولاتی که تخفیف دارند
    featured_products = list(
        products.filter(discount__is_active=True).order_by("-created_at")[:4]
    )

    # اگر تعداد محصولات تخفیف‌دار کمتر از ۴ بود،
    # از جدیدترین محصولات برای تکمیل بخش ویژه استفاده کن.
    featured_ids = {product.id for product in featured_products}

    if len(featured_products) < 4:
        remaining = 4 - len(featured_products)

        extra_products = list(
            products.exclude(id__in=featured_ids).order_by("-created_at")[:remaining]
        )

        featured_products.extend(extra_products)

    # جدیدترین محصولات
    new_products = list(products[:4])

    # آخرین ۵ دسته‌بندی
    categories = Category.objects.order_by("name")[:5]

    context = {
        "categories": categories,
        "featured_products": featured_products,
        "new_products": new_products,
    }

    return render(request, "home.html", context)
