"""Checkout: order creation and coupon display."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from store.forms import CheckoutForm
from store.models import Coupon, CouponRedemption, Order
from store.services.cart import get_cart_items
from store.services.checkout import (
    CartEmptyError,
    CouponNoLongerValidError,
    create_order_from_cart,
)


def _coupon_preview(request, subtotal):
    code = str(request.session.get("coupon_code") or "").strip().upper()
    if not code:
        return "", 0
    coupon = Coupon.objects.filter(code=code).first()
    if (
        coupon is None
        or not coupon.is_valid_now
        or CouponRedemption.objects.filter(
            coupon=coupon, user=request.user
        ).exists()
    ):
        # Do not silently drop the code here. Keeping it in the session lets
        # order creation reject the checkout explicitly instead of charging the
        # customer the undiscounted total without their consent.
        return "", 0
    discount = coupon.discount_for(subtotal)
    if discount <= 0:
        return "", 0
    return coupon.code, discount


@login_required
def checkout(request):
    items, subtotal = get_cart_items(request)
    if not items:
        messages.error(request, "سبد خرید شما خالی است.")
        return redirect("shop")

    coupon_code, coupon_discount = _coupon_preview(request, subtotal)
    payable = max(0, subtotal - coupon_discount)

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            try:
                order = create_order_from_cart(request, form.cleaned_data)
            except CartEmptyError:
                messages.error(request, "سبد خرید شما دیگر موجود نیست.")
                return redirect("cart")
            except CouponNoLongerValidError as exc:
                request.session.pop("coupon_code", None)
                request.session.pop("coupon_discount", None)
                request.session.modified = True
                messages.error(request, str(exc))
                return redirect("checkout")
            return redirect("payment", order_id=order.id)
    else:
        form = CheckoutForm(initial={"email": request.user.email})

    return render(
        request,
        "checkout.html",
        {
            "form": form,
            "items": items,
            "subtotal": subtotal,
            "coupon_code": coupon_code,
            "coupon_discount": coupon_discount,
            "total": payable,
        },
    )


@login_required
def order_list_redirect(request):
    return redirect("orders")
