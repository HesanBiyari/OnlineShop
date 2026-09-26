from django.db import transaction
from django.utils import timezone

from .models import DigitalCode


def get_item_price(product, variant=None):
    return variant.final_price if variant else product.final_price


def get_item_stock(product, variant=None):
    return variant.stock if variant else product.stock


def deliver_digital_codes(order):
    """Assign unused digital codes idempotently and atomically."""
    all_delivered = True

    with transaction.atomic():
        for item in order.items.select_related("product", "variant"):
            existing_codes = item.digital_codes.count()
            needed = item.quantity - existing_codes
            if needed <= 0:
                continue

            filters = {
                "product_id": item.product_id,
                "is_used": False,
                "order_item__isnull": True,
            }
            if item.variant_id:
                filters["variant_id"] = item.variant_id
            else:
                filters["variant__isnull"] = True

            codes = list(
                DigitalCode.objects.select_for_update()
                .filter(**filters)
                .order_by("id")[:needed]
            )
            if len(codes) < needed:
                all_delivered = False

            now = timezone.now()
            for code in codes:
                code.is_used = True
                code.used_at = now
                code.order_item_id = item.id
                code.save(update_fields=["is_used", "used_at", "order_item"])

    return all_delivered
