"""Durable fulfilment: stock, codes, loyalty and notifications."""

from __future__ import annotations

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from store.models import (
    DigitalCode,
    LoyaltyTransaction,
    Notification,
    Order,
    OrderItem,
    Payment,
)
from store.services.orders import fulfill_paid_order

from .helpers import digital_code, make_order, make_product, make_user


class FulfilmentTests(TestCase):
    def setUp(self):
        self.user = make_user("09120000601")
        self.product = make_product(name="Digital", price=100_000, stock=5)

    def _paid_order(self, *, quantity=1, status=Order.STATUS_PAID):
        order, item = make_order(
            self.user,
            self.product,
            quantity=quantity,
            status=status,
            payment_status=Payment.STATUS_PAID,
            authority="AUTH-F",
        )
        order.paid_at = timezone.now()
        order.save(update_fields=["paid_at"])
        Payment.objects.filter(order=order).update(paid_at=order.paid_at)
        return order, item

    def test_order_is_fulfilled_once_and_repeated_calls_are_idempotent(self):
        order, item = self._paid_order()
        code = digital_code(self.product, "FULFIL-1")

        first = fulfill_paid_order(order)
        second = fulfill_paid_order(order)

        self.assertTrue(first.completed)
        self.assertTrue(second.completed)
        self.product.refresh_from_db()
        order.refresh_from_db()
        code.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertIsNotNone(order.stock_consumed_at)
        self.assertTrue(code.is_used)
        self.assertEqual(code.order_item_id, item.pk)
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

    def test_process_orders_command_retries_delivery_and_is_idempotent(self):
        order, _ = self._paid_order()
        first = StringIO()
        call_command("process_orders", stdout=first)
        self.assertIn("pending=1", first.getvalue())

        digital_code(self.product, "CRON-1")
        second = StringIO()
        call_command("process_orders", stdout=second)
        self.assertIn("completed=1", second.getvalue())

        third = StringIO()
        call_command("process_orders", stdout=third)
        self.assertIn("Processed=0", third.getvalue())
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertIsNotNone(order.fulfillment_notified_at)

    def test_insufficient_stock_keeps_payment_and_retries_after_restock(self):
        self.product.stock = 0
        self.product.save(update_fields=["stock"])
        order, _ = self._paid_order()
        self.product.refresh_from_db()
        self.product.stock = 0
        self.product.save(update_fields=["stock"])
        code = digital_code(self.product, "FULFIL-2")

        result = fulfill_paid_order(order)

        self.assertFalse(result.completed)
        self.assertFalse(result.stock_consumed)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PROCESSING)
        self.assertEqual(Payment.objects.get(order=order).status, Payment.STATUS_PAID)
        self.assertIsNone(order.stock_consumed_at)
        code.refresh_from_db()
        self.assertFalse(code.is_used)
        self.assertEqual(
            LoyaltyTransaction.objects.filter(order=order, reason="خرید").count(), 1
        )
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
        self.product.refresh_from_db()
        order.refresh_from_db()
        code.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertTrue(code.is_used)
        self.assertEqual(
            Notification.objects.filter(
                user=self.user, title="سفارش تکمیل شد"
            ).count(),
            1,
        )

    def test_missing_codes_retry_without_second_stock_deduction(self):
        order, _ = self._paid_order()

        result = fulfill_paid_order(order)

        self.assertFalse(result.completed)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(order.status, Order.STATUS_PROCESSING)
        self.assertIsNotNone(order.stock_consumed_at)
        self.assertFalse(
            Notification.objects.filter(
                user=self.user, title="سفارش تکمیل شد"
            ).exists()
        )

        digital_code(self.product, "FULFIL-3")
        result = fulfill_paid_order(order)

        self.assertTrue(result.completed)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(order.items.first().digital_codes.count(), 1)
        self.assertEqual(
            Notification.objects.filter(
                user=self.user, title="سفارش تکمیل شد"
            ).count(),
            1,
        )

    def test_stock_is_all_or_nothing_across_order_lines(self):
        second = make_product(name="Second", price=50_000, stock=0)
        order, first_item = self._paid_order()
        second_item = OrderItem.objects.create(
            order=order,
            product=second,
            product_name=second.name,
            quantity=1,
            unit_price=second.price,
            total_price=second.price,
        )
        order.total_amount = Decimal("150000")
        order.save(update_fields=["total_amount"])
        payment = Payment.objects.get(order=order)
        payment.amount = order.total_amount
        payment.save(update_fields=["amount"])
        digital_code(self.product, "LINE-A")
        digital_code(second, "LINE-B")

        result = fulfill_paid_order(order)

        self.assertFalse(result.completed)
        self.product.refresh_from_db()
        second.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(second.stock, 0)
        self.assertEqual(order.status, Order.STATUS_PROCESSING)
        self.assertIsNone(order.stock_consumed_at)
        self.assertFalse(first_item.digital_codes.exists())
        self.assertFalse(second_item.digital_codes.exists())

        second.stock = 1
        second.save(update_fields=["stock"])
        result = fulfill_paid_order(order)

        self.assertTrue(result.completed)
        self.product.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(second.stock, 0)
        self.assertEqual(first_item.digital_codes.count(), 1)
        self.assertEqual(second_item.digital_codes.count(), 1)

    def test_two_lines_for_same_product_check_combined_stock(self):
        self.product.stock = 6
        self.product.save(update_fields=["stock"])
        order, first_item = self._paid_order(quantity=4)
        second_item = OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            quantity=4,
            unit_price=self.product.price,
            total_price=self.product.price * 4,
        )
        order.total_amount = self.product.price * 8
        order.save(update_fields=["total_amount"])
        Payment.objects.filter(order=order).update(amount=order.total_amount)
        for index in range(8):
            digital_code(self.product, f"COMBINED-{index}")

        result = fulfill_paid_order(order)

        self.assertFalse(result.completed)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock, 6)
        self.assertIsNone(order.stock_consumed_at)
        self.assertFalse(first_item.digital_codes.exists())
        self.assertFalse(second_item.digital_codes.exists())

        self.product.stock = 8
        self.product.save(update_fields=["stock"])
        result = fulfill_paid_order(order)

        self.assertTrue(result.completed)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertEqual(first_item.digital_codes.count(), 4)
        self.assertEqual(second_item.digital_codes.count(), 4)

    def test_payment_notification_is_retried_if_side_effect_fails(self):
        order, _ = self._paid_order()
        digital_code(self.product, "FULFIL-4")

        with patch(
            "store.services.promotions.notify", side_effect=RuntimeError("mail down")
        ):
            first = fulfill_paid_order(order)
        self.assertTrue(first.completed)
        self.assertFalse(
            LoyaltyTransaction.objects.filter(order=order, reason="خرید").exists()
        )
        self.assertFalse(
            Notification.objects.filter(user=self.user, title="پرداخت موفق").exists()
        )

        second = fulfill_paid_order(order)
        self.assertTrue(second.completed)
        self.assertEqual(
            LoyaltyTransaction.objects.filter(order=order, reason="خرید").count(), 1
        )
        self.assertEqual(
            Notification.objects.filter(user=self.user, title="پرداخت موفق").count(),
            1,
        )

    def test_delivery_notification_is_retried_after_completion(self):
        order, _ = self._paid_order()
        digital_code(self.product, "FULFIL-5")

        with patch(
            "store.services.orders.notify", side_effect=RuntimeError("mail down")
        ):
            first = fulfill_paid_order(order)
        self.assertTrue(first.completed)
        self.assertFalse(first.notified)
        order.refresh_from_db()
        self.assertIsNone(order.fulfillment_notified_at)

        second = fulfill_paid_order(order)
        self.assertTrue(second.completed)
        self.assertTrue(second.notified)
        order.refresh_from_db()
        self.assertIsNotNone(order.fulfillment_notified_at)
        self.assertEqual(
            Notification.objects.filter(
                user=self.user, title="سفارش تکمیل شد"
            ).count(),
            1,
        )

    def test_zero_point_order_still_gets_one_ledger_row_and_notification(self):
        order, _ = self._paid_order()
        order.total_amount = Decimal("5000")
        order.save(update_fields=["total_amount"])
        Payment.objects.filter(order=order).update(amount=order.total_amount)
        digital_code(self.product, "FULFIL-6")

        fulfill_paid_order(order)
        fulfill_paid_order(order)

        self.assertEqual(
            LoyaltyTransaction.objects.filter(order=order, reason="خرید").count(), 1
        )
        self.assertEqual(
            Notification.objects.filter(user=self.user, title="پرداخت موفق").count(),
            1,
        )


class DigitalCodeProtectionTests(TestCase):
    def setUp(self):
        self.user = make_user("09120000602")
        self.product = make_product(name="Protected", price=10_000, stock=1)

    def test_assigned_code_cannot_be_edited_or_deleted(self):
        order, item = make_order(
            self.user,
            self.product,
            payment_status=Payment.STATUS_PAID,
            authority="AUTH-C",
        )
        code = digital_code(self.product, "PROTECT-1")
        code.is_used = True
        code.order_item = item
        code.used_at = timezone.now()
        code.save()

        code.code = "CHANGED"
        with self.assertRaises(Exception):
            code.save()
        with self.assertRaises(Exception):
            DigitalCode.objects.filter(pk=code.pk).delete()
        with self.assertRaises(Exception):
            code.delete()
        self.assertTrue(DigitalCode.objects.filter(pk=code.pk).exists())
