"""Payment initiation and gateway callback."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.views.decorators.http import require_http_methods

from store.models import Order
from store.services.cart import clear_cart
from store.services.orders import ZeroOrderError, complete_zero_total_order
from store.services.payments import (
    OUTCOME_ALREADY_PAID,
    OUTCOME_CANCELED,
    OUTCOME_FAILED,
    OUTCOME_PAID,
    process_callback,
    start_payment,
)


@login_required
@require_http_methods(["GET", "POST"])
def payment(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    if order.status != Order.STATUS_PENDING:
        return redirect("order_detail", order_id=order.id)

    payment_error = ""

    if request.method == "POST":
        if order.total_amount <= 0:
            try:
                fulfillment = complete_zero_total_order(order)
            except ZeroOrderError as exc:
                messages.error(request, str(exc))
                return redirect("checkout")
            clear_cart(request)
            if fulfillment.completed:
                messages.success(request, "سفارش رایگان شما با موفقیت تکمیل شد.")
            else:
                messages.warning(
                    request,
                    "سفارش رایگان ثبت شد و برای تأمین موجودی/کد در حال پردازش است.",
                )
            return redirect("order_detail", order_id=order.id)

        callback_url = request.build_absolute_uri(
            reverse("payment_callback", args=[order.id])
        )
        result = start_payment(order, callback_url=callback_url)
        if result.ok and result.redirect_url:
            return redirect(result.redirect_url)
        if result.free_order:
            try:
                fulfillment = complete_zero_total_order(order)
            except ZeroOrderError as exc:
                messages.error(request, str(exc))
                return redirect("checkout")
            clear_cart(request)
            if fulfillment.completed:
                messages.success(request, "سفارش رایگان شما با موفقیت تکمیل شد.")
            else:
                messages.warning(
                    request,
                    "سفارش رایگان ثبت شد و برای تأمین موجودی/کد در حال پردازش است.",
                )
            return redirect("order_detail", order_id=order.id)
        if result.already_paid:
            messages.info(request, result.message)
            return redirect("order_detail", order_id=order.id)
        payment_error = result.message

    response = render(
        request,
        "payment.html",
        {
            "order": order,
            "payment_error": payment_error,
            "is_free_order": order.total_amount <= 0,
        },
    )
    add_never_cache_headers(response)
    return response


def _is_owner(request, order: Order) -> bool:
    return (
        request.user.is_authenticated and request.user.pk == order.user_id
    )


@require_http_methods(["GET"])
def payment_callback(request, order_id):
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return render(
            request,
            "payment_result.html",
            {
                "order": None,
                "success": False,
                "message": "سفارش موردنظر پیدا نشد.",
            },
            status=404,
        )

    outcome = process_callback(
        order.id,
        request.GET.get("Authority", ""),
        request.GET.get("Status", ""),
    )

    if outcome.success:
        if _is_owner(request, outcome.order):
            clear_cart(request)
            if outcome.order.status == Order.STATUS_PROCESSING:
                messages.warning(request, outcome.message)
            else:
                messages.success(request, outcome.message)
            return redirect("order_detail", order_id=outcome.order.id)

        response = render(
            request,
            "payment_result.html",
            {
                "order": outcome.order,
                "success": True,
                "message": outcome.message,
            },
        )
        add_never_cache_headers(response)
        return response

    if outcome.kind in {OUTCOME_CANCELED, OUTCOME_FAILED}:
        if _is_owner(request, outcome.order):
            messages.warning(
                request,
                "پرداخت کامل نشد و سفارش لغو شد. سبد خرید شما حفظ شده است؛ "
                "می‌توانید سفارش را دوباره ثبت کنید.",
            )
            return redirect("checkout")
        response = render(
            request,
            "payment_result.html",
            {
                "order": outcome.order,
                "success": False,
                "message": outcome.message,
            },
        )
        add_never_cache_headers(response)
        return response

    status_code = 400 if outcome.kind in {"invalid"} else 200
    response = render(
        request,
        "payment_result.html",
        {
            "order": outcome.order,
            "success": False,
            "message": outcome.message,
        },
        status=status_code,
    )
    add_never_cache_headers(response)
    return response
