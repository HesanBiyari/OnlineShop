"""Smoke tests: every user-facing page must render with real context."""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from .helpers import make_product, make_user, make_variant


class PublicPageTests(TestCase):
    def setUp(self):
        self.category_product = make_product(name="Steam Card", price=100_000, stock=3)
        make_variant(self.category_product, name="10 USD", stock=2, sku="SMOKE-1")

    def test_public_pages_render(self):
        urls = [
            reverse("home"),
            reverse("shop"),
            reverse("shop") + "?sort=price_low",
            reverse("shop") + "?sort=price_high&q=Steam",
            reverse("product_detail", args=[self.category_product.pk]),
            reverse("about"),
            reverse("contact"),
            reverse("faq"),
            reverse("guide"),
            reverse("terms"),
            reverse("privacy"),
            reverse("login"),
            reverse("signup"),
            reverse("robots"),
            reverse("sitemap"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_missing_page_uses_custom_404(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "این صفحه پیدا نشد", status_code=404)


class AuthenticatedPageTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(name="Account Card", price=20_000, stock=2)
        self.client.force_login(self.user)

    def test_account_pages_render(self):
        for url in (
            reverse("account"),
            reverse("orders"),
            reverse("wishlist"),
            reverse("notifications"),
            reverse("referral"),
            reverse("loyalty"),
            reverse("cart"),
            reverse("checkout"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(response.status_code, {200, 302})

    def test_cart_and_checkout_render_with_items(self):
        self.client.post(reverse("add_to_cart", args=[self.product.pk]), {"quantity": 1})
        self.assertEqual(self.client.get(reverse("cart")).status_code, 200)
        self.assertEqual(self.client.get(reverse("checkout")).status_code, 200)
