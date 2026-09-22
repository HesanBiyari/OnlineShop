from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Category, DigitalCode, Discount, Order, OrderItem, Product, ProductVariant


class StoreSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tester",
            email="tester@example.com",
            password="StrongPass123!",
        )
        self.category = Category.objects.create(name="Gaming", slug="gaming")
        self.product = Product.objects.create(
            category=self.category,
            name="Gift Card",
            description="Test product",
            price=100000,
            stock=3,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            name="10 USD",
            price=150000,
            stock=2,
            sku="TEST-10",
            is_active=True,
        )

    def test_catalog_properties_use_variants(self):
        self.assertTrue(self.product.catalog_has_stock)
        self.assertEqual(self.product.catalog_price, 150000)

        self.variant.stock = 0
        self.variant.save(update_fields=["stock"])
        self.product.refresh_from_db()
        self.assertFalse(self.product.catalog_has_stock)
        self.assertEqual(self.product.catalog_price, 150000)

    def test_live_discount(self):
        Discount.objects.create(product=self.product, percent=20)
        self.product.refresh_from_db()
        self.assertEqual(self.product.final_price, 80000)
        self.assertEqual(self.variant.final_price, 120000)
        self.assertEqual(self.product.catalog_old_price, 150000)
        self.assertEqual(self.product.catalog_price, 120000)

    def test_public_pages_render(self):
        urls = [
            reverse("home"),
            reverse("shop"),
            reverse("product_detail", args=[self.product.pk]),
            reverse("login"),
            reverse("signup"),
            reverse("cart"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_auth_and_account_pages(self):
        response = self.client.get(reverse("account"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.user)
        response = self.client.get(reverse("account"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("orders")).status_code, 200)

    def test_add_to_cart_and_checkout(self):
        response = self.client.post(
            reverse("add_to_cart", args=[self.product.pk]),
            {"variant_id": str(self.variant.pk), "quantity": 2},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["cart"], {f"{self.product.pk}:{self.variant.pk}": 2})

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("checkout"),
            {
                "full_name": "Test User",
                "email": "tester@example.com",
                "phone": "09121234567",
            },
        )
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.total_amount, 300000)

        response = self.client.post(reverse("payment_success", args=[order.pk]))
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, "processing")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 0)

    def test_completed_digital_delivery(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("add_to_cart", args=[self.product.pk]),
            {"variant_id": str(self.variant.pk), "quantity": 1},
        )
        DigitalCode.objects.create(product=self.product, variant=self.variant, code="CODE-1")
        self.client.post(
            reverse("checkout"),
            {
                "full_name": "Test User",
                "email": "tester@example.com",
                "phone": "09121234567",
            },
        )
        order = Order.objects.get(user=self.user)
        self.client.post(reverse("payment_success", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, "completed")
        self.assertEqual(order.items.first().digital_codes.count(), 1)
