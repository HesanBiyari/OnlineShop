"""Storefront catalog views."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from store.models import Category, Review, Wishlist
from store.selectors.catalog import (
    home_sections,
    product_queryset,
    related_products,
    shop_products,
)
from store.services.promotions import record_recent_view


def home(request):
    return render(request, "home.html", home_sections())


def shop(request):
    query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "").strip()
    sort = request.GET.get("sort", "newest")

    products = shop_products(query, category_slug, sort)
    page_obj = Paginator(products, 12).get_page(request.GET.get("page"))

    return render(
        request,
        "shop.html",
        {
            "page_obj": page_obj,
            "categories": Category.objects.order_by("name"),
            "query": query,
            "selected_category": category_slug,
            "selected_sort": sort,
        },
    )


def product_detail(request, pk):
    product = get_object_or_404(product_queryset(), pk=pk)
    variants = list(getattr(product, "active_variants", []))
    record_recent_view(request, product)

    approved_reviews = Review.objects.filter(
        product=product, is_approved=True
    ).select_related("user")
    wished = (
        request.user.is_authenticated
        and Wishlist.objects.filter(user=request.user, product=product).exists()
    )

    structured_currency = str(getattr(settings, "PAYMENT_CURRENCY", "IRR")).upper()
    catalog_price = Decimal(product.catalog_price)
    structured_price = (
        catalog_price * 10 if structured_currency == "IRR" else catalog_price
    )

    return render(
        request,
        "product_detail.html",
        {
            "product": product,
            "variants": variants,
            "related_products": related_products(product),
            "reviews": approved_reviews[:10],
            "review_count": approved_reviews.count(),
            "wished": wished,
            "structured_currency": structured_currency,
            "structured_price": structured_price,
        },
    )
