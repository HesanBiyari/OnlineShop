"""Zero-total orders must use the same financial and fulfilment path."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from store.models import (
    Coupon,
    CouponRedemption,
    DigitalCode,
    LoyaltyTransaction,
    Notification,
    Order,
    Payment,
)
from store.services.orders import fulfill_paid_order

from .helpers import digital_code, make_order, make_product, make_user


class ZeroTotalOrderTests(TestCase):
    def setUp(self):
        self.user = make_user("09120000701")
        self.product = make_product(name="Free Card", price=100_000, stock=1)
        self.client.force_login(self.user)

    def _zero_order(self, *, redemption_amount=100_000, coupon=None):
        order, item = make_order(
            self.user,
            self.product,
            unit_price=100_000,
            total_amount=0,
            payment_status=Payment.STATUS_CREATED,
            authority=None,
        )
        item.total_price = Decimal("100000")
        item.save(update_fields=["total_price"])
        if coupon is None:
            coupon = Coupon.objects.create(
                code="FULL100",
                kind=Coupon.KIND_PERCENT,
                value=100,
                used_count=1,
            )
        CouponRedemption.objects.create(
            coupon=coupon,
            order=order,
            user=self.user,
            amount=redemption_amount,
        )
        return order, coupon

    def _post_payment(self, order):
        return self.client.post(reverse("payment", args=[order.pk]))

    def test_zero_order_completes_without_gateway_and_fulfils_everything(self):
        order, coupon = self._zero_order()
        code = digital_code(self.product, "FREE-1")

        response = self._post_payment(order)

        self.assertRedirects(response, reverse("order_detail", args=[order.pk]))
        order.refresh_from_db()
        payment = Payment.objects.get(order=order)
        self.product.refresh_from_db()
        code.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertEqual(payment.status, Payment.STATUS_PAID)
        self.assertEqual(payment.amount, Decimal("0"))
        self.assertEqual(order.payment_ref, f"FREE-{order.pk}")
        self.assertEqual(self.product.stock, 0)
        self.assertTrue(code.is_used)
        self.assertTrue(CouponRedemption.objects.filter(order=order).exists())
        self.assertEqual(coupon.used_count, 1)
        self.assertEqual(
            LoyaltyTransaction.objects.filter(order=order, reason="خرید").count(), 1
        )
        self.assertEqual(
            Notification.objects.filter(user=self.user, title="پرداخت موفق").count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                user=self.user, title="سفارش تکمیل شد"
            ).count(),
            1,
        )

    def test_zero_order_with_insufficient_stock_stays_paid_processing(self):
        self.product.stock = 0
        self.product.save(update_fields=["stock"])
        order, _ = self._zero_order()
        code = digital_code(self.product, "FREE-2")

        response = self._post_payment(order)

        self.assertRedirects(response, reverse("order_detail", args=[order.pk]))
        order.refresh_from_db()
        code.refresh_from_db()
        self.assertEqual(Payment.objects.get(order=order).status, Payment.STATUS_PAID)
        self.assertEqual(order.status, Order.STATUS_PROCESSING)
        self.assertIsNone(order.stock_consumed_at)
        self.assertFalse(code.is_used)
        self.assertEqual(
            Notification.objects.filter(user=self.user, title="پرداخت موفق").count(),
            1,
        )
        self.assertFalse(
            Notification.objects.filter(
                user=self.user, title="سفارش تکمیل شد"
            ).exists()
        )

        self.product.stock = 1
        self.product.save(update_fields=["stock"])
        result = fulfill_paid_order(order)
        self.assertTrue(result.completed)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)

    def test_zero_order_with_mismatched_redemption_is_canceled_and_released(self):
        order, coupon = self._zero_order(redemption_amount=50_000)

        response = self._post_payment(order)

        self.assertRedirects(response, reverse("checkout"), target_status_code=302)
        order.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELED)
        self.assertEqual(
            Payment.objects.get(order=order).status, Payment.STATUS_CANCELED
        )
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())
        self.assertEqual(coupon.used_count, 0)

    def test_zero_order_with_expired_coupon_is_canceled_and_released(self):
        coupon = Coupon.objects.create(
            code="EXPIRED",
            kind=Coupon.KIND_PERCENT,
            value=100,
            used_count=1,
            ends_at=timezone.now() - timedelta(days=1),
        )
        order, _ = self._zero_order(coupon=coupon)

        response = self._post_payment(order)

        self.assertRedirects(response, reverse("checkout"), target_status_code=302)
        order.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELED)
        self.assertEqual(coupon.used_count, 0)
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())

    def test_zero_order_with_tampered_payment_amount_is_canceled(self):
        order, coupon = self._zero_order()
        Payment.objects.filter(order=order).update(amount=Decimal("1000"))

        response = self._post_payment(order)

        self.assertRedirects(response, reverse("checkout"), target_status_code=302)
        order.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELED)
        self.assertEqual(coupon.used_count, 0)
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())

    def test_second_zero_order_request_does_not_duplicate_fulfilment(self):
        order, _ = self._zero_order()
        digital_code(self.product, "FREE-3")
        self._post_payment(order)

        response = self._post_payment(order)

        self.assertRedirects(response, reverse("order_detail", args=[order.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertEqual(order.items.first().digital_codes.count(), 1)
        self.assertEqual(
            LoyaltyTransaction.objects.filter(order=order, reason="خرید").count(), 1
        )
