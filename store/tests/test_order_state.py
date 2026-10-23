"""Order state-machine rules at service, form and admin boundaries."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from store.forms import OrderAdminForm, OrderStaffForm
from store.models import Coupon, CouponRedemption, Order, Payment
from store.services.orders import cancel_pending_order, validate_staff_transition

from .helpers import make_order, make_product, make_user


class TransitionRuleTests(TestCase):
    def setUp(self):
        self.user = make_user("09120000801")
        self.product = make_product(price=100_000, stock=2)

    def _order(self, status=Order.STATUS_PENDING, *, paid=False, stock=False):
        order, _ = make_order(
            self.user,
            self.product,
            status=status,
            payment_status=Payment.STATUS_PAID if paid else Payment.STATUS_CREATED,
        )
        updates = []
        if paid:
            order.paid_at = timezone.now()
            updates.append("paid_at")
        if stock:
            order.stock_consumed_at = timezone.now()
            updates.append("stock_consumed_at")
        if updates:
            order.save(update_fields=updates)
        return order

    def test_pending_order_cannot_be_marked_paid(self):
        order = self._order()
        with self.assertRaises(ValidationError):
            validate_staff_transition(order, Order.STATUS_PAID)

    def test_paid_order_cannot_return_to_pending(self):
        order = self._order(Order.STATUS_PAID, paid=True)
        with self.assertRaises(ValidationError):
            validate_staff_transition(order, Order.STATUS_PENDING)

    def test_paid_order_cannot_be_canceled_manually(self):
        order = self._order(Order.STATUS_PAID, paid=True)
        with self.assertRaises(ValidationError):
            validate_staff_transition(order, Order.STATUS_CANCELED)

    def test_completion_requires_stock_consumption(self):
        order = self._order(Order.STATUS_PAID, paid=True)
        with self.assertRaises(ValidationError):
            validate_staff_transition(order, Order.STATUS_COMPLETED)

    def test_paid_order_can_move_to_completed_after_stock_step(self):
        order = self._order(Order.STATUS_PAID, paid=True, stock=True)
        validate_staff_transition(order, Order.STATUS_COMPLETED)

    def test_completed_order_is_terminal(self):
        order = self._order(Order.STATUS_COMPLETED, paid=True, stock=True)
        with self.assertRaises(ValidationError):
            validate_staff_transition(order, Order.STATUS_PROCESSING)

    def test_pending_order_can_be_canceled(self):
        order = self._order()
        validate_staff_transition(order, Order.STATUS_CANCELED)


class OrderFormTests(TestCase):
    def setUp(self):
        self.user = make_user("09120000802")
        self.product = make_product(price=100_000, stock=2)

    def _order(self, status=Order.STATUS_PAID, *, stock=True):
        order, _ = make_order(
            self.user,
            self.product,
            status=status,
            payment_status=Payment.STATUS_PAID,
        )
        if stock:
            order.stock_consumed_at = timezone.now()
            order.save(update_fields=["stock_consumed_at"])
        return order

    def test_staff_form_rejects_fake_payment(self):
        order = self._order(Order.STATUS_PENDING, stock=False)
        form = OrderStaffForm(data={"status": Order.STATUS_PAID}, instance=order)
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_admin_form_rejects_fake_payment(self):
        order = self._order(Order.STATUS_PENDING, stock=False)
        data = model_to_dict(order)
        data["status"] = Order.STATUS_PAID
        form = OrderAdminForm(data=data, instance=order)
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_admin_form_rejects_canceling_paid_order(self):
        order = self._order(Order.STATUS_PAID)
        data = model_to_dict(order)
        data["status"] = Order.STATUS_CANCELED
        form = OrderAdminForm(data=data, instance=order)
        self.assertFalse(form.is_valid())

    def test_admin_form_allows_valid_completion(self):
        order = self._order(Order.STATUS_PAID)
        data = model_to_dict(order)
        data["status"] = Order.STATUS_COMPLETED
        form = OrderAdminForm(data=data, instance=order)
        self.assertTrue(form.is_valid(), form.errors)

    def test_staff_form_rejects_canceling_a_live_gateway_attempt(self):
        order, _ = make_order(
            self.user,
            self.product,
            payment_status=Payment.STATUS_REDIRECTED,
        )
        form = OrderStaffForm(
            data={"status": Order.STATUS_CANCELED}, instance=order
        )
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_cancellation_never_downgrades_an_already_paid_payment(self):
        order, _ = make_order(
            self.user,
            self.product,
            payment_status=Payment.STATUS_PAID,
        )
        self.assertFalse(cancel_pending_order(order.pk))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)
        self.assertEqual(
            Payment.objects.get(order=order).status, Payment.STATUS_PAID
        )

    def test_staff_cancel_pending_releases_coupon_and_payment(self):
        order, _ = make_order(
            self.user,
            self.product,
            payment_status=Payment.STATUS_CREATED,
        )
        coupon = Coupon.objects.create(
            code="MANUAL-CANCEL",
            kind=Coupon.KIND_FIXED,
            value=10_000,
            used_count=1,
        )
        CouponRedemption.objects.create(
            coupon=coupon,
            order=order,
            user=self.user,
            amount=10_000,
        )
        form = OrderStaffForm(
            data={"status": Order.STATUS_CANCELED}, instance=order
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        order.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELED)
        self.assertEqual(
            Payment.objects.get(order=order).status, Payment.STATUS_CANCELED
        )
        self.assertEqual(coupon.used_count, 0)
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())

    def test_staff_view_cannot_cancel_paid_order(self):
        staff = make_user("09120000803", is_staff=True)
        order = self._order(Order.STATUS_PAID)
        self.client.force_login(staff)
        response = self.client.post(
            reverse("admin_model_edit", args=["orders", order.pk]),
            {"status": Order.STATUS_CANCELED},
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PAID)
