"""Idempotent, concurrency-safe digital delivery."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from store.models import DigitalCode, Order, OrderItem


def _available_codes(item: OrderItem, limit: int):
    filters = {
        "product_id": item.product_id,
        "is_used": False,
        "order_item__isnull": True,
    }
    if item.variant_id:
        filters["variant_id"] = item.variant_id
    else:
        filters["variant__isnull"] = True
    return list(
        DigitalCode.objects.select_for_update()
        .filter(**filters)
        .order_by("id")[:limit]
    )


def deliver_digital_codes(order: Order) -> bool:
    """Assign one unused code per ordered unit.

    Delivery is all-or-nothing *per line*: if a line needs three codes and only
    two are available, none of the codes for that line are consumed. Re-running
    the function after success is safe and assigns nothing new.
    """

    all_delivered = True

    with transaction.atomic():
        items = list(
            order.items.select_related("product", "variant").order_by("id")
        )
        for item in items:
            existing = item.digital_codes.count()
            needed = item.quantity - existing
            if needed <= 0:
                continue

            codes = _available_codes(item, needed)
            if len(codes) < needed:
                all_delivered = False
                continue

            now = timezone.now()
            for code in codes:
                code.is_used = True
                code.used_at = now
                code.order_item_id = item.id
                code.save(update_fields=["is_used", "used_at", "order_item"])

    return all_delivered
