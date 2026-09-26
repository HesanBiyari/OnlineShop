from django import template
from django.db.models import Sum
from django.utils import timezone
from store.models import DigitalCode, Order, Payment, Product
register = template.Library()

@register.simple_tag
def sales_today():
    day = timezone.localtime().date()
    v = Order.objects.filter(status__in=("paid","processing","completed"), created_at__date=day).aggregate(x=Sum("total_amount"))["x"] or 0
    return f"{v:,}"

@register.simple_tag
def orders_today(): return Order.objects.filter(created_at__date=timezone.localtime().date()).count()
@register.simple_tag
def pending_orders(): return Order.objects.filter(status="pending").count()
@register.simple_tag
def processing_orders(): return Order.objects.filter(status="processing").count()
@register.simple_tag
def available_codes(): return DigitalCode.objects.filter(is_used=False).count()
@register.simple_tag
def failed_payments(): return Payment.objects.filter(status="failed").count()
@register.simple_tag
def low_stock(): return Product.objects.filter(stock__lte=3).count()
@register.simple_tag
def attention_count(): return Order.objects.filter(status="processing").count() + Payment.objects.filter(status="failed").count()

@register.simple_tag
def recent_orders(limit=8):
    return Order.objects.select_related("user").order_by("-created_at","-id")[:int(limit)]

@register.simple_tag
def low_stock_products(limit=6):
    return Product.objects.filter(stock__lte=3).order_by("stock","name")[:int(limit)]