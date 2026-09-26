from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.conf import settings
from django.utils import timezone

from .models import Order, Payment, Product, ProductVariant
from .payment_gateway import get_gateway
from .utils import deliver_digital_codes


@login_required
def payment(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    if order.status != "pending":
        return redirect("order_detail", order_id=order.id)
    payment_record, _ = Payment.objects.get_or_create(
        order=order,
        defaults={"amount": order.total_amount, "currency": getattr(settings, "PAYMENT_CURRENCY", "IRR").upper()},
    )
    try:
        gateway = get_gateway()
        if payment_record.status == "redirected" and payment_record.authority:
            age = timezone.now() - payment_record.updated_at
            if age.total_seconds() < 30 * 60:
                return redirect(gateway.start_url + payment_record.authority)
        callback_url = request.build_absolute_uri(reverse("payment_callback", args=[order.id]))
        result = gateway.create_payment(
            amount_toman=order.total_amount,
            callback_url=callback_url,
            description=f"پرداخت سفارش #{order.id}",
            mobile=order.phone,
            email=order.email,
        )
    except Exception as exc:
        result = type("GatewayError", (), {"ok": False, "code": "APP", "message": str(exc), "authority": "", "reference_id": "", "redirect_url": ""})()
    if result.ok:
        payment_record.amount = order.total_amount
        payment_record.currency = getattr(settings, "PAYMENT_CURRENCY", "IRR").upper()
        payment_record.authority = result.authority
        payment_record.gateway_code = result.code
        payment_record.gateway_message = result.message
        payment_record.status = "redirected"
        payment_record.save(update_fields=["amount", "currency", "authority", "gateway_code", "gateway_message", "status", "updated_at"])
        return redirect(result.redirect_url)
    payment_record.status = "failed"
    payment_record.gateway_code = result.code
    payment_record.gateway_message = result.message
    payment_record.save(update_fields=["status", "gateway_code", "gateway_message", "updated_at"])
    return render(request, "payment.html", {"order": order, "payment_error": result.message})


def payment_callback(request, order_id):
    authority = request.GET.get("Authority", "").strip()
    status = request.GET.get("Status", "").upper()
    order = get_object_or_404(Order, pk=order_id)
    if order.status in {"paid", "processing", "completed"}:
        return _after_callback(request, order)
    if not authority or status != "OK":
        Payment.objects.filter(order=order).update(status="canceled", gateway_code=status or "NOK", gateway_message="پرداخت توسط کاربر تکمیل نشد.")
        if request.user.is_authenticated and request.user.id == order.user_id:
            messages.warning(request, "پرداخت کامل نشد. می‌توانی دوباره تلاش کنی.")
            return redirect("payment", order_id=order.id)
        return render(request, "payment_result.html", {"order": order, "success": False, "message": "پرداخت تکمیل نشد."})
    try:
        with transaction.atomic():
            locked_order = get_object_or_404(Order.objects.select_for_update(), pk=order.id)
            payment_record = get_object_or_404(Payment.objects.select_for_update(), order=locked_order)
            if payment_record.authority != authority:
                payment_record.status = "failed"
                payment_record.gateway_code = "AUTHORITY_MISMATCH"
                payment_record.gateway_message = "شناسه تراکنش با سفارش مطابقت ندارد."
                payment_record.save(update_fields=["status", "gateway_code", "gateway_message", "updated_at"])
                return render(request, "payment_result.html", {"order": locked_order, "success": False, "message": "تراکنش با این سفارش مطابقت ندارد."})
            payment_record.status = "verifying"
            payment_record.save(update_fields=["status", "updated_at"])
            result = get_gateway().verify_payment(amount_toman=locked_order.total_amount, authority=authority)
            if not result.ok:
                payment_record.status = "failed"
                payment_record.gateway_code = result.code
                payment_record.gateway_message = result.message
                payment_record.save(update_fields=["status", "gateway_code", "gateway_message", "updated_at"])
                return render(request, "payment_result.html", {"order": locked_order, "success": False, "message": result.message})
            now = timezone.now()
            payment_record.status = "paid"
            payment_record.reference_id = result.reference_id
            payment_record.gateway_code = result.code
            payment_record.gateway_message = result.message
            payment_record.paid_at = now
            payment_record.save(update_fields=["status", "reference_id", "gateway_code", "gateway_message", "paid_at", "updated_at"])
            if locked_order.status == "pending":
                items = list(locked_order.items.select_related("product", "variant"))
                stock_ok = True
                locked_variants = []
                locked_products = []
                for item in items:
                    if item.variant_id:
                        variant = ProductVariant.objects.select_for_update().get(pk=item.variant_id)
                        locked_variants.append((variant, item))
                        if not variant.is_active or variant.stock < item.quantity:
                            stock_ok = False
                    else:
                        product = Product.objects.select_for_update().get(pk=item.product_id)
                        locked_products.append((product, item))
                        if product.stock < item.quantity:
                            stock_ok = False
                if stock_ok:
                    for variant, item in locked_variants:
                        variant.stock -= item.quantity
                        variant.save(update_fields=["stock"])
                    for product, item in locked_products:
                        product.stock -= item.quantity
                        product.save(update_fields=["stock"])
                    locked_order.status = "paid"
                else:
                    # Payment succeeded, but inventory changed while the buyer was at the gateway.
                    # Keep the order paid/processing rather than fabricating a failed payment.
                    locked_order.status = "processing"
                locked_order.payment_ref = result.reference_id or authority
                locked_order.paid_at = now
                locked_order.save(update_fields=["status", "payment_ref", "paid_at"])
                delivered = deliver_digital_codes(locked_order)
                if locked_order.status == "paid":
                    locked_order.status = "completed" if delivered else "processing"
                    locked_order.save(update_fields=["status"])
        if request.user.is_authenticated and request.user.id == order.user_id:
            request.session["cart"] = {}
            request.session.modified = True
            messages.success(request, "پرداخت با موفقیت تأیید شد.")
            return redirect("order_detail", order_id=order.id)
        return render(request, "payment_result.html", {"order": order, "success": True, "message": "پرداخت با موفقیت تأیید شد."})
    except Exception as exc:
        return render(request, "payment_result.html", {"order": order, "success": False, "message": f"خطای داخلی هنگام تأیید پرداخت: {exc}"})


def _after_callback(request, order):
    if request.user.is_authenticated and request.user.id == order.user_id:
        request.session["cart"] = {}
        request.session.modified = True
        return redirect("order_detail", order_id=order.id)
    return redirect(f"{reverse('login')}?next={reverse('order_detail', args=[order.id])}")
