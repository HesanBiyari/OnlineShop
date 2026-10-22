"""Payment orchestration.

Guarantees:

* the browser never decides the amount;
* gateway network calls happen outside database transactions;
* a callback must carry the authority issued for that order;
* repeated callbacks cannot deduct stock or deliver codes twice;
* a paid order is never downgraded by a duplicate callback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from store.models import Order, Payment, Product, ProductVariant

from .digital import deliver_digital_codes
from .gateway import GatewayResult, get_gateway
from .promotions import finalize_advanced_order, release_coupon_for_order

logger = logging.getLogger(__name__)

OUTCOME_ALREADY_PAID = "already_paid"
OUTCOME_PAID = "paid"
OUTCOME_FAILED = "failed"
OUTCOME_CANCELED = "canceled"
OUTCOME_INVALID = "invalid"
OUTCOME_VERIFY_ERROR = "verify_error"


@dataclass(frozen=True)
class StartResult:
    ok: bool
    redirect_url: str = ""
    message: str = ""
    already_paid: bool = False


@dataclass(frozen=True)
class CallbackOutcome:
    kind: str
    order: Order
    message: str = ""
    success: bool = False


def _currency() -> str:
    return str(getattr(settings, "PAYMENT_CURRENCY", "IRR")).upper()


def _gateway_name() -> str:
    return str(getattr(settings, "PAYMENT_GATEWAY", "zarinpal")).lower()


def ensure_payment(order: Order) -> Payment:
    payment, _ = Payment.objects.get_or_create(
        order=order,
        defaults={
            "amount": order.total_amount,
            "currency": _currency(),
            "gateway": _gateway_name(),
            "status": Payment.STATUS_CREATED,
        },
    )
    return payment


def start_payment(order: Order, callback_url: str | None = None) -> StartResult:
    """Create or reuse a gateway authority and return the redirect URL."""

    reuse_seconds = int(getattr(settings, "PAYMENT_REDIRECT_REUSE_SECONDS", 1800))

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.status != Order.STATUS_PENDING:
            return StartResult(
                False, message="این سفارش در وضعیت قابل پرداخت نیست.", already_paid=True
            )

        payment, _ = Payment.objects.select_for_update().get_or_create(
            order=locked_order,
            defaults={
                "amount": locked_order.total_amount,
                "currency": _currency(),
                "gateway": _gateway_name(),
                "status": Payment.STATUS_CREATED,
            },
        )

        age = timezone.now() - payment.updated_at
        if (
            payment.status == Payment.STATUS_REDIRECTED
            and payment.authority
            and payment.amount == locked_order.total_amount
            and age.total_seconds() < reuse_seconds
        ):
            try:
                gateway = get_gateway()
            except Exception:
                logger.exception("Payment gateway is misconfigured")
            else:
                return StartResult(
                    True, redirect_url=gateway.start_url + payment.authority
                )

        payment.amount = locked_order.total_amount
        payment.currency = _currency()
        payment.gateway = _gateway_name()
        payment.status = Payment.STATUS_CREATED
        payment.gateway_code = ""
        payment.gateway_message = ""
        payment.save(
            update_fields=[
                "amount",
                "currency",
                "gateway",
                "status",
                "gateway_code",
                "gateway_message",
                "updated_at",
            ]
        )

    # Network call: deliberately outside the transaction above.
    try:
        gateway = get_gateway()
        result = gateway.create_payment(
            amount_toman=order.total_amount,
            callback_url=callback_url or _callback_url(order),
            description=f"پرداخت سفارش #{order.id}",
            mobile=order.phone,
            email=order.email,
        )
    except Exception:
        logger.exception("Payment creation failed for order %s", order.id)
        result = GatewayResult(
            False,
            code="APP",
            message="ایجاد تراکنش ممکن نشد. لطفاً دوباره تلاش کنید.",
        )

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.status != Order.STATUS_PENDING:
            return StartResult(False, message="وضعیت سفارش تغییر کرد.", already_paid=True)

        if result.ok and result.authority:
            payment.authority = result.authority
            payment.status = Payment.STATUS_REDIRECTED
            payment.gateway_code = result.code
            payment.gateway_message = result.message[:500]
            payment.amount = locked_order.total_amount
            payment.save(
                update_fields=[
                    "authority",
                    "status",
                    "gateway_code",
                    "gateway_message",
                    "amount",
                    "updated_at",
                ]
            )
            return StartResult(True, redirect_url=result.redirect_url)

        payment.status = Payment.STATUS_FAILED
        payment.gateway_code = result.code
        payment.gateway_message = (result.message or "")[:500]
        payment.save(
            update_fields=[
                "status",
                "gateway_code",
                "gateway_message",
                "updated_at",
            ]
        )
        return StartResult(False, message=result.message)


def _callback_url(order: Order) -> str:
    from django.urls import reverse

    path = reverse("payment_callback", args=[order.id])
    base = str(getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if base:
        return f"{base}{path}"
    # The gateway requires an absolute URL. The configured public domain is
    # preferred; views pass a request-built URL by setting SITE_URL per deploy.
    return f"https://{settings.SITE_DOMAIN}{path}"


def _invalid(order: Order, message: str) -> CallbackOutcome:
    return CallbackOutcome(OUTCOME_INVALID, order=order, message=message)


def _already(order: Order) -> CallbackOutcome:
    return CallbackOutcome(
        OUTCOME_ALREADY_PAID,
        order=order,
        message="این سفارش قبلاً پرداخت شده است.",
        success=True,
    )


def _guard_locked(order_id: int, authority: str):
    order = Order.objects.select_for_update().get(pk=order_id)
    payment = Payment.objects.select_for_update().filter(order=order).first()
    return order, payment


def process_callback(order_id: int, authority: str, gateway_status: str) -> CallbackOutcome:
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return CallbackOutcome(OUTCOME_INVALID, order=None, message="سفارش پیدا نشد.")

    authority = (authority or "").strip()
    gateway_status = (gateway_status or "").strip().upper()

    if order.is_paid:
        return _already(order)

    payment = Payment.objects.filter(order=order).first()
    if payment is None:
        return _invalid(order, "تراکنش برای این سفارش ثبت نشده است.")
    if not authority:
        return _invalid(order, "اطلاعات بازگشت از درگاه ناقص است.")
    if payment.authority != authority:
        return _invalid(order, "تراکنش با این سفارش مطابقت ندارد.")
    if order.status == Order.STATUS_CANCELED:
        return _invalid(order, "این سفارش لغو شده است.")

    if gateway_status != "OK":
        return _cancel(order_id, authority, gateway_status)

    # Claim the attempt. The network verify happens after this commit, never
    # while holding database locks.
    with transaction.atomic():
        locked_order, locked_payment = _guard_locked(order_id, authority)
        if locked_order.is_paid:
            return _already(locked_order)
        if locked_payment is None or locked_payment.authority != authority:
            return _invalid(locked_order, "تراکنش با این سفارش مطابقت ندارد.")
        locked_payment.status = Payment.STATUS_VERIFYING
        locked_payment.save(update_fields=["status", "updated_at"])
        verify_amount = locked_order.total_amount

    try:
        result = get_gateway().verify_payment(
            amount_toman=verify_amount, authority=authority
        )
    except Exception:
        logger.exception("Payment verification crashed for order %s", order_id)
        return CallbackOutcome(
            OUTCOME_VERIFY_ERROR,
            order=order,
            message=(
                "در تأیید پرداخت مشکلی رخ داد. اگر مبلغ از حساب شما کسر شده، "
                "سفارش شما بررسی خواهد شد."
            ),
        )

    if not result.ok and result.code == "NETWORK":
        # Keep the attempt in "verifying" so a retry/reconciliation can verify
        # it later. Never release the coupon on an inconclusive result.
        return CallbackOutcome(
            OUTCOME_VERIFY_ERROR,
            order=order,
            message=(
                "ارتباط با درگاه برای تأیید پرداخت برقرار نشد. اگر مبلغ کسر شده، "
                "با پشتیبانی تماس بگیرید."
            ),
        )

    return _finalize(order_id, authority, result)


def _cancel(order_id: int, authority: str, gateway_status: str) -> CallbackOutcome:
    with transaction.atomic():
        order, payment = _guard_locked(order_id, authority)
        if order.is_paid:
            return _already(order)
        if payment is None or payment.authority != authority:
            return _invalid(order, "تراکنش با این سفارش مطابقت ندارد.")

        release_coupon_for_order(order)
        payment.status = Payment.STATUS_CANCELED
        payment.gateway_code = (gateway_status or "NOK")[:30]
        payment.gateway_message = "پرداخت توسط کاربر تکمیل نشد."
        payment.save(
            update_fields=[
                "status",
                "gateway_code",
                "gateway_message",
                "updated_at",
            ]
        )
        return CallbackOutcome(
            OUTCOME_CANCELED,
            order=order,
            message="پرداخت تکمیل نشد.",
        )


def _finalize(order_id: int, authority: str, result: GatewayResult) -> CallbackOutcome:
    with transaction.atomic():
        order, payment = _guard_locked(order_id, authority)
        if order.is_paid:
            return _already(order)
        if payment is None or payment.authority != authority:
            return _invalid(order, "تراکنش با این سفارش مطابقت ندارد.")

        if not result.ok:
            release_coupon_for_order(order)
            payment.status = Payment.STATUS_FAILED
            payment.gateway_code = (result.code or "")[:30]
            payment.gateway_message = (result.message or "")[:500]
            payment.save(
                update_fields=[
                    "status",
                    "gateway_code",
                    "gateway_message",
                    "updated_at",
                ]
            )
            return CallbackOutcome(
                OUTCOME_FAILED,
                order=order,
                message=result.message or "پرداخت تأیید نشد.",
            )

        now = timezone.now()
        reference = (result.reference_id or authority)[:100]
        payment.status = Payment.STATUS_PAID
        payment.amount = order.total_amount
        payment.reference_id = (result.reference_id or "")[:120]
        payment.gateway_code = (result.code or "")[:30]
        payment.gateway_message = (result.message or "")[:500]
        payment.paid_at = now
        payment.save(
            update_fields=[
                "status",
                "amount",
                "reference_id",
                "gateway_code",
                "gateway_message",
                "paid_at",
                "updated_at",
            ]
        )

        items = list(order.items.select_related("product", "variant").order_by("id"))
        locked_lines: list[tuple[object, object, Decimal, bool]] = []
        stock_ok = True
        for item in items:
            if item.variant_id:
                variant = ProductVariant.objects.select_for_update().get(
                    pk=item.variant_id
                )
                if not variant.is_active or variant.stock < item.quantity:
                    stock_ok = False
                locked_lines.append((variant, item, item.quantity, True))
            else:
                product = Product.objects.select_for_update().get(pk=item.product_id)
                if product.stock < item.quantity:
                    stock_ok = False
                locked_lines.append((product, item, item.quantity, False))

        order.payment_ref = reference
        order.paid_at = now

        if not stock_ok:
            # Money was received but inventory is missing. Keep it in the
            # fulfilment queue; do not consume stock or deliver codes.
            order.status = Order.STATUS_PROCESSING
            order.save(update_fields=["status", "payment_ref", "paid_at"])
            return CallbackOutcome(
                OUTCOME_PAID,
                order=order,
                message=(
                    "پرداخت تأیید شد و سفارش برای تکمیل موجودی در حال پردازش است."
                ),
                success=True,
            )

        for stock_holder, _item, quantity, is_variant in locked_lines:
            stock_holder.stock -= quantity
            stock_holder.save(update_fields=["stock"])

        order.status = Order.STATUS_PAID
        order.save(update_fields=["status", "payment_ref", "paid_at"])

        delivered = deliver_digital_codes(order)
        try:
            # Loyalty/notification failures must not roll back a confirmed
            # payment. A savepoint keeps the payment durable.
            with transaction.atomic():
                finalize_advanced_order(order)
        except Exception:
            logger.exception("Post-payment finalisation failed for order %s", order.id)

        order.status = (
            Order.STATUS_COMPLETED if delivered else Order.STATUS_PROCESSING
        )
        order.save(update_fields=["status"])

        return CallbackOutcome(
            OUTCOME_PAID,
            order=order,
            message=(
                "پرداخت با موفقیت تأیید شد."
                if delivered
                else "پرداخت تأیید شد و سفارش در حال پردازش است."
            ),
            success=True,
        )
