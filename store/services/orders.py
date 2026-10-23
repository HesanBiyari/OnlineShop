"""Order state machine and durable fulfilment steps.

The payment layer records that money was received. This module owns everything
after that point: stock consumption, digital-code delivery, completion and the
retry of notifications. Every step is idempotent and protected by row locks so
a cron run and a gateway callback cannot apply it twice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from store.models import (
    CouponRedemption,
    Order,
    Payment,
    Product,
    ProductVariant,
)

from .digital import deliver_digital_codes
from .promotions import finalize_advanced_order, notify, release_coupon_for_order

logger = logging.getLogger(__name__)

# Transitions a staff member may apply from the panel or Django admin. Internal
# payment/fulfilment code does not use this table: it follows the payment state
# explicitly and never lets a human mark an unpaid order as paid.
STAFF_TRANSITIONS: dict[str, set[str]] = {
    Order.STATUS_PENDING: {Order.STATUS_CANCELED},
    Order.STATUS_PAID: {Order.STATUS_PROCESSING, Order.STATUS_COMPLETED},
    Order.STATUS_PROCESSING: {Order.STATUS_COMPLETED},
    Order.STATUS_COMPLETED: set(),
    Order.STATUS_CANCELED: set(),
}


class ZeroOrderError(Exception):
    """A zero-total order failed final server-side validation."""


@dataclass(frozen=True)
class FulfillmentResult:
    stock_consumed: bool
    delivered: bool
    completed: bool
    notified: bool


def validate_staff_transition(order: Order, new_status: str) -> None:
    """Raise ``ValidationError`` unless this is an allowed staff transition."""

    valid_statuses = {value for value, _label in Order.STATUS_CHOICES}
    if new_status not in valid_statuses:
        raise ValidationError("وضعیت انتخاب‌شده معتبر نیست.")
    if new_status == order.status:
        return

    allowed = STAFF_TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        if not order.is_paid and new_status in Order.PAID_STATUSES:
            raise ValidationError(
                "تغییر وضعیت به پرداخت‌شده فقط از طریق تأیید درگاه انجام می‌شود."
            )
        if order.is_paid and new_status == Order.STATUS_CANCELED:
            raise ValidationError(
                "لغو سفارش پرداخت‌شده نیازمند جریان بازپرداخت است و از این مسیر مجاز نیست."
            )
        if order.is_paid and new_status == Order.STATUS_PENDING:
            raise ValidationError(
                "سفارش پرداخت‌شده را نمی‌توان به وضعیت پرداخت‌نشده برگرداند."
            )
        raise ValidationError("این انتقال وضعیت برای سفارش مجاز نیست.")
    if new_status == Order.STATUS_COMPLETED and order.stock_consumed_at is None:
        raise ValidationError(
            "تکمیل دستی سفارش پیش از مصرف موجودی و تحویل کد مجاز نیست؛ "
            "ابتدا موجودی/کد را تأمین کنید و فرایند پردازش را اجرا کنید."
        )
    if new_status == Order.STATUS_CANCELED and order.status == Order.STATUS_PENDING:
        payment = Payment.objects.filter(order=order).first() if order.pk else None
        if payment and payment.status in {
            Payment.STATUS_REDIRECTED,
            Payment.STATUS_VERIFYING,
        }:
            raise ValidationError(
                "این سفارش درگاه فعال یا در حال تأیید دارد و لغو دستی آن ممکن است "
                "باعث از دست رفتن پرداخت شود؛ ابتدا وضعیت درگاه را بررسی کنید."
            )


def _safe_finalize_advanced(order: Order) -> None:
    """Award loyalty and send the payment notification once, without rolling
    back a confirmed payment if a side effect fails."""

    try:
        with transaction.atomic():
            finalize_advanced_order(order)
    except Exception:
        logger.exception(
            "Loyalty/payment notification failed for order %s", order.pk
        )


def _notify_completion(order: Order) -> bool:
    if order.fulfillment_notified_at is not None:
        return False
    try:
        with transaction.atomic():
            notify(
                order.user,
                "سفارش تکمیل شد",
                f"سفارش #{order.pk} تکمیل شد و کدهای تحویل‌شده در صفحه سفارش قابل مشاهده است.",
            )
            order.fulfillment_notified_at = timezone.now()
            order.save(update_fields=["fulfillment_notified_at"])
        return True
    except Exception:
        logger.exception(
            "Delivery notification failed for order %s; cron will retry", order.pk
        )
        return False


def _locked_stock_holders(items):
    product_ids = {item.product_id for item in items}
    variant_ids = {item.variant_id for item in items if item.variant_id}
    products = {
        row.pk: row
        for row in Product.objects.select_for_update()
        .filter(pk__in=product_ids)
        .order_by("pk")
    }
    variants = {
        row.pk: row
        for row in ProductVariant.objects.select_for_update()
        .filter(pk__in=variant_ids)
        .order_by("pk")
    }
    return products, variants


def fulfill_paid_order(order: Order) -> FulfillmentResult:
    """Consume stock and deliver codes for a paid order, exactly once.

    A paid order with insufficient stock stays ``processing``. The stock flag
    remains NULL so a later cron run retries the stock step. A paid order whose
    stock was consumed but whose digital codes are missing stays processing and
    only retries the delivery step.
    """

    with transaction.atomic():
        locked = (
            Order.objects.select_for_update()
            .select_related("user")
            .get(pk=order.pk)
        )
        if locked.status == Order.STATUS_CANCELED:
            return FulfillmentResult(False, False, False, False)

        payment = Payment.objects.select_for_update().filter(order=locked).first()
        if payment is None or payment.status != Payment.STATUS_PAID:
            raise ValidationError("سفارش بدون پرداخت تأییدشده قابل تکمیل نیست.")

        # A manually completed order must not be retroactively delivered by a
        # notification retry. Legacy completed rows are backfilled by migration.
        if locked.status == Order.STATUS_COMPLETED:
            _safe_finalize_advanced(locked)
            notified = _notify_completion(locked)
            return FulfillmentResult(
                stock_consumed=locked.stock_consumed_at is not None,
                delivered=True,
                completed=True,
                notified=notified,
            )

        items = list(
            locked.items.select_related("product", "variant").order_by("id")
        )
        if not items:
            locked.status = Order.STATUS_PROCESSING
            locked.save(update_fields=["status"])
            _safe_finalize_advanced(locked)
            return FulfillmentResult(False, False, False, False)

        stock_consumed = locked.stock_consumed_at is not None
        if not stock_consumed:
            products, variants = _locked_stock_holders(items)
            # Two lines may reference the same product/variant. Check and
            # decrement the aggregate requirement, otherwise each line can pass
            # individually while the combined quantity drives stock negative.
            product_needed: dict[int, int] = {}
            variant_needed: dict[int, int] = {}
            for item in items:
                target = variant_needed if item.variant_id else product_needed
                key = item.variant_id or item.product_id
                target[key] = target.get(key, 0) + item.quantity

            stock_ok = True
            for variant_id, needed in variant_needed.items():
                variant = variants.get(variant_id)
                if (
                    variant is None
                    or not variant.is_active
                    or variant.stock < needed
                ):
                    stock_ok = False
            for product_id, needed in product_needed.items():
                product = products.get(product_id)
                if product is None or product.stock < needed:
                    stock_ok = False

            if not stock_ok:
                # Money is already received. Keep the order in the queue and
                # still record loyalty/notification independently of stock.
                if locked.status != Order.STATUS_PROCESSING:
                    locked.status = Order.STATUS_PROCESSING
                    locked.save(update_fields=["status"])
                _safe_finalize_advanced(locked)
                return FulfillmentResult(False, False, False, False)

            now = timezone.now()
            for variant_id, needed in variant_needed.items():
                holder = variants[variant_id]
                holder.stock -= needed
                holder.save(update_fields=["stock"])
            for product_id, needed in product_needed.items():
                holder = products[product_id]
                holder.stock -= needed
                holder.save(update_fields=["stock"])
            locked.stock_consumed_at = now
            locked.save(update_fields=["stock_consumed_at"])

        delivered = deliver_digital_codes(locked)
        if delivered:
            locked.status = Order.STATUS_COMPLETED
            locked.save(update_fields=["status"])
            completed = True
        else:
            if locked.status != Order.STATUS_PROCESSING:
                locked.status = Order.STATUS_PROCESSING
                locked.save(update_fields=["status"])
            completed = False

        _safe_finalize_advanced(locked)
        notified = _notify_completion(locked) if completed else False

        return FulfillmentResult(
            stock_consumed=True,
            delivered=delivered,
            completed=completed,
            notified=notified,
        )


def _cancel_locked(
    order: Order,
    payment: Payment | None,
    *,
    reason: str,
    payment_status: str = Payment.STATUS_CANCELED,
) -> bool:
    if order.is_paid or (
        payment is not None and payment.status == Payment.STATUS_PAID
    ):
        # A paid payment must never be canceled just because an inconsistent
        # order status says pending; surface it for reconciliation instead.
        return False
    release_coupon_for_order(order)
    if payment is not None and payment.status != Payment.STATUS_PAID:
        payment.status = payment_status
        payment.gateway_message = (reason or "")[:500]
        payment.save(update_fields=["status", "gateway_message", "updated_at"])
    order.status = Order.STATUS_CANCELED
    order.save(update_fields=["status"])
    return True


def cancel_pending_order(
    order_id: int,
    *,
    reason: str = "سفارش لغو شد.",
    payment_status: str = Payment.STATUS_CANCELED,
) -> bool:
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None:
            return False
        payment = Payment.objects.select_for_update().filter(order=order).first()
        return _cancel_locked(
            order, payment, reason=reason, payment_status=payment_status
        )


def release_expired_pending_orders() -> int:
    """Cancel abandoned unpaid orders and release their coupon reservations.

    Orders with a live ``redirected`` or ``verifying`` payment are intentionally
    left alone: cancelling them while the customer is at the gateway could turn
    a real captured payment into a rejected callback. Those attempts are
    reconciled by the payment command instead.
    """

    hours = int(getattr(settings, "ORDER_PENDING_EXPIRY_HOURS", 24))
    cutoff = timezone.now() - timedelta(hours=max(1, hours))
    order_ids = list(
        Order.objects.filter(
            Q(payment__isnull=True)
            | Q(
                payment__status__in=(
                    Payment.STATUS_CREATED,
                    Payment.STATUS_INITIATING,
                    Payment.STATUS_FAILED,
                    Payment.STATUS_CANCELED,
                )
            ),
            status=Order.STATUS_PENDING,
            created_at__lt=cutoff,
        ).values_list("id", flat=True)
    )

    released = 0
    for order_id in order_ids:
        ok = cancel_pending_order(
            order_id,
            reason="مهلت پرداخت سفارش به پایان رسید.",
            payment_status=Payment.STATUS_CANCELED,
        )
        if ok:
            released += 1
    return released


def complete_zero_total_order(order: Order) -> FulfillmentResult:
    """Complete a fully discounted order without contacting the gateway.

    All values are re-checked on the server: the saved line snapshots, the
    coupon reservation, the payment amount and the zero total. A mismatch cancels
    the order and releases the coupon rather than giving away goods.
    """

    with transaction.atomic():
        locked = (
            Order.objects.select_for_update()
            .select_related("user")
            .get(pk=order.pk)
        )
        if locked.is_paid:
            return FulfillmentResult(True, True, True, False)
        if locked.status != Order.STATUS_PENDING:
            raise ZeroOrderError("این سفارش در وضعیت قابل تکمیل نیست.")
        if Decimal(locked.total_amount) != Decimal("0"):
            raise ZeroOrderError("مبلغ سفارش صفر نیست و باید از درگاه پرداخت شود.")

        payment = Payment.objects.select_for_update().filter(order=locked).first()
        error_message = ""
        if payment is None or Decimal(payment.amount) != Decimal("0"):
            _cancel_locked(
                locked,
                payment,
                reason="رکورد پرداخت با مبلغ صفر سفارش مطابقت ندارد.",
                payment_status=Payment.STATUS_CANCELED,
            )
            error_message = (
                "رکورد پرداخت با مبلغ سفارش مطابقت ندارد؛ لطفاً دوباره ثبت سفارش کنید."
            )

        redemption = (
            CouponRedemption.objects.select_for_update()
            .select_related("coupon")
            .filter(order=locked)
            .first()
        )
        if not error_message:
            subtotal = sum(
                (Decimal(item.total_price) for item in locked.items.all()),
                Decimal("0"),
            )
            discount = Decimal(redemption.amount) if redemption else Decimal("0")
            if subtotal - discount != Decimal("0"):
                _cancel_locked(
                    locked,
                    payment,
                    reason="مبلغ سفارش با اقلام و تخفیف رزروشده مطابقت ندارد.",
                    payment_status=Payment.STATUS_CANCELED,
                )
                error_message = (
                    "مبلغ سفارش با اقلام و تخفیف مطابقت ندارد؛ لطفاً دوباره ثبت سفارش کنید."
                )
            elif redemption and not redemption.coupon.reservation_window_is_valid():
                _cancel_locked(
                    locked,
                    payment,
                    reason="کوپن سفارش منقضی یا غیرفعال شده است.",
                    payment_status=Payment.STATUS_CANCELED,
                )
                error_message = (
                    "کد تخفیف دیگر معتبر نیست؛ لطفاً دوباره ثبت سفارش کنید."
                )

        if error_message:
            # Raise only after the atomic block commits the cancellation.
            pass
        else:
            now = timezone.now()
            reference = f"FREE-{locked.pk}"
            payment.status = Payment.STATUS_PAID
            payment.amount = Decimal("0")
            payment.reference_id = reference
            payment.gateway_code = "FREE"
            payment.gateway_message = "تکمیل بدون درگاه (مبلغ صفر)"
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
            locked.status = Order.STATUS_PAID
            locked.paid_at = now
            locked.payment_ref = reference
            locked.save(update_fields=["status", "paid_at", "payment_ref"])

    if error_message:
        raise ZeroOrderError(error_message)

    # Fulfilment has its own transaction and row locks. The payment is already
    # durable, so a stock/code failure leaves a consistent paid/processing order.
    return fulfill_paid_order(locked)
