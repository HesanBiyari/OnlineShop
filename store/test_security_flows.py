from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .advanced_models import Coupon, CouponRedemption, LoyaltyTransaction, Wishlist
from .models import Category, DigitalCode, Order, OrderItem, Payment, Product, ProductVariant
from .tests import GiftwebFakeGateway, GiftwebFakeGatewayResult


class PaymentSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="security-user",
            password="StrongPass123!",
            email="security@example.com",
        )
        category = Category.objects.create(name="Security", slug="security")
        self.product = Product.objects.create(
            category=category, name="Secure Gift Card", price=100000, stock=5
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            name="10 USD",
            price=100000,
            stock=2,
            sku="SECURITY-10",
            is_active=True,
        )

    def make_order(self, quantity=1):
        order = Order.objects.create(
            user=self.user,
            full_name="Security User",
            email="security@example.com",
            phone="09121234567",
            total_amount=100000 * quantity,
            status="pending",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            variant=self.variant,
            product_name=self.product.name,
            variant_name=self.variant.name,
            quantity=quantity,
            unit_price=100000,
            total_price=100000 * quantity,
        )
        Payment.objects.create(
            order=order,
            amount=order.total_amount,
            currency="IRR",
            gateway="zarinpal",
            authority="SEC-AUTH",
            status="redirected",
        )
        return order

    def test_missing_or_wrong_authority_does_not_mutate_payment(self):
        order = self.make_order()
        self.client.get(reverse("payment_callback", args=[order.pk]) + "?Status=NOK")
        self.assertEqual(Payment.objects.get(order=order).status, "redirected")
        self.client.get(reverse("payment_callback", args=[order.pk]) + "?Status=OK&Authority=WRONG")
        self.assertEqual(Payment.objects.get(order=order).status, "redirected")

    def test_failed_verification_releases_coupon_and_deletes_redemption(self):
        order = self.make_order()
        coupon = Coupon.objects.create(code="FAIL10", kind="percent", value=10, used_count=1)
        CouponRedemption.objects.create(coupon=coupon, order=order, user=self.user, amount=10000)
        result = GiftwebFakeGatewayResult(ok=False, code="-1", message="verification failed", authority="SEC-AUTH")
        gateway = GiftwebFakeGateway()
        gateway.verify_payment = lambda *, amount_toman, authority: result
        with patch("store.payment_flows.get_gateway", return_value=gateway):
            response = self.client.get(reverse("payment_callback", args=[order.pk]) + "?Status=OK&Authority=SEC-AUTH")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.get(order=order).status, "failed")
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())

    def test_duplicate_success_callback_is_idempotent(self):
        order = self.make_order()
        DigitalCode.objects.create(product=self.product, variant=self.variant, code="SEC-CODE-1")
        self.client.force_login(self.user)
        with patch("store.payment_flows.get_gateway", return_value=GiftwebFakeGateway()):
            url = reverse("payment_callback", args=[order.pk]) + "?Status=OK&Authority=SEC-AUTH"
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.get(url).status_code, 302)
        self.variant.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.variant.stock, 1)
        self.assertEqual(order.status, "completed")
        self.assertEqual(order.items.first().digital_codes.count(), 1)
        self.assertEqual(LoyaltyTransaction.objects.filter(order=order, reason="خرید").count(), 1)

    def test_already_paid_callback_does_not_verify(self):
        order = self.make_order()
        order.status = "completed"
        order.payment_ref = "SEC-REF"
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "payment_ref", "paid_at"])
        payment = Payment.objects.get(order=order)
        payment.status = "paid"
        payment.reference_id = "SEC-REF"
        payment.save(update_fields=["status", "reference_id"])
        self.client.force_login(self.user)
        with patch("store.payment_flows.get_gateway") as gateway_factory:
            response = self.client.get(reverse("payment_callback", args=[order.pk]))
        self.assertEqual(response.status_code, 302)
        gateway_factory.assert_not_called()

    def test_paid_but_out_of_stock_never_delivers_code(self):
        order = self.make_order(quantity=3)
        DigitalCode.objects.create(product=self.product, variant=self.variant, code="SEC-CODE-2")
        self.client.force_login(self.user)
        with patch("store.payment_flows.get_gateway", return_value=GiftwebFakeGateway()):
            response = self.client.get(reverse("payment_callback", args=[order.pk]) + "?Status=OK&Authority=SEC-AUTH")
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        payment = Payment.objects.get(order=order)
        code = DigitalCode.objects.get(code="SEC-CODE-2")
        self.assertEqual(order.status, "processing")
        self.assertEqual(payment.status, "paid")
        self.assertFalse(code.is_used)
        self.assertIsNone(code.order_item_id)


class CouponAndAdminSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="coupon-user", password="StrongPass123!", email="coupon@example.com")
        category = Category.objects.create(name="Coupon", slug="coupon")
        self.product = Product.objects.create(category=category, name="Coupon Product", price=100000, stock=10)

    def test_checkout_recomputes_coupon_from_current_total(self):
        coupon = Coupon.objects.create(code="TEN", kind="percent", value=10)
        session = self.client.session
        session["cart"] = {f"{self.product.pk}:0": 1}
        session["coupon_code"] = coupon.code
        session["coupon_discount"] = 999999
        session.save()
        self.client.force_login(self.user)
        response = self.client.post(reverse("checkout"), {
            "full_name": "Coupon User", "email": "coupon@example.com", "phone": "09121234567"
        })
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.total_amount, 90000)
        redemption = CouponRedemption.objects.get(order=order)
        self.assertEqual(redemption.amount, 10000)

    def test_staff_cannot_escalate_user(self):
        staff = User.objects.create_user(username="staff-security", password="StrongPass123!", is_staff=True)
        target = User.objects.create_user(username="target-security", password="StrongPass123!")
        self.client.force_login(staff)
        response = self.client.post(reverse("admin_model_edit", args=["users", target.pk]), {
            "username": target.username, "first_name": "", "last_name": "", "email": "", "is_active": "on",
            "is_staff": "on", "is_superuser": "on",
        })
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertFalse(target.is_staff)
        self.assertFalse(target.is_superuser)

    def test_non_superuser_cannot_open_group_management(self):
        staff = User.objects.create_user(username="staff-list", password="StrongPass123!", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("admin_model_list", args=["groups"])).status_code, 403)

    def test_external_wishlist_next_is_rejected(self):
        target = self.product
        Wishlist.objects.all().delete()
        self.client.force_login(self.user)
        response = self.client.post(reverse("wishlist_toggle", args=[target.pk]), {"next": "https://example.com/evil"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith(reverse("product_detail", args=[target.pk])))
