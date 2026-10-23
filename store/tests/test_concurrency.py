"""Real-database concurrency tests.

These are intentionally skipped on SQLite. SQLite's locking model is not the
production model and cannot prove MariaDB row-lock behaviour.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from store.models import Coupon, CouponRedemption, DigitalCode, Order, Payment
from store.services.orders import fulfill_paid_order
from store.services.payments import process_callback, start_payment
from store.services.promotions import release_coupon_for_order

from .helpers import FakeGateway, digital_code, make_order, make_product, make_user

MYSQL_ONLY = skipUnless(
    connection.vendor == "mysql", "MariaDB/MySQL-specific concurrency test"
)


class SlowGateway(FakeGateway):
    def __init__(self, delay=0.25, **kwargs):
        super().__init__(**kwargs)
        self.delay = delay

    def create_payment(self, **kwargs):
        time.sleep(self.delay)
        return super().create_payment(**kwargs)

    def verify_payment(self, *, amount_toman, authority):
        time.sleep(self.delay)
        return super().verify_payment(
            amount_toman=amount_toman, authority=authority
        )


@MYSQL_ONLY
class PaymentConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = make_user("09120001201")
        self.product = make_product(price=100_000, stock=1)

    def _two_threads(self, function):
        barrier = threading.Barrier(2)

        def runner():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return function()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return [future.result(timeout=20) for future in (pool.submit(runner), pool.submit(runner))]

    def test_two_initiations_create_only_one_authority(self):
        order, _ = make_order(
            self.user,
            self.product,
            payment_status=Payment.STATUS_CREATED,
            authority=None,
        )
        gateway = SlowGateway()

        from unittest.mock import patch

        with patch("store.services.payments.get_gateway", return_value=gateway):
            results = self._two_threads(
                lambda: start_payment(order, callback_url="https://example.test/cb")
            )

        self.assertEqual(len(gateway.create_calls), 1)
        self.assertEqual(sum(1 for result in results if result.ok), 1)
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.status, Payment.STATUS_REDIRECTED)
        self.assertEqual(payment.authority, "NEW-AUTHORITY")

    def test_two_callbacks_deliver_stock_and_code_once(self):
        order, _ = make_order(
            self.user,
            self.product,
            payment_status=Payment.STATUS_REDIRECTED,
            authority="AUTH-CC",
        )
        code = digital_code(self.product, "CONCURRENT-CODE")
        gateway = SlowGateway()

        from unittest.mock import patch

        with patch("store.services.payments.get_gateway", return_value=gateway):
            results = self._two_threads(
                lambda: process_callback(order.pk, "AUTH-CC", "OK")
            )

        order.refresh_from_db()
        self.product.refresh_from_db()
        code.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertEqual(Payment.objects.get(order=order).status, Payment.STATUS_PAID)
        self.assertEqual(self.product.stock, 0)
        self.assertTrue(code.is_used)
        self.assertEqual(order.items.first().digital_codes.count(), 1)
        self.assertEqual(
            sum(1 for result in results if result.success), 2
        )


@MYSQL_ONLY
class FulfilmentConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = make_user("09120001202")
        self.product = make_product(price=100_000, stock=1)

    def _paid_order(self):
        order, item = make_order(
            self.user,
            self.product,
            payment_status=Payment.STATUS_PAID,
            authority="AUTH-FC",
        )
        order.paid_at = timezone.now()
        order.save(update_fields=["paid_at"])
        Payment.objects.filter(order=order).update(paid_at=order.paid_at)
        return order, item

    def test_two_cron_workers_consume_stock_once(self):
        order, _ = self._paid_order()
        code = digital_code(self.product, "CONCURRENT-FULFIL")
        barrier = threading.Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return fulfill_paid_order(order)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                future.result(timeout=20)
                for future in (pool.submit(worker), pool.submit(worker))
            ]

        self.product.refresh_from_db()
        code.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertTrue(code.is_used)
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertTrue(all(result.completed for result in results))


@MYSQL_ONLY
class CouponConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = make_user("09120001203")
        self.product = make_product(price=100_000, stock=1)

    def test_two_release_workers_decrement_once(self):
        order, _ = make_order(
            self.user,
            self.product,
            status=Order.STATUS_PENDING,
            payment_status=Payment.STATUS_FAILED,
            authority="AUTH-CR",
        )
        coupon = Coupon.objects.create(
            code="CONCURRENT-RELEASE",
            kind=Coupon.KIND_PERCENT,
            value=10,
            used_count=1,
        )
        CouponRedemption.objects.create(
            coupon=coupon, order=order, user=self.user, amount=10_000
        )
        barrier = threading.Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return release_coupon_for_order(order)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                future.result(timeout=20)
                for future in (pool.submit(worker), pool.submit(worker))
            ]

        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        self.assertEqual(sum(1 for result in results if result), 1)
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())
