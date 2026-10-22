"""Catalog pricing and session-cart behaviour."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from store.models import Discount, Product, ProductVariant
from store.services.cart import add_to_cart, cart_key, get_cart_items, get_cart_count

from .helpers import make_product, make_variant


class CatalogPricingTests(TestCase):
    def test_discount_is_applied_and_floored(self):
        product = make_product(price=99_999)
        Discount.objects.create(product=product, percent=10)
        product.refresh_from_db()
        self.assertEqual(product.final_price, Decimal("90000"))

    def test_inactive_discount_is_ignored(self):
        product = make_product(price=50_000)
        Discount.objects.create(product=product, percent=50, is_active=False)
        product.refresh_from_db()
        self.assertEqual(product.final_price, Decimal("50000"))

    def test_catalog_uses_lowest_in_stock_variant(self):
        product = make_product(price=10_000, stock=0)
        make_variant(product, name="Small", price=60_000, stock=0, sku="S")
        make_variant(product, name="Large", price=80_000, stock=3, sku="L")
        product = Product.objects.prefetch_related("variants").get(pk=product.pk)
        self.assertEqual(product.catalog_price, Decimal("80000"))
        self.assertTrue(product.catalog_has_stock)

    def test_product_with_all_variants_out_of_stock_is_unavailable(self):
        product = make_product(price=10_000, stock=5)
        make_variant(product, stock=0, sku="OUT")
        product = Product.objects.prefetch_related("variants").get(pk=product.pk)
        self.assertFalse(product.catalog_has_stock)


class SessionCartTests(TestCase):
    def setUp(self):
        self.product = make_product(price=120_000, stock=5)

    def _get_request(self):
        # Prime a session through the test client and reuse its request object.
        self.client.get(reverse("cart"))
        return self.client.session

    def test_cart_stores_only_quantities_and_recalculates_price(self):
        self.client.post(reverse("add_to_cart", args=[self.product.pk]), {"quantity": 2})
        self.assertEqual(
            self.client.session["cart"], {cart_key(self.product.pk, None): 2}
        )
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.context["total"], Decimal("240000"))

        self.product.price = Decimal("150000")
        self.product.save(update_fields=["price"])
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.context["total"], Decimal("300000"))

    def test_cart_clamps_quantity_to_stock(self):
        self.client.post(reverse("add_to_cart", args=[self.product.pk]), {"quantity": 99})
        self.assertEqual(
            self.client.session["cart"][cart_key(self.product.pk, None)], 5
        )

    def test_product_with_variants_rejects_missing_or_inactive_variant(self):
        make_variant(self.product, stock=2, sku="V1")
        ok, _ = add_to_cart(
            _RequestStub(self.client.session),
            self.product,
            variant_id="",
            quantity=1,
        )
        self.assertFalse(ok)

        make_variant(self.product, name="Old", stock=2, sku="V2", is_active=False)
        inactive = ProductVariant.objects.get(sku="V2")
        ok, _ = add_to_cart(
            _RequestStub(self.client.session),
            self.product,
            variant_id=inactive.pk,
            quantity=1,
        )
        self.assertFalse(ok)

    def test_tampered_session_key_is_dropped(self):
        session = self.client.session
        session["cart"] = {"not-a-key": 3, f"{self.product.pk}:0": 1}
        session.save()
        response = self.client.get(reverse("cart"))
        self.assertEqual(len(response.context["items"]), 1)
        self.assertNotIn("not-a-key", self.client.session["cart"])

    def test_cart_count_ignores_invalid_values(self):
        session = self.client.session
        session["cart"] = {f"{self.product.pk}:0": "2", "x:y": 5}
        session.save()
        self.assertEqual(get_cart_count(_RequestStub(self.client.session)), 2)


class _RequestStub:
    """Minimal request exposing the session/service contract."""

    def __init__(self, session):
        self.session = session
