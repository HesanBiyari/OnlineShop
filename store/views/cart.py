"""Cart views. Every mutation is POST + CSRF protected."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from store.models import Product
from store.services import cart as cart_service


def cart_view(request):
    items, total = cart_service.get_cart_items(request)
    return render(request, "cart.html", {"items": items, "total": total})


@require_POST
def add_to_cart(request, pk):
    product = get_object_or_404(Product.objects.prefetch_related("variants"), pk=pk)
    ok, message = cart_service.add_to_cart(
        request,
        product,
        variant_id=request.POST.get("variant_id", ""),
        quantity=request.POST.get("quantity", 1),
    )
    if ok:
        messages.success(request, message)
        return redirect("cart")
    messages.error(request, message)
    return redirect("product_detail", pk=pk)


@require_POST
def update_cart(request):
    cart_service.update_cart_from_post(request)
    messages.success(request, "سبد خرید به‌روزرسانی شد.")
    return redirect("cart")


@require_POST
def remove_from_cart(request, key):
    cart_service.remove_from_cart(request, key)
    return redirect("cart")


@require_POST
def clear_cart(request):
    cart_service.clear_cart(request)
    return redirect("cart")
