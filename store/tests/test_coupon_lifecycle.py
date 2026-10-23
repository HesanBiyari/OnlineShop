"""Coupon reservation release and abandoned-order expiry."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from store.models import Coupon, CouponRedemption, Order, Payment
from store.services.orders import release_expired_pending_orders
from store.services.promotions import release_coupon_for_order, reserve_coupon

from .helpers import make_order, make_product, make_user


class CouponReleaseTests(TestCase):
    def setUp(self):
        self.user = make_user("09120001101")
        self.product = make_product(price=100_000, stock=5)

    def _order_with_coupon(self, *, status=Order.STATUS_PENDING, payment_status=None):
        order, _ = make_order(
            self.user,
            self.product,
            status=status,
            payment_status=payment_status or Payment.STATUS_CREATED,
            authority=None,
        )
        coupon = Coupon.objects.create(
            code="RELEASE10", kind=Coupon.KIND_PERCENT, value=10, used_count=1
        )
        CouponRedemption.objects.create(
            coupon=coupon, order=order, user=self.user, amount=10_000
        )
        return order, coupon

    def test_release_is_idempotent_and_decrements_only_once(self):
        order, coupon = self._order_with_coupon()
        self.assertTrue(release_coupon_for_order(order))
        self.assertFalse(release_coupon_for_order(order))
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())

    def test_paid_order_never_releases_its_coupon(self):
        order, coupon = self._order_with_coupon(
            status=Order.STATUS_PAID, payment_status=Payment.STATUS_PAID
        )
        self.assertFalse(release_coupon_for_order(order))
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assertTrue(CouponRedemption.objects.filter(order=order).exists())

    def test_coupon_usage_limit_is_enforced_before_reservation(self):
        coupon = Coupon.objects.create(
            code="LIMIT1",
            kind=Coupon.KIND_FIXED,
            value=10_000,
            usage_limit=1,
            used_count=1,
        )
        found, discount, error = reserve_coupon(
            self.user, coupon.code, Decimal("100000")
        )
        self.assertIsNone(found)
        self.assertEqual(discount, Decimal("0"))
        self.assertIn("معتبر", error)


class ExpiredOrderTests(TestCase):
    def setUp(self):
        self.user = make_user("09120001102")
        self.product = make_product(price=100_000, stock=5)

    def _old_order(self, *, payment_status):
        order, _ = make_order(
            self.user,
            self.product,
            status=Order.STATUS_PENDING,
            payment_status=payment_status,
            authority=None if payment_status == Payment.STATUS_CREATED else "AUTH-E",
        )
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(days=3)
        )
        coupon = Coupon.objects.create(
            code=f"EXPIRE-{order.pk}",
            kind=Coupon.KIND_PERCENT,
            value=11,
            used_count=1,
        )
        CouponRedemption.objects.create(
            coupon=coupon, order=order, user=self.user, amount=11_000
        )
        return order, coupon

    @override_settings(ORDER_PENDING_EXPIRY_HOURS=1)
    def test_abandoned_created_payment_is_canceled_and_released(self):
        order, coupon = self._old_order(payment_status=Payment.STATUS_CREATED)
        self.assertEqual(release_expired_pending_orders(), 1)
        order.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELED)
        self.assertEqual(
            Payment.objects.get(order=order).status, Payment.STATUS_CANCELED
        )
        self.assertEqual(coupon.used_count, 0)
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())

        # Second cron run must not decrement or change anything again.
        self.assertEqual(release_expired_pending_orders(), 0)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)

    @override_settings(ORDER_PENDING_EXPIRY_HOURS=1)
    def test_stale_initiating_payment_is_expired(self):
        order, coupon = self._old_order(payment_status=Payment.STATUS_INITIATING)
        self.assertEqual(release_expired_pending_orders(), 1)
        order.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELED)
        self.assertEqual(coupon.used_count, 0)

    @override_settings(ORDER_PENDING_EXPIRY_HOURS=1)
    def test_pending_order_without_payment_row_is_expired(self):
        order, coupon = self._old_order(payment_status=Payment.STATUS_CREATED)
        Payment.objects.filter(order=order).delete()
        self.assertEqual(release_expired_pending_orders(), 1)
        order.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELED)
        self.assertEqual(coupon.used_count, 0)

    @override_settings(ORDER_PENDING_EXPIRY_HOURS=1)
    def test_redirected_payment_is_not_expired_while_customer_is_at_gateway(self):
        order, coupon = self._old_order(payment_status=Payment.STATUS_REDIRECTED)
        self.assertEqual(release_expired_pending_orders(), 0)
        order.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)
        self.assertEqual(coupon.used_count, 1)

    @override_settings(ORDER_PENDING_EXPIRY_HOURS=1)
    def test_verifying_payment_is_left_for_reconciliation(self):
        order, coupon = self._old_order(payment_status=Payment.STATUS_VERIFYING)
        self.assertEqual(release_expired_pending_orders(), 0)
        order.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)
        self.assertEqual(coupon.used_count, 1)

    @override_settings(ORDER_PENDING_EXPIRY_HOURS=1)
    def test_paid_order_is_never_expired(self):
        order, coupon = self._old_order(payment_status=Payment.STATUS_PAID)
        order.status = Order.STATUS_PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at"])
        self.assertEqual(release_expired_pending_orders(), 0)
        order.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PAID)
        self.assertEqual(coupon.used_count, 1)
