"""Settings parsing, notifications, revenue and upload validation."""

from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image as PILImage

from config.env import env_bool
from store.forms import CouponStaffForm
from store.models import (
    Coupon,
    CouponRedemption,
    Discount,
    Notification,
    Order,
    Payment,
    ProductImage,
)

from .helpers import make_order, make_product, make_user


class EnvBoolTests(TestCase):
    def test_accepted_values(self):
        for value in ("1", "true", "TRUE", "yes", "on"):
            with patch.dict(os.environ, {"FLAG": value}):
                self.assertTrue(env_bool("FLAG"))
        for value in ("0", "false", "FALSE", "no", "off"):
            with patch.dict(os.environ, {"FLAG": value}):
                self.assertFalse(env_bool("FLAG"))

    def test_empty_uses_default(self):
        with patch.dict(os.environ, {"FLAG": ""}):
            self.assertTrue(env_bool("FLAG", True))
            self.assertFalse(env_bool("FLAG", False))

    def test_unknown_value_is_an_error(self):
        with patch.dict(os.environ, {"FLAG": "maybe"}):
            with self.assertRaises(ValueError):
                env_bool("FLAG")


class CouponValidationTests(TestCase):
    def setUp(self):
        self.user = make_user("09120001001")
        self.product = make_product(price=100_000, stock=2)

    def test_incomplete_coupon_form_is_invalid_not_a_crash(self):
        form = CouponStaffForm(
            data={
                "code": "EMPTY",
                "kind": Coupon.KIND_PERCENT,
                "value": "",
                "min_order_amount": "0",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("value", form.errors)

    def test_model_clean_rejects_negative_and_over_100_percent(self):
        with self.assertRaises(ValidationError):
            Coupon(
                code="NEG", kind=Coupon.KIND_FIXED, value=Decimal("-1")
            ).full_clean()
        with self.assertRaises(ValidationError):
            Coupon(
                code="OVER", kind=Coupon.KIND_PERCENT, value=Decimal("101")
            ).full_clean()

    def test_database_rejects_negative_coupon_amounts(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Coupon.objects.create(
                    code="DBNEG", kind=Coupon.KIND_FIXED, value=Decimal("-1")
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Coupon.objects.create(
                    code="DBOVER", kind=Coupon.KIND_PERCENT, value=Decimal("101")
                )

    def test_database_rejects_duplicate_coupon_user_redemption(self):
        coupon = Coupon.objects.create(
            code="ONCE", kind=Coupon.KIND_FIXED, value=1
        )
        first, _ = make_order(self.user, self.product, authority="AUTH-RED-1")
        second, _ = make_order(self.user, self.product, authority="AUTH-RED-2")
        CouponRedemption.objects.create(
            coupon=coupon, order=first, user=self.user, amount=1
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CouponRedemption.objects.create(
                    coupon=coupon, order=second, user=self.user, amount=1
                )

    def test_database_rejects_discount_percent_above_100(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Discount.objects.create(product=self.product, percent=101)


class NotificationTests(TestCase):
    def setUp(self):
        self.user = make_user("09120001002")
        self.other = make_user("09120001003")
        self.mine = Notification.objects.create(
            user=self.user, title="Mine", body="Body"
        )
        self.others = Notification.objects.create(
            user=self.other, title="Other", body="Body"
        )
        self.client.force_login(self.user)

    def test_get_does_not_mark_notifications_read(self):
        response = self.client.get(reverse("notifications"))
        self.assertEqual(response.status_code, 200)
        self.mine.refresh_from_db()
        self.assertFalse(self.mine.is_read)

    def test_mark_read_requires_post(self):
        self.assertEqual(
            self.client.get(reverse("notifications_mark_read")).status_code, 405
        )

    def test_post_marks_only_own_notifications(self):
        response = self.client.post(reverse("notifications_mark_read"))
        self.assertEqual(response.status_code, 302)
        self.mine.refresh_from_db()
        self.others.refresh_from_db()
        self.assertTrue(self.mine.is_read)
        self.assertFalse(self.others.is_read)


class RevenueTests(TestCase):
    def setUp(self):
        self.staff = make_user("09120001004", is_staff=True)
        self.user = make_user("09120001005")
        self.product = make_product(price=100_000, stock=5)

    def test_today_revenue_uses_payment_time_not_order_creation(self):
        old, _ = make_order(
            self.user,
            self.product,
            status=Order.STATUS_COMPLETED,
            payment_status="paid",
            authority="OLD",
        )
        old.paid_at = timezone.now()
        old.save(update_fields=["paid_at"])
        Order.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=3)
        )
        Payment.objects.filter(order=old).update(paid_at=old.paid_at)

        unpaid, _ = make_order(
            self.user,
            self.product,
            quantity=2,
            status=Order.STATUS_PENDING,
            payment_status="failed",
            authority="UNPAID",
        )

        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["stats"]["sales_today"], old.total_amount
        )
        self.assertNotEqual(
            response.context["stats"]["sales_today"], unpaid.total_amount
        )

    def test_old_order_paid_today_is_counted_today(self):
        order, _ = make_order(
            self.user,
            self.product,
            status=Order.STATUS_COMPLETED,
            payment_status="paid",
            authority="TODAY",
        )
        order.paid_at = timezone.now()
        order.save(update_fields=["paid_at"])
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        Payment.objects.filter(order=order).update(paid_at=order.paid_at)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["today"], order.total_amount)


class ImageValidationTests(TestCase):
    def setUp(self):
        self.product = make_product(price=100_000, stock=1)

    def test_non_image_upload_is_rejected_at_model_boundary(self):
        image = ProductImage(
            product=self.product,
            image=SimpleUploadedFile(
                "fake.jpg", b"this is not an image", content_type="image/jpeg"
            ),
        )
        with self.assertRaises(ValidationError):
            image.save()

    def test_oversized_dimensions_are_rejected_at_model_boundary(self):
        buffer = BytesIO()
        PILImage.new("RGB", (20, 20), color="red").save(buffer, format="PNG")
        image = ProductImage(
            product=self.product,
            image=SimpleUploadedFile(
                "large.png", buffer.getvalue(), content_type="image/png"
            ),
        )
        with override_settings(PRODUCT_IMAGE_MAX_DIMENSION=5):
            with self.assertRaises(ValidationError):
                image.save()
