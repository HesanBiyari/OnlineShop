"""Digital delivery is all-or-nothing per line and idempotent."""

from __future__ import annotations

from django.test import TestCase

from store.models import DigitalCode
from store.services.digital import deliver_digital_codes

from .helpers import digital_code, make_order, make_product, make_user, make_variant


class DigitalDeliveryTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(price=50_000, stock=10)

    def test_all_or_nothing_per_line(self):
        order, item = make_order(self.user, self.product, quantity=3, authority=None)
        digital_code(self.product, "C1")
        digital_code(self.product, "C2")

        delivered = deliver_digital_codes(order)

        self.assertFalse(delivered)
        self.assertEqual(item.digital_codes.count(), 0)
        self.assertEqual(DigitalCode.objects.filter(is_used=True).count(), 0)

    def test_delivery_assigns_exact_quantity_and_is_idempotent(self):
        order, item = make_order(self.user, self.product, quantity=2, authority=None)
        digital_code(self.product, "C1")
        digital_code(self.product, "C2")
        digital_code(self.product, "C3")

        self.assertTrue(deliver_digital_codes(order))
        self.assertTrue(deliver_digital_codes(order))

        self.assertEqual(item.digital_codes.count(), 2)
        self.assertEqual(DigitalCode.objects.filter(is_used=True).count(), 2)
        self.assertEqual(DigitalCode.objects.get(code="C3").is_used, False)

    def test_variant_codes_do_not_leak_between_variants(self):
        variant_x = make_variant(self.product, name="X", stock=1, sku="X")
        variant_y = make_variant(self.product, name="Y", stock=1, sku="Y")
        order, item = make_order(
            self.user, self.product, variant=variant_x, quantity=1, authority=None
        )
        digital_code(self.product, "FOR-Y", variant=variant_y)
        digital_code(self.product, "FOR-X", variant=variant_x)

        self.assertTrue(deliver_digital_codes(order))

        item.refresh_from_db()
        self.assertEqual(item.digital_codes.get().code, "FOR-X")
        self.assertFalse(DigitalCode.objects.get(code="FOR-Y").is_used)

    def test_used_codes_are_never_reassigned(self):
        order, item = make_order(self.user, self.product, quantity=1, authority=None)
        other_order, other_item = make_order(
            self.user, self.product, quantity=1, authority=None
        )
        taken = digital_code(self.product, "TAKEN")
        taken.is_used = True
        taken.order_item = other_item
        from django.utils import timezone

        taken.used_at = timezone.now()
        taken.save(update_fields=["is_used", "order_item", "used_at"])
        digital_code(self.product, "FREE")

        self.assertTrue(deliver_digital_codes(order))
        self.assertEqual(item.digital_codes.get().code, "FREE")

    def test_missing_codes_leave_order_incomplete(self):
        order, _ = make_order(self.user, self.product, quantity=1, authority=None)
        self.assertFalse(deliver_digital_codes(order))
        self.assertEqual(DigitalCode.objects.count(), 0)
