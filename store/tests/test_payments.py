"""Payment initiation and callback guarantees."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

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
from store.services.gateway import GatewayResult
from store.services.payments import (
    OUTCOME_ALREADY_PAID,
    OUTCOME_CANCELED,
    OUTCOME_INVALID,
    OUTCOME_VERIFY_ERROR,
    process_callback,
    reconcile_verifying_payments,
    start_payment,
)

from .helpers import FakeGateway, digital_code, make_order, make_product, make_user, make_variant


class StartPaymentTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(price=100_000)
        self.order, _ = make_order(
            self.user, self.product, authority=None, payment_status=Payment.STATUS_CREATED
        )

    def test_start_payment_stores_authority_and_uses_order_total(self):
        gateway = FakeGateway()
        with patch("store.services.payments.get_gateway", return_value=gateway):
            result = start_payment(self.order, callback_url="https://testserver/cb/")

        self.assertTrue(result.ok)
        self.assertEqual(result.redirect_url, gateway.start_url + "NEW-AUTHORITY")
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.authority, "NEW-AUTHORITY")
        self.assertEqual(payment.status, Payment.STATUS_REDIRECTED)
        self.assertEqual(gateway.create_calls[0]["amount_toman"], Decimal("100000"))

    def test_gateway_failure_marks_payment_failed(self):
        gateway = FakeGateway(
            create_result=GatewayResult(False, code="-1", message="rejected")
        )
        with patch("store.services.payments.get_gateway", return_value=gateway):
            result = start_payment(self.order)

        self.assertFalse(result.ok)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.STATUS_FAILED)

    def test_non_pending_order_is_not_sent_to_gateway(self):
        self.order.status = Order.STATUS_COMPLETED
        self.order.save(update_fields=["status"])
        gateway = FakeGateway()
        with patch("store.services.payments.get_gateway", return_value=gateway):
            result = start_payment(self.order)
        self.assertFalse(result.ok)
        self.assertTrue(result.already_paid)
        self.assertEqual(gateway.create_calls, [])

    def test_recent_authority_is_reused(self):
        payment = Payment.objects.get(order=self.order)
        payment.authority = "REUSE-ME"
        payment.status = Payment.STATUS_REDIRECTED
        payment.save(update_fields=["authority", "status"])
        gateway = FakeGateway()
        with patch("store.services.payments.get_gateway", return_value=gateway):
            result = start_payment(self.order)
        self.assertTrue(result.ok)
        self.assertEqual(result.redirect_url, gateway.start_url + "REUSE-ME")
        self.assertEqual(gateway.create_calls, [])


class CallbackTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(price=100_000, stock=5)
        self.variant = make_variant(self.product, price=100_000, stock=2, sku="VCB")

    def _order(self, **kwargs):
        order, item = make_order(
            self.user,
            self.product,
            variant=self.variant,
            authority="AUTH-OK",
            **kwargs,
        )
        return order, item

    def _callback(self, order, query="Status=OK&Authority=AUTH-OK", login=True):
        if login:
            self.client.force_login(self.user)
        return self.client.get(reverse("payment_callback", args=[order.pk]) + "?" + query)

    def test_successful_callback_pays_order_and_delivers_code(self):
        order, item = self._order()
        code = digital_code(self.product, "CODE-1", variant=self.variant)
        gateway = FakeGateway()
        with patch("store.services.payments.get_gateway", return_value=gateway):
            response = self._callback(order)

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        payment = Payment.objects.get(order=order)
        code.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertEqual(payment.status, Payment.STATUS_PAID)
        self.assertEqual(payment.reference_id, "REF-123")
        self.assertEqual(order.payment_ref, "REF-123")
        self.assertEqual(self.variant.stock, 1)
        self.assertTrue(code.is_used)
        self.assertEqual(code.order_item_id, item.pk)
        self.assertEqual(
            LoyaltyTransaction.objects.filter(order=order, reason="خرید").count(), 1
        )
        self.assertEqual(
            Notification.objects.filter(user=self.user).count(), 2
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.user, title="پرداخت موفق"
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.user, title="سفارش تکمیل شد"
            ).exists()
        )
        self.assertEqual(gateway.verify_calls, [(Decimal("100000"), "AUTH-OK")])

    def test_duplicate_callback_is_idempotent(self):
        order, _ = self._order()
        digital_code(self.product, "CODE-1", variant=self.variant)
        gateway = FakeGateway()
        with patch("store.services.payments.get_gateway", return_value=gateway):
            self._callback(order)
            self._callback(order)

        self.variant.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.variant.stock, 1)
        self.assertEqual(order.items.first().digital_codes.count(), 1)
        self.assertEqual(
            LoyaltyTransaction.objects.filter(order=order, reason="خرید").count(), 1
        )
        self.assertEqual(len(gateway.verify_calls), 1)

    def test_wrong_authority_does_not_touch_payment(self):
        order, _ = self._order()
        response = self._callback(order, query="Status=OK&Authority=WRONG")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            Payment.objects.get(order=order).status, Payment.STATUS_REDIRECTED
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)

    def test_missing_authority_does_not_mutate_payment(self):
        order, _ = self._order()
        response = self._callback(order, query="Status=NOK")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            Payment.objects.get(order=order).status, Payment.STATUS_REDIRECTED
        )

    def test_failed_verification_releases_coupon(self):
        order, _ = self._order()
        coupon = Coupon.objects.create(code="FAIL10", kind=Coupon.KIND_PERCENT, value=10, used_count=1)
        CouponRedemption.objects.create(
            coupon=coupon, order=order, user=self.user, amount=10_000
        )
        gateway = FakeGateway(
            verify_result=GatewayResult(False, code="-1", message="verification failed")
        )
        with patch("store.services.payments.get_gateway", return_value=gateway):
            response = self._callback(order)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Payment.objects.get(order=order).status, Payment.STATUS_FAILED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELED)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())

    def test_network_error_keeps_attempt_verifying_and_keeps_coupon(self):
        order, _ = self._order()
        coupon = Coupon.objects.create(code="NET10", kind=Coupon.KIND_PERCENT, value=10, used_count=1)
        CouponRedemption.objects.create(
            coupon=coupon, order=order, user=self.user, amount=10_000
        )
        gateway = FakeGateway(
            verify_result=GatewayResult(False, code="NETWORK", message="offline")
        )
        with patch("store.services.payments.get_gateway", return_value=gateway):
            response = self._callback(order)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.get(order=order).status, Payment.STATUS_VERIFYING)
        self.assertTrue(CouponRedemption.objects.filter(order=order).exists())

    def test_reconciliation_confirms_stale_verifying_payment_once(self):
        order, _ = self._order()
        digital_code(self.product, "RECON-1", variant=self.variant)
        offline = FakeGateway(
            verify_result=GatewayResult(False, code="NETWORK", message="offline")
        )
        with patch("store.services.payments.get_gateway", return_value=offline):
            self._callback(order)
        Payment.objects.filter(order=order).update(
            updated_at=timezone.now() - timedelta(minutes=10)
        )

        online = FakeGateway()
        with patch("store.services.payments.get_gateway", return_value=online):
            self.assertEqual(reconcile_verifying_payments(), 1)
            self.assertEqual(reconcile_verifying_payments(), 0)

        order.refresh_from_db()
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.status, Payment.STATUS_PAID)
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertEqual(order.items.first().digital_codes.count(), 1)
        self.assertEqual(len(online.verify_calls), 1)

    def test_amount_mismatch_never_calls_gateway_or_marks_paid(self):
        order, _ = self._order()
        Payment.objects.filter(order=order).update(amount=Decimal("1"))
        gateway = FakeGateway()
        with patch("store.services.payments.get_gateway", return_value=gateway):
            response = self._callback(order)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(gateway.verify_calls, [])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)
        self.assertEqual(
            Payment.objects.get(order=order).status, Payment.STATUS_REDIRECTED
        )

    def test_user_cancel_marks_payment_canceled(self):
        order, _ = self._order()
        response = self._callback(order, query="Status=NOK&Authority=AUTH-OK")
        self.assertRedirects(
            response, reverse("checkout"), target_status_code=302
        )
        self.assertEqual(Payment.objects.get(order=order).status, Payment.STATUS_CANCELED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELED)

    def test_paid_order_is_never_downgraded(self):
        order, item = self._order(status=Order.STATUS_COMPLETED)
        payment = Payment.objects.get(order=order)
        payment.status = Payment.STATUS_PAID
        payment.save(update_fields=["status"])

        outcome = process_callback(order.pk, "AUTH-OK", "NOK")
        self.assertEqual(outcome.kind, OUTCOME_ALREADY_PAID)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_PAID)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)

    def test_paid_order_does_not_call_gateway(self):
        order, _ = self._order(status=Order.STATUS_PAID)
        payment = Payment.objects.get(order=order)
        payment.status = Payment.STATUS_PAID
        payment.save(update_fields=["status"])
        with patch("store.services.payments.get_gateway") as factory:
            self._callback(order)
        factory.assert_not_called()

    def test_out_of_stock_payment_stays_processing_without_delivery(self):
        order, _ = self._order(quantity=3)
        code = digital_code(self.product, "CODE-2", variant=self.variant)
        with patch("store.services.payments.get_gateway", return_value=FakeGateway()):
            response = self._callback(order)

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        payment = Payment.objects.get(order=order)
        code.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PROCESSING)
        self.assertEqual(payment.status, Payment.STATUS_PAID)
        self.assertEqual(self.variant.stock, 2)
        self.assertFalse(code.is_used)
        self.assertIsNone(code.order_item_id)

    def test_canceled_order_rejects_callback(self):
        order, _ = self._order(status=Order.STATUS_CANCELED)
        outcome = process_callback(order.pk, "AUTH-OK", "OK")
        self.assertEqual(outcome.kind, OUTCOME_INVALID)
        self.assertEqual(
            Payment.objects.get(order=order).status, Payment.STATUS_REDIRECTED
        )

    def test_physical_stock_is_decremented(self):
        order, _ = make_order(
            self.user,
            self.product,
            variant=None,
            quantity=2,
            authority="AUTH-PHYS",
            unit_price=100_000,
        )
        with patch("store.services.payments.get_gateway", return_value=FakeGateway()):
            process_callback(order.pk, "AUTH-PHYS", "OK")

        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        # No digital stock was available for this line, so it needs manual
        # fulfilment instead of being marked complete.
        self.assertEqual(order.status, Order.STATUS_PROCESSING)


class CallbackSafetyTests(TestCase):
    def test_unknown_order_returns_404(self):
        response = self.client.get(reverse("payment_callback", args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_success_renders_result_without_redirect(self):
        user = make_user()
        product = make_product(price=10_000, stock=1)
        order, _ = make_order(user, product, authority="AUTH-ANON")
        with patch("store.services.payments.get_gateway", return_value=FakeGateway()):
            response = self.client.get(
                reverse("payment_callback", args=[order.pk])
                + "?Status=OK&Authority=AUTH-ANON"
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پرداخت")
