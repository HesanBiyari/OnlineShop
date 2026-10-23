"""Dashboard tags retained for backwards-compatible templates."""

from django import template
from django.db.models import Sum

from store.models import DigitalCode, Order, Payment, Product
from store.services.reporting import local_day_bounds

register = template.Library()


@register.simple_tag
def sales_today():
    start, end = local_day_bounds()
    value = (
        Order.objects.filter(
            status__in=Order.PAID_STATUSES,
            paid_at__gte=start,
            paid_at__lt=end,
        ).aggregate(total=Sum("total_amount"))["total"]
        or 0
    )
    return f"{value:,}"


@register.simple_tag
def orders_today():
    start, end = local_day_bounds()
    return Order.objects.filter(
        created_at__gte=start, created_at__lt=end
    ).count()


@register.simple_tag
def pending_orders():
    return Order.objects.filter(status=Order.STATUS_PENDING).count()


@register.simple_tag
def processing_orders():
    return Order.objects.filter(status=Order.STATUS_PROCESSING).count()


@register.simple_tag
def available_codes():
    return DigitalCode.objects.filter(is_used=False).count()


@register.simple_tag
def failed_payments():
    return Payment.objects.filter(status=Payment.STATUS_FAILED).count()


@register.simple_tag
def low_stock():
    return Product.objects.filter(stock__lte=3).count()


@register.simple_tag
def attention_count():
    return (
        Order.objects.filter(status=Order.STATUS_PROCESSING).count()
        + Payment.objects.filter(status=Payment.STATUS_FAILED).count()
    )


@register.simple_tag
def recent_orders(limit=8):
    return Order.objects.select_related("user").order_by("-created_at", "-id")[
        : int(limit)
    ]
