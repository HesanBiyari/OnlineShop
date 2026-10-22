"""Server-side price and stock resolution.

Views never trust prices or stock values supplied by the browser.
"""

from __future__ import annotations

from decimal import Decimal

from store.models import Product, ProductVariant


def get_item_price(product: Product, variant: ProductVariant | None = None) -> Decimal:
    return variant.final_price if variant is not None else product.final_price


def get_item_stock(product: Product, variant: ProductVariant | None = None) -> int:
    return variant.stock if variant is not None else product.stock
