from django.utils import timezone

from .models import DigitalCode


def get_item_price(product, variant=None):
    return variant.final_price if variant else product.final_price


def get_item_stock(product, variant=None):
    return variant.stock if variant else product.stock


def deliver_digital_codes(order):
    all_delivered = True

    for item in order.items.select_related("product", "variant"):
        existing_codes = item.digital_codes.count()
        needed = item.quantity - existing_codes
        if needed <= 0:
            continue

        filters = {
            "product": item.product,
            "is_used": False,
            "order_item__isnull": True,
        }

        if item.variant:
            filters["variant"] = item.variant
        else:
            filters["variant__isnull"] = True

        codes = list(
            DigitalCode.objects
            .select_for_update()
            .filter(**filters)
            .order_by("id")[:needed]
        )

        if len(codes) < needed:
            all_delivered = False

        for code in codes:
            code.is_used = True
            code.used_at = timezone.now()
            code.order_item = item
            code.save(
                update_fields=[
                    "is_used",
                    "used_at",
                    "order_item",
                ]
            )

    return all_delivered
