"""Read queries for the storefront."""

from __future__ import annotations

from django.db.models import (
    Case,
    DecimalField,
    Exists,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone

from store.models import Category, Product, ProductImage, ProductVariant


def active_discount_q(now=None) -> Q:
    now = now or timezone.now()
    return (
        Q(discount__is_active=True)
        & (Q(discount__starts_at__isnull=True) | Q(discount__starts_at__lte=now))
        & (Q(discount__ends_at__isnull=True) | Q(discount__ends_at__gte=now))
    )


def product_queryset():
    images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("-is_main", "id"),
        to_attr="display_images",
    )
    active_variants = Prefetch(
        "variants",
        queryset=ProductVariant.objects.filter(is_active=True).order_by("price", "id"),
        to_attr="active_variants",
    )
    return (
        Product.objects.select_related("category", "discount")
        .prefetch_related(images, active_variants)
    )


def available_products():
    available_variant = ProductVariant.objects.filter(
        product_id=OuterRef("pk"), is_active=True, stock__gt=0
    )
    any_active_variant = ProductVariant.objects.filter(
        product_id=OuterRef("pk"), is_active=True
    )
    return (
        product_queryset()
        .annotate(
            has_available_variant=Exists(available_variant),
            has_any_active_variant=Exists(any_active_variant),
        )
        .filter(
            Q(has_available_variant=True)
            | Q(has_any_active_variant=False, stock__gt=0)
        )
    )


def home_sections() -> dict:
    products = available_products().order_by("-created_at", "-id")

    featured = list(products.filter(active_discount_q())[:4])
    featured_ids = {product.id for product in featured}
    if len(featured) < 4:
        featured.extend(
            list(products.exclude(id__in=featured_ids)[: 4 - len(featured)])
        )

    new_products = list(products[:4])

    bestsellers = list(
        products.filter(is_bestseller=True).order_by(
            "bestseller_priority", "-created_at", "-id"
        )[:4]
    )
    if len(bestsellers) < 4:
        selected_ids = {product.id for product in bestsellers}
        bestsellers.extend(
            list(
                Product.objects.filter(
                    orderitem__order__status__in=(
                        "paid",
                        "processing",
                        "completed",
                    )
                )
                .exclude(id__in=selected_ids)
                .annotate(sold_units=Sum("orderitem__quantity"))
                .filter(sold_units__gt=0)
                .order_by("-sold_units", "-created_at", "-id")[
                    : 4 - len(bestsellers)
                ]
            )
        )

    return {
        "categories": Category.objects.order_by("name")[:5],
        "featured_products": featured,
        "new_products": new_products,
        "bestseller_products": bestsellers,
    }


def _price_ordering_annotations():
    variant_price = Subquery(
        ProductVariant.objects.filter(
            product_id=OuterRef("pk"), is_active=True
        )
        .order_by("price", "id")
        .values("price")[:1],
        output_field=DecimalField(max_digits=14, decimal_places=0),
    )
    discount_percent = Case(
        When(active_discount_q(), then=F("discount__percent")),
        default=Value(0),
        output_field=IntegerField(),
    )
    sort_price = Cast(
        ExpressionWrapper(
            Coalesce(F("_variant_price"), F("price"))
            * (Value(100) - F("_discount_percent"))
            / Value(100),
            output_field=DecimalField(max_digits=14, decimal_places=0),
        ),
        DecimalField(max_digits=14, decimal_places=0),
    )
    return variant_price, discount_percent, sort_price


def shop_products(query: str, category_slug: str, sort: str):
    products = product_queryset()

    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    if category_slug:
        products = products.filter(category__slug=category_slug)

    if sort in {"price_low", "price_high"}:
        variant_price, discount_percent, sort_price = _price_ordering_annotations()
        products = products.annotate(
            _variant_price=variant_price,
            _discount_percent=discount_percent,
        ).annotate(_catalog_price_sort=sort_price)

    if sort == "price_low":
        return products.order_by("_catalog_price_sort", "id")
    if sort == "price_high":
        return products.order_by("-_catalog_price_sort", "-id")
    if sort == "name":
        return products.order_by("name", "id")
    return products.order_by("-created_at", "-id")


def related_products(product: Product):
    if product.category_id is None:
        return []
    return list(
        product_queryset()
        .filter(category_id=product.category_id)
        .exclude(pk=product.pk)
        .order_by("-created_at", "-id")[:4]
    )
