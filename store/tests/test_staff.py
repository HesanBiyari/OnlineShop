"""Least-privilege rules for the custom staff panel."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from store.models import AuditLog, DigitalCode, Order, Product

from .helpers import digital_code, make_order, make_product, make_user


class StaffPanelAccessTests(TestCase):
    def setUp(self):
        self.staff = make_user("09120000001", is_staff=True)
        self.superuser = make_user("09120000002", is_staff=True, is_superuser=True)
        self.customer = make_user("09120000003")
        self.product = make_product(price=100_000, stock=3)
        self.order, _ = make_order(self.customer, self.product)

    def test_dashboard_requires_staff(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_staff_dashboard_renders(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "داشبورد فروشگاه")

    def test_list_headers_are_localised(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_model_list", args=["products"]))
        self.assertContains(response, "قیمت")
        self.assertContains(response, "موجودی")
        self.assertNotContains(response, ">price<")

    def test_payment_rows_are_read_only(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse("admin_model_list", args=["payments"])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("admin_model_edit", args=["payments", self.order.payment.pk])
            ).status_code,
            403,
        )

    def test_groups_and_audit_are_superuser_only(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse("admin_model_list", args=["groups"])).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("admin_model_list", args=["audit"])).status_code, 403
        )

        self.client.force_login(self.superuser)
        self.assertEqual(
            self.client.get(reverse("admin_model_list", args=["groups"])).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("admin_model_list", args=["audit"])).status_code, 200
        )

    def test_unknown_resource_redirects_to_dashboard(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_model_list", args=["nope"]))
        self.assertRedirects(response, reverse("admin_dashboard"))

    def test_delete_requires_post(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("admin_model_delete", args=["products", self.product.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_staff_can_create_product(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("admin_model_create", args=["products"]),
            {
                "name": "New Card",
                "category": "",
                "description": "",
                "price": "250000",
                "stock": "4",
                "bestseller_priority": "100",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Product.objects.get(name="New Card")
        self.assertEqual(created.price, Decimal("250000"))


class OrderEditingTests(TestCase):
    def setUp(self):
        self.staff = make_user("09120000101", is_staff=True)
        self.customer = make_user("09120000102")
        self.product = make_product(price=100_000)
        self.order, _ = make_order(self.customer, self.product, authority="AUTH-O")

    def test_money_fields_cannot_be_edited(self):
        self.order.status = Order.STATUS_PAID
        self.order.stock_consumed_at = timezone.now()
        self.order.save(update_fields=["status", "stock_consumed_at"])
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("admin_model_edit", args=["orders", self.order.pk]),
            {"status": Order.STATUS_COMPLETED, "total_amount": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_amount, Decimal("100000"))
        self.assertEqual(self.order.status, Order.STATUS_COMPLETED)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.ACTION_ORDER_STATUS, target_id=str(self.order.pk)
            ).exists()
        )

    def test_pending_order_cannot_be_marked_paid(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("admin_model_edit", args=["orders", self.order.pk]),
            {"status": Order.STATUS_PAID},
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_PENDING)


class UserAdministrationTests(TestCase):
    def setUp(self):
        self.staff = make_user("09120000201", is_staff=True)
        self.superuser = make_user("09120000202", is_staff=True, is_superuser=True)
        self.target = make_user("09120000203")
        self.other_staff = make_user("09120000204", is_staff=True)

    def test_non_superuser_cannot_escalate_privileges(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("admin_model_edit", args=["users", self.target.pk]),
            {
                "username": self.target.username,
                "first_name": "",
                "last_name": "",
                "email": self.target.email,
                "is_active": "on",
                "is_staff": "on",
                "is_superuser": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff)
        self.assertFalse(self.target.is_superuser)

    def test_non_superuser_cannot_edit_staff_account(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("admin_model_edit", args=["users", self.other_staff.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_edit_privileges(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("admin_model_edit", args=["users", self.target.pk]),
            {
                "username": self.target.username,
                "first_name": "Ali",
                "last_name": "",
                "email": self.target.email,
                "is_active": "on",
                "is_staff": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)


class DigitalCodePermissionTests(TestCase):
    def setUp(self):
        self.staff = make_user("09120000301", is_staff=True)
        self.auditor = make_user("09120000302", is_staff=True)
        self.auditor.user_permissions.add(
            Permission.objects.get(codename="export_digitalcode")
        )
        self.product = make_product(price=10_000)
        self.code = digital_code(self.product, "SECRET-CODE", pin="998877")

    def test_codes_hidden_without_export_permission(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse("admin_model_list", args=["codes"])).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("codes_export")).status_code, 403)
        self.assertEqual(self.client.get(reverse("codes_import")).status_code, 403)

    def test_export_requires_permission_and_is_audited(self):
        self.client.force_login(self.auditor)
        self.assertEqual(
            self.client.get(reverse("admin_model_list", args=["codes"])).status_code, 200
        )
        response = self.client.get(reverse("codes_export"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("SECRET-CODE", response.content.decode("utf-8-sig"))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.ACTION_DIGITAL_EXPORT, actor=self.auditor
            ).exists()
        )

    def test_anonymous_cannot_export(self):
        response = self.client.get(reverse("codes_export"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        self.assertIn("next=", response["Location"])

    def test_django_admin_code_screens_need_export_permission(self):
        self.staff.user_permissions.add(
            Permission.objects.get(codename="view_digitalcode"),
            Permission.objects.get(codename="change_digitalcode"),
        )
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get("/django-admin/store/digitalcode/").status_code, 403
        )

        self.client.force_login(self.auditor)
        self.assertEqual(
            self.client.get("/django-admin/store/digitalcode/").status_code, 200
        )

    def test_superuser_can_import_csv_and_import_is_audited(self):
        self.client.force_login(
            make_user("09120000303", is_staff=True, is_superuser=True)
        )
        upload = SimpleUploadedFile(
            "codes.csv",
            (
                "code,pin,product_id,variant_id\n"
                f"NEW-CODE-1,111,{self.product.pk},\n"
                "NEW-CODE-2,222,999999,\n"
                f"SECRET-CODE,333,{self.product.pk},\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )
        response = self.client.post(reverse("codes_import"), {"file": upload})
        self.assertEqual(response.status_code, 302)

        self.assertTrue(DigitalCode.objects.filter(code="NEW-CODE-1").exists())
        self.assertFalse(DigitalCode.objects.filter(code="NEW-CODE-2").exists())
        self.assertEqual(DigitalCode.objects.filter(code="SECRET-CODE").count(), 1)
        entry = AuditLog.objects.get(action=AuditLog.ACTION_DIGITAL_IMPORT)
        self.assertEqual(entry.details["created"], 1)
        self.assertEqual(entry.details["invalid"], 1)
        self.assertEqual(entry.details["duplicates"], 1)
