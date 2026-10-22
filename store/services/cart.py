"""Session cart.

The cart stores only product/variant identifiers and quantities. Every price
and stock value is recalculated on read, so a stale or tampered session cannot
change what the customer is charged.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Prefetch

from store.models import Product, ProductImage, ProductVariant

from .pricing import get_item_price, get_item_stock

CART_SESSION_KEY = "cart"


def safe_positive_int(value, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def parse_cart_key(key) -> tuple[int, int] | None:
    """Parse ``"<product_id>:<variant_id>"``; variant id 0 means none."""

    try:
        product_id, variant_id = str(key).split(":", 1)
        product_id = int(product_id)
        variant_id = int(variant_id)
    except (TypeError, ValueError):
        return None
    if product_id <= 0 or variant_id < 0:
        return None
    return product_id, variant_id


def cart_key(product_id: int, variant_id: int | None) -> str:
    return f"{product_id}:{variant_id or 0}"


def _session_cart(request) -> dict:
    cart = request.session.get(CART_SESSION_KEY, {})
    return cart if isinstance(cart, dict) else {}


def get_cart_count(request) -> int:
    total = 0
    for key, quantity in _session_cart(request).items():
        if parse_cart_key(key) is None:
            continue
        try:
            total += max(0, int(quantity))
        except (TypeError, ValueError):
            continue
    return total


def get_cart_items(request, *, lock: bool = False) -> tuple[list[dict], Decimal]:
    """Resolve the session cart into priced line items.

    ``lock=True`` must be used inside ``transaction.atomic()`` when the result
    feeds order creation. It locks the product rows (and variant rows through
    the prefetch) on MySQL/MariaDB/PostgreSQL.
    """

    cart = _session_cart(request)
    if not cart:
        return [], Decimal("0")

    entries: list[tuple[str, int, int, int]] = []
    product_ids: set[int] = set()
    for key, raw_quantity in list(cart.items()):
        parsed = parse_cart_key(key)
        if parsed is None:
            continue
        quantity = safe_positive_int(raw_quantity, 0)
        if quantity <= 0:
            continue
        product_id, variant_id = parsed
        entries.append((str(key), product_id, variant_id, quantity))
        product_ids.add(product_id)

    if not entries:
        return [], Decimal("0")

    image_prefetch = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("-is_main", "id"),
        to_attr="display_images",
    )
    variant_queryset = ProductVariant.objects.filter(is_active=True).order_by(
        "price", "id"
    )
    if lock:
        variant_queryset = variant_queryset.select_for_update()
    variant_prefetch = Prefetch(
        "variants", queryset=variant_queryset, to_attr="cart_variants"
    )

    products_query = (
        Product.objects.filter(id__in=product_ids)
        .select_related("category", "discount")
        .prefetch_related(image_prefetch, variant_prefetch)
    )
    if lock:
        products_query = products_query.select_for_update()

    products_by_id = {product.id: product for product in products_query}
    items: list[dict] = []
    total = Decimal("0")
    cleaned_cart: dict[str, int] = {}

    for key, product_id, variant_id, quantity in entries:
        product = products_by_id.get(product_id)
        if not product:
            continue

        active_variants = list(getattr(product, "cart_variants", []))
        variants_by_id = {variant.id: variant for variant in active_variants}
        variant = variants_by_id.get(variant_id) if variant_id else None

        if active_variants and variant is None:
            continue
        if variant_id and variant is None:
            continue

        stock = get_item_stock(product, variant)
        quantity = min(quantity, stock)
        if quantity <= 0:
            continue

        unit_price = get_item_price(product, variant)
        line_total = unit_price * quantity
        images = getattr(product, "display_images", [])
        cleaned_cart[key] = quantity
        items.append(
            {
                "key": key,
                "product": product,
                "variant": variant,
                "quantity": quantity,
                "unit_price": unit_price,
                "total": line_total,
                "image": images[0] if images else None,
                "stock": stock,
            }
        )
        total += line_total

    if cleaned_cart != cart:
        request.session[CART_SESSION_KEY] = cleaned_cart
        request.session.modified = True

    return items, total


def add_to_cart(
    request,
    product: Product,
    *,
    variant_id: str | int | None,
    quantity: str | int | None,
) -> tuple[bool, str]:
    active_variants = product.variants.filter(is_active=True)
    variant = None

    if active_variants.exists():
        try:
            variant = active_variants.get(pk=int(variant_id))
        except (TypeError, ValueError, ProductVariant.DoesNotExist):
            return False, "گزینه انتخاب‌شده معتبر نیست."
    elif str(variant_id or "0") not in {"", "0"}:
        return False, "گزینه انتخاب‌شده معتبر نیست."

    stock = get_item_stock(product, variant)
    if stock <= 0:
        return False, "این محصول موجود نیست."

    cart = _session_cart(request)
    key = cart_key(product.id, variant.id if variant else None)
    current = safe_positive_int(cart.get(key, 0), 0)
    requested = safe_positive_int(quantity, 1)
    cart[key] = min(current + requested, stock)
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True
    return True, "محصول به سبد خرید اضافه شد."


def update_cart_from_post(request) -> None:
    cart = _session_cart(request)

    parsed_keys: dict[str, tuple[int, int]] = {}
    product_ids: set[int] = set()
    for key in cart:
        parsed = parse_cart_key(key)
        if parsed:
            parsed_keys[key] = parsed
            product_ids.add(parsed[0])

    products = {
        product.id: product
        for product in Product.objects.filter(id__in=product_ids)
        .select_related("discount")
        .prefetch_related(
            Prefetch(
                "variants",
                queryset=ProductVariant.objects.filter(is_active=True),
                to_attr="active_cart_variants",
            )
        )
    }

    cleaned: dict[str, int] = {}
    for key, (product_id, variant_id) in parsed_keys.items():
        field_name = f"quantity_{key}"
        if field_name not in request.POST:
            cleaned[key] = cart[key]
            continue

        product = products.get(product_id)
        if not product:
            continue

        active_variants = {
            variant.id: variant
            for variant in getattr(product, "active_cart_variants", [])
        }
        variant = active_variants.get(variant_id) if variant_id else None
        if active_variants and variant is None:
            continue
        if variant_id and variant is None:
            continue

        quantity = safe_positive_int(request.POST.get(field_name), 0)
        stock = get_item_stock(product, variant)
        if quantity > 0 and stock > 0:
            cleaned[key] = min(quantity, stock)

    request.session[CART_SESSION_KEY] = cleaned
    request.session.modified = True


def remove_from_cart(request, key: str) -> None:
    cart = _session_cart(request)
    cart.pop(str(key), None)
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True


def clear_cart(request) -> None:
    request.session[CART_SESSION_KEY] = {}
    request.session.modified = True
