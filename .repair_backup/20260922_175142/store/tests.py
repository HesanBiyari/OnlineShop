from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Discount, DigitalCode, Order, OrderItem, Product, ProductVariant


class ModelValidationTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Test Product",
            description="Test",
            price=1000,
            stock=5,
        )

    def test_discount_percent_validation(self):
        discount = Discount(product=self.product, percent=101)
        with self.assertRaises(Exception):
            discount.full_clean()

    def test_variant_must_belong_to_product_for_order_item(self):
        other_product = Product.objects.create(
            name="Other",
            description="Other",
            price=1000,
            stock=1,
        )
        variant = ProductVariant.objects.create(
            product=other_product,
            name="Other variant",
            price=1000,
            stock=1,
            sku="OTHER-1",
        )
        user = User.objects.create_user(username="u1", password="StrongPass123!")
        order = Order.objects.create(
            user=user,
            full_name="Test User",
            email="test@example.com",
            phone="09123456789",
            total_amount=1000,
        )
        item = OrderItem(
            order=order,
            product=self.product,
            variant=variant,
            product_name=self.product.name,
            variant_name=variant.name,
            quantity=1,
            unit_price=1000,
            total_price=1000,
        )
        with self.assertRaises(Exception):
            item.full_clean()


class SecurityAndFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="hesan",
            password="StrongPass123!",
            email="hesan@example.com",
        )
        self.product = Product.objects.create(
            name="Gift Card",
            description="Digital",
            price=1000,
            stock=5,
        )

    def test_remove_from_cart_requires_post(self):
        self.client.session["cart"] = {f"{self.product.id}:0": 1}
        self.client.session.save()
        response = self.client.get(
            reverse("remove_from_cart", kwargs={"key": f"{self.product.id}:0"})
        )
        self.assertEqual(response.status_code, 405)

    def test_login_rejects_external_next(self):
        response = self.client.post(
            reverse("login") + "?next=https://example.com/evil",
            {"username": "hesan", "password": "StrongPass123!", "next": "https://example.com/evil"},
        )
        self.assertRedirects(response, reverse("account"))

    def test_demo_payment_consumes_stock_and_delivers_code(self):
        self.client.login(username="hesan", password="StrongPass123!")
        order = Order.objects.create(
            user=self.user,
            full_name="Test User",
            email="hesan@example.com",
            phone="09123456789",
            total_amount=1000,
        )
        item = OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            quantity=1,
            unit_price=1000,
            total_price=1000,
        )
        code = DigitalCode.objects.create(
            product=self.product,
            code="TEST-CODE-1",
        )

        response = self.client.post(
            reverse("payment_success", kwargs={"order_id": order.id})
        )

        self.assertRedirects(
            response,
            reverse("order_detail", kwargs={"order_id": order.id}),
        )
        order.refresh_from_db()
        code.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, "completed")
        self.assertEqual(self.product.stock, 4)
        self.assertTrue(code.is_used)
        self.assertEqual(code.order_item_id, item.id)
