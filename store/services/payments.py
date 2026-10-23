"""Payment orchestration.

Guarantees:

* the browser never decides the amount;
* gateway network calls happen outside database transactions;
* a callback must carry the authority issued for that order;
* repeated callbacks cannot deduct stock or deliver codes twice;
* a paid order is never downgraded by a duplicate callback;
* concurrent initiation requests cannot create several live authorities;
* an inconclusive verification is left in ``verifying`` for reconciliation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from store.models import Order, Payment

from .gateway import GatewayResult, get_gateway
from .orders import (
    FulfillmentResult,
    fulfill_paid_order,
    release_expired_pending_orders,
)
from .promotions import release_coupon_for_order

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
    free_order: bool = False
    in_progress: bool = False


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


def _reuse_redirect(payment: Payment, amount: Decimal, reuse_seconds: int) -> str:
    if (
        payment.status == Payment.STATUS_REDIRECTED
        and payment.authority
        and payment.amount == amount
        and (timezone.now() - payment.updated_at).total_seconds() < reuse_seconds
    ):
        try:
            gateway = get_gateway()
        except Exception:
            logger.exception("Payment gateway is misconfigured")
            return ""
        return gateway.start_url + payment.authority
    return ""


def start_payment(order: Order, callback_url: str | None = None) -> StartResult:
    """Create or claim one gateway authority and return the redirect URL.

    The ``initiating`` state is written and committed before the network call.
    A second concurrent request observes it and returns without creating another
    authority. If the first process dies, the stale timeout allows a retry.
    """

    reuse_seconds = int(getattr(settings, "PAYMENT_REDIRECT_REUSE_SECONDS", 1800))
    initiating_stale = int(
        getattr(settings, "PAYMENT_INITIATING_STALE_SECONDS", 120)
    )

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.status != Order.STATUS_PENDING:
            return StartResult(
                False,
                message="این سفارش در وضعیت قابل پرداخت نیست.",
                already_paid=locked_order.is_paid,
            )
        if Decimal(locked_order.total_amount) <= Decimal("0"):
            return StartResult(
                False,
                message="این سفارش مبلغی برای پرداخت درگاه ندارد.",
                free_order=True,
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

        if payment.status == Payment.STATUS_PAID:
            return StartResult(
                False,
                message="این سفارش قبلاً پرداخت شده است.",
                already_paid=True,
            )

        redirect_url = _reuse_redirect(
            payment, locked_order.total_amount, reuse_seconds
        )
        if redirect_url:
            return StartResult(True, redirect_url=redirect_url)

        age_seconds = (timezone.now() - payment.updated_at).total_seconds()
        if payment.status == Payment.STATUS_INITIATING:
            if age_seconds < initiating_stale:
                return StartResult(
                    False,
                    message="ایجاد تراکنش در حال انجام است. لطفاً چند لحظه بعد دوباره تلاش کنید.",
                    in_progress=True,
                )
        if payment.status == Payment.STATUS_VERIFYING:
            return StartResult(
                False,
                message=(
                    "پرداخت این سفارش در حال تأیید است. برای جلوگیری از پرداخت "
                    "دوباره، لطفاً بعداً وضعیت سفارش را بررسی کنید."
                ),
                in_progress=True,
            )

        amount = Decimal(locked_order.total_amount)
        payment.amount = amount
        payment.currency = _currency()
        payment.gateway = _gateway_name()
        payment.status = Payment.STATUS_INITIATING
        # Clearing the previous authority makes a late callback for the old
        # attempt fail closed instead of being treated as the current attempt.
        payment.authority = None
        payment.reference_id = ""
        payment.gateway_code = ""
        payment.gateway_message = ""
        payment.save(
            update_fields=[
                "amount",
                "currency",
                "gateway",
                "status",
                "authority",
                "reference_id",
                "gateway_code",
                "gateway_message",
                "updated_at",
            ]
        )

    # Network call: deliberately outside the transaction above.
    try:
        gateway = get_gateway()
        result = gateway.create_payment(
            amount_toman=amount,
            callback_url=callback_url or _callback_url(locked_order),
            description=f"پرداخت سفارش #{locked_order.id}",
            mobile=locked_order.phone,
            email=locked_order.email,
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
            return StartResult(
                False,
                message="وضعیت سفارش تغییر کرد.",
                already_paid=locked_order.is_paid,
            )
        if payment.status != Payment.STATUS_INITIATING:
            # Another process completed the attempt while this network call was
            # in flight. Reuse only a genuinely redirectable authority.
            redirect_url = _reuse_redirect(
                payment, locked_order.total_amount, reuse_seconds
            )
            if redirect_url:
                return StartResult(True, redirect_url=redirect_url)
            return StartResult(
                False,
                message="وضعیت تراکنش تغییر کرد. لطفاً دوباره تلاش کنید.",
            )

        if result.ok and result.authority:
            payment.authority = result.authority
            payment.status = Payment.STATUS_REDIRECTED
            payment.gateway_code = result.code
            payment.gateway_message = (result.message or "")[:500]
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
        return StartResult(False, message=result.message)


def _callback_url(order: Order) -> str:
    from django.urls import reverse

    path = reverse("payment_callback", args=[order.id])
    base = str(getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if base:
        return f"{base}{path}"
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


def _amount_mismatch(order: Order, payment: Payment) -> bool:
    return Decimal(payment.amount) != Decimal(order.total_amount)


def process_callback(order_id: int, authority: str, gateway_status: str) -> CallbackOutcome:
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return CallbackOutcome(OUTCOME_INVALID, order=None, message="سفارش پیدا نشد.")

    authority = (authority or "").strip()
    gateway_status = (gateway_status or "").strip().upper()

    payment = Payment.objects.filter(order=order).first()
    if payment is None:
        return _invalid(order, "تراکنش برای این سفارش ثبت نشده است.")
    if not authority:
        return _invalid(order, "اطلاعات بازگشت از درگاه ناقص است.")
    if payment.authority != authority:
        return _invalid(order, "تراکنش با این سفارش مطابقت ندارد.")
    if order.is_paid:
        return _already(order)
    if _amount_mismatch(order, payment):
        return _invalid(order, "مبلغ تراکنش با مبلغ سفارش مطابقت ندارد.")
    if order.status == Order.STATUS_CANCELED:
        return _invalid(order, "این سفارش لغو شده است.")

    if gateway_status != "OK":
        return _fail(
            order_id,
            authority,
            gateway_status or "NOK",
            message="پرداخت توسط کاربر تکمیل نشد.",
            canceled=True,
        )

    # Claim the attempt. The network verify happens after this commit, never
    # while holding database locks.
    with transaction.atomic():
        locked_order, locked_payment = _guard_locked(order_id, authority)
        if locked_order.is_paid:
            return _already(locked_order)
        if locked_order.status == Order.STATUS_CANCELED:
            return _invalid(locked_order, "این سفارش لغو شده است.")
        if locked_payment is None or locked_payment.authority != authority:
            return _invalid(locked_order, "تراکنش با این سفارش مطابقت ندارد.")
        if _amount_mismatch(locked_order, locked_payment):
            return _invalid(locked_order, "مبلغ تراکنش با مبلغ سفارش مطابقت ندارد.")
        locked_payment.status = Payment.STATUS_VERIFYING
        locked_payment.save(update_fields=["status", "updated_at"])
        verify_amount = Decimal(locked_order.total_amount)

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
        # Keep the attempt in "verifying" so reconciliation can retry it later.
        # Never release the coupon on an inconclusive result.
        return CallbackOutcome(
            OUTCOME_VERIFY_ERROR,
            order=order,
            message=(
                "ارتباط با درگاه برای تأیید پرداخت برقرار نشد. اگر مبلغ کسر شده، "
                "با پشتیبانی تماس بگیرید."
            ),
        )

    if not result.ok:
        return _fail(
            order_id,
            authority,
            result.code or "VERIFY-FAILED",
            message=result.message or "پرداخت تأیید نشد.",
            canceled=True,
            gateway_message=result.message or "پرداخت تأیید نشد.",
            payment_status=Payment.STATUS_FAILED,
        )

    return _confirm(order_id, authority, result)


def _fail(
    order_id: int,
    authority: str,
    gateway_code: str,
    *,
    message: str,
    canceled: bool,
    gateway_message: str | None = None,
    payment_status: str | None = None,
) -> CallbackOutcome:
    with transaction.atomic():
        order, payment = _guard_locked(order_id, authority)
        if order.is_paid:
            return _already(order)
        if payment is None or payment.authority != authority:
            return _invalid(order, "تراکنش با این سفارش مطابقت ندارد.")

        release_coupon_for_order(order)
        order.status = Order.STATUS_CANCELED
        order.save(update_fields=["status"])
        payment.status = payment_status or (
            Payment.STATUS_CANCELED if canceled else Payment.STATUS_FAILED
        )
        payment.gateway_code = (gateway_code or "")[:30]
        payment.gateway_message = (gateway_message or message or "")[:500]
        payment.save(
            update_fields=[
                "status",
                "gateway_code",
                "gateway_message",
                "updated_at",
            ]
        )
        return CallbackOutcome(
            OUTCOME_CANCELED if canceled else OUTCOME_FAILED,
            order=order,
            message=message or "پرداخت تأیید نشد.",
        )


def _confirm(order_id: int, authority: str, result: GatewayResult) -> CallbackOutcome:
    with transaction.atomic():
        order, payment = _guard_locked(order_id, authority)
        if order.is_paid:
            return _already(order)
        if order.status == Order.STATUS_CANCELED:
            return _invalid(order, "این سفارش لغو شده است.")
        if payment is None or payment.authority != authority:
            return _invalid(order, "تراکنش با این سفارش مطابقت ندارد.")
        if _amount_mismatch(order, payment):
            return _invalid(order, "مبلغ تراکنش با مبلغ سفارش مطابقت ندارد.")

        now = timezone.now()
        reference = (result.reference_id or authority)[:100]
        payment.status = Payment.STATUS_PAID
        payment.reference_id = (result.reference_id or "")[:120]
        payment.gateway_code = (result.code or "")[:30]
        payment.gateway_message = (result.message or "")[:500]
        payment.paid_at = now
        payment.save(
            update_fields=[
                "status",
                "reference_id",
                "gateway_code",
                "gateway_message",
                "paid_at",
                "updated_at",
            ]
        )
        order.status = Order.STATUS_PAID
        order.payment_ref = reference
        order.paid_at = now
        order.save(update_fields=["status", "payment_ref", "paid_at"])

    # Money is now durably recorded. Fulfilment is a separate transaction so a
    # stock or code problem cannot turn a successful payment into a failure.
    try:
        fulfillment = fulfill_paid_order(order)
    except Exception:
        logger.exception(
            "Fulfilment failed after confirmed payment for order %s", order_id
        )
        order.refresh_from_db()
        return CallbackOutcome(
            OUTCOME_PAID,
            order=order,
            message=(
                "پرداخت تأیید شد و سفارش در صف تکمیل است. وضعیت را از صفحه "
                "سفارش پیگیری کنید."
            ),
            success=True,
        )

    order.refresh_from_db()
    return _paid_outcome(order, fulfillment)


def _paid_outcome(order: Order, fulfillment: FulfillmentResult) -> CallbackOutcome:
    if fulfillment.completed:
        message = "پرداخت با موفقیت تأیید شد و سفارش تکمیل شد."
    elif not fulfillment.stock_consumed:
        message = "پرداخت تأیید شد و سفارش برای تکمیل موجودی در حال پردازش است."
    else:
        message = "پرداخت تأیید شد و تحویل کد در حال انجام است."
    return CallbackOutcome(
        OUTCOME_PAID,
        order=order,
        message=message,
        success=True,
    )


def reconcile_verifying_payments() -> int:
    """Re-verify stale ``verifying`` attempts without creating a new authority."""

    stale_seconds = int(
        getattr(settings, "PAYMENT_VERIFYING_STALE_SECONDS", 300)
    )
    cutoff = timezone.now() - timedelta(seconds=max(30, stale_seconds))
    rows = list(
        Payment.objects.filter(
            status=Payment.STATUS_VERIFYING,
            updated_at__lt=cutoff,
            authority__isnull=False,
        ).values_list("order_id", "authority")[:100]
    )

    processed = 0
    for order_id, authority in rows:
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(pk=order_id).first()
            payment = (
                Payment.objects.select_for_update()
                .filter(order_id=order_id)
                .first()
            )
            if (
                order is None
                or payment is None
                or payment.status != Payment.STATUS_VERIFYING
                or payment.authority != authority
                or payment.updated_at >= cutoff
                or order.status != Order.STATUS_PENDING
            ):
                continue
            # Reset the stale timer while the network call is in flight so two
            # cron processes do not verify the same attempt simultaneously.
            payment.save(update_fields=["updated_at"])
            amount = Decimal(order.total_amount)

        try:
            result = get_gateway().verify_payment(
                amount_toman=amount, authority=authority
            )
        except Exception:
            logger.exception(
                "Payment reconciliation crashed for order %s", order_id
            )
            continue
        if not result.ok and result.code == "NETWORK":
            continue
        if result.ok:
            _confirm(order_id, authority, result)
        else:
            _fail(
                order_id,
                authority,
                result.code or "VERIFY-FAILED",
                message=result.message or "پرداخت تأیید نشد.",
                canceled=True,
                payment_status=Payment.STATUS_FAILED,
            )
        processed += 1
    return processed


__all__ = [
    "CallbackOutcome",
    "OUTCOME_ALREADY_PAID",
    "OUTCOME_CANCELED",
    "OUTCOME_FAILED",
    "OUTCOME_INVALID",
    "OUTCOME_PAID",
    "OUTCOME_VERIFY_ERROR",
    "StartResult",
    "ensure_payment",
    "process_callback",
    "reconcile_verifying_payments",
    "release_expired_pending_orders",
    "start_payment",
]
