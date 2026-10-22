"""Checkout recalculates every price from the database."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from store.models import Coupon, CouponRedemption, Order, Payment
from store.services.cart import cart_key

from .helpers import make_order, make_product, make_user


class CheckoutTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(price=250_000, stock=4)
        self.client.force_login(self.user)

    def _cart(self, quantity=1, **session_values):
        session = self.client.session
        session["cart"] = {cart_key(self.product.pk, None): quantity}
        session.update(session_values)
        session.save()

    def _post_checkout(self, **overrides):
        data = {
            "full_name": "Ali Rezaei",
            "email": "ali@example.com",
            "phone": "09121234567",
        }
        data.update(overrides)
        return self.client.post(reverse("checkout"), data)

    def test_checkout_creates_order_with_database_price(self):
        self._cart(quantity=2)
        response = self._post_checkout()
        self.assertEqual(response.status_code, 302)

        order = Order.objects.get(user=self.user)
        self.assertEqual(order.total_amount, Decimal("500000"))
        self.assertEqual(order.status, Order.STATUS_PENDING)
        item = order.items.get()
        self.assertEqual(item.unit_price, Decimal("250000"))
        self.assertEqual(item.total_price, Decimal("500000"))
        self.assertEqual(Payment.objects.get(order=order).amount, Decimal("500000"))
        self.assertTrue(
            response["Location"].endswith(reverse("payment", args=[order.pk]))
        )

    def test_coupon_discount_is_recomputed_at_checkout(self):
        coupon = Coupon.objects.create(code="TEN", kind=Coupon.KIND_PERCENT, value=10)
        self._cart(coupon_code=coupon.code, coupon_discount="999999")
        self._post_checkout()

        order = Order.objects.get(user=self.user)
        self.assertEqual(order.total_amount, Decimal("225000"))
        redemption = CouponRedemption.objects.get(order=order)
        self.assertEqual(redemption.amount, Decimal("25000"))
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assertNotIn("coupon_code", self.client.session)

    def test_coupon_fixed_amount_is_capped_at_total(self):
        coupon = Coupon.objects.create(code="BIG", kind=Coupon.KIND_FIXED, value=999_999)
        self._cart(coupon_code=coupon.code)
        self._post_checkout()
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.total_amount, Decimal("0"))
        self.assertEqual(CouponRedemption.objects.get(order=order).amount, Decimal("250000"))

    def test_coupon_cannot_be_reused_by_the_same_user(self):
        coupon = Coupon.objects.create(code="ONCE", kind=Coupon.KIND_PERCENT, value=10)
        previous_order, _ = make_order(
            self.user, self.product, total_amount=250_000, authority=None
        )
        CouponRedemption.objects.create(
            coupon=coupon, order=previous_order, user=self.user, amount=25_000
        )
        self._cart(coupon_code=coupon.code)
        response = self._post_checkout()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertEqual(CouponRedemption.objects.count(), 1)

    def test_exhausted_coupon_is_rejected(self):
        coupon = Coupon.objects.create(
            code="LIMIT", kind=Coupon.KIND_PERCENT, value=10, usage_limit=1, used_count=1
        )
        self._cart(coupon_code=coupon.code)
        response = self._post_checkout()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.filter(user=self.user).exists())

    def test_empty_cart_redirects_to_shop(self):
        response = self.client.get(reverse("checkout"))
        self.assertRedirects(response, reverse("shop"))

    def test_invalid_phone_is_rejected(self):
        self._cart()
        response = self._post_checkout(phone="12345")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.filter(user=self.user).exists())
