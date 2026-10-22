"""Order read queries scoped to a user."""

from __future__ import annotations

from store.models import Order, OrderItem


def user_orders(user):
    return (
        Order.objects.filter(user=user)
        .prefetch_related("items")
        .order_by("-created_at", "-id")
    )


def user_order_detail(user):
    return Order.objects.filter(user=user).prefetch_related("items__digital_codes")


def order_items_with_codes(order: Order):
    return (
        OrderItem.objects.filter(order=order)
        .select_related("product", "variant")
        .prefetch_related("digital_codes")
        .order_by("id")
    )
