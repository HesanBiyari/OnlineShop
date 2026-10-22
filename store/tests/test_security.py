"""Cross-cutting access-control and request-forgery checks."""

from __future__ import annotations

from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from store.models import Order
from store.services.audit import client_ip

from .helpers import FakeGateway, make_order, make_product, make_user


class OrderOwnershipTests(TestCase):
    def setUp(self):
        self.owner = make_user("09120000401")
        self.other = make_user("09120000402")
        self.product = make_product(price=10_000)
        self.order, _ = make_order(self.owner, self.product, authority="AUTH-OWN")

    def test_order_detail_is_owner_only(self):
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(reverse("order_detail", args=[self.order.pk])).status_code,
            200,
        )

        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(reverse("order_detail", args=[self.order.pk])).status_code,
            404,
        )

    def test_payment_page_is_owner_only(self):
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(reverse("payment", args=[self.order.pk])).status_code, 404
        )

    def test_anonymous_order_detail_redirects_to_login(self):
        response = self.client.get(reverse("order_detail", args=[self.order.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])


class CsrfTests(TestCase):
    def setUp(self):
        self.user = make_user("09120000501")
        self.product = make_product(price=10_000)
        self.order, _ = make_order(self.user, self.product, authority="AUTH-CSRF")

    def test_payment_post_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(reverse("payment", args=[self.order.pk]))
        self.assertEqual(response.status_code, 403)

    def test_cart_add_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("add_to_cart", args=[self.product.pk]), {"quantity": 1})
        self.assertEqual(response.status_code, 403)

    def test_cart_mutations_are_post_only(self):
        self.assertEqual(
            self.client.get(reverse("add_to_cart", args=[self.product.pk])).status_code,
            405,
        )
        self.assertEqual(self.client.get(reverse("clear_cart")).status_code, 405)


class PaymentRequestTests(TestCase):
    def setUp(self):
        self.user = make_user("09120000601")
        self.product = make_product(price=321_000)
        self.order, _ = make_order(self.user, self.product, authority=None)
        self.client.force_login(self.user)

    def test_gateway_amount_comes_from_order_not_request(self):
        gateway = FakeGateway()
        with patch("store.services.payments.get_gateway", return_value=gateway):
            response = self.client.post(
                reverse("payment", args=[self.order.pk]), {"amount": "1"}
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(gateway.create_calls[0]["amount_toman"], 321_000)

    def test_payment_get_does_not_contact_gateway(self):
        gateway = FakeGateway()
        with patch("store.services.payments.get_gateway", return_value=gateway):
            response = self.client.get(reverse("payment", args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(gateway.create_calls, [])

    def test_paid_order_cannot_open_payment_page(self):
        self.order.status = Order.STATUS_COMPLETED
        self.order.save(update_fields=["status"])
        response = self.client.get(reverse("payment", args=[self.order.pk]))
        self.assertRedirects(
            response, reverse("order_detail", args=[self.order.pk])
        )


class ClientIpTests(TestCase):
    def test_forwarded_for_header_is_ignored(self):
        request = type(
            "Request",
            (),
            {"META": {"REMOTE_ADDR": "10.0.0.1", "HTTP_X_FORWARDED_FOR": "1.2.3.4"}},
        )()
        self.assertEqual(client_ip(request), "10.0.0.1")

    def test_invalid_remote_addr_returns_none(self):
        request = type("Request", (), {"META": {"REMOTE_ADDR": "not-an-ip"}})()
        self.assertIsNone(client_ip(request))
