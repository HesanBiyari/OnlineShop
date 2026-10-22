"""Account and order history."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from store.selectors.orders import user_order_detail, user_orders


@login_required
def account(request):
    orders = user_orders(request.user).prefetch_related("items")[:10]
    return render(request, "account.html", {"orders": orders})


@login_required
def orders(request):
    page_obj = Paginator(user_orders(request.user), 10).get_page(
        request.GET.get("page")
    )
    return render(request, "orders.html", {"page_obj": page_obj})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(user_order_detail(request.user), pk=order_id)
    return render(request, "order_detail.html", {"order": order})
