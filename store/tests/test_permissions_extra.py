"""Permission boundaries, protected codes and audit-failure behaviour."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from store.models import AuditLog, Coupon, DigitalCode, Order
from store.views.staff import can_view_codes

from .helpers import digital_code, make_order, make_product, make_user


class CodePermissionTests(TestCase):
    def setUp(self):
        self.product = make_product(price=10_000)
        self.auditor = make_user("09120000901", is_staff=True)
        self.auditor.user_permissions.add(
            Permission.objects.get(codename="export_digitalcode")
        )
        self.adder = make_user("09120000902", is_staff=True)
        self.adder.user_permissions.add(
            Permission.objects.get(codename="add_digitalcode")
        )

    def _csv(self, text):
        return SimpleUploadedFile(
            "codes.csv", text.encode("utf-8"), content_type="text/csv"
        )

    def test_export_only_user_cannot_import(self):
        self.client.force_login(self.auditor)
        response = self.client.post(
            reverse("codes_import"),
            {
                "file": self._csv(
                    f"code,pin,product_id\nIMPORT-NO,1,{self.product.pk}\n"
                )
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DigitalCode.objects.filter(code="IMPORT-NO").exists())

    def test_add_only_user_can_import_but_cannot_export_or_list(self):
        self.client.force_login(self.adder)
        response = self.client.post(
            reverse("codes_import"),
            {
                "file": self._csv(
                    f"code,pin,product_id\nIMPORT-YES,1,{self.product.pk}\n"
                )
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(DigitalCode.objects.filter(code="IMPORT-YES").exists())
        self.assertFalse(can_view_codes(self.adder))
        self.assertEqual(self.client.get(reverse("codes_export")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("admin_model_list", args=["codes"])).status_code,
            403,
        )

    def test_import_detects_casefold_duplicates_inside_and_against_database(self):
        digital_code(self.product, "MiXeD-CoDe")
        self.client.force_login(self.adder)
        response = self.client.post(
            reverse("codes_import"),
            {
                "file": self._csv(
                    "code,pin,product_id\n"
                    "mixed-code,1,{pid}\n"
                    "MIXED-CODE,2,{pid}\n"
                    "MiXeD-CoDe,3,{pid}\n"
                    "BRAND-NEW,4,{pid}\n".format(pid=self.product.pk)
                )
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(DigitalCode.objects.filter(code="BRAND-NEW").exists())
        self.assertEqual(
            DigitalCode.objects.filter(code__iexact="mixed-code").count(), 1
        )
        entry = AuditLog.objects.get(action=AuditLog.ACTION_DIGITAL_IMPORT)
        self.assertEqual(entry.details["duplicates"], 3)
        self.assertEqual(entry.details["created"], 1)

    def test_export_is_not_sent_if_audit_write_fails(self):
        digital_code(self.product, "NEVER-LEAK")
        self.client.force_login(self.auditor)
        with patch(
            "store.views.staff.log_action", side_effect=RuntimeError("audit down")
        ):
            response = self.client.get(reverse("codes_export"))
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("NEVER-LEAK", response.content.decode("utf-8"))


class ProtectedCodeTests(TestCase):
    def setUp(self):
        self.superuser = make_user(
            "09120000903", is_staff=True, is_superuser=True
        )
        self.customer = make_user("09120000904")
        self.product = make_product(price=10_000, stock=1)
        self.order, self.item = make_order(
            self.customer, self.product, payment_status="paid", authority="AUTH-P"
        )
        self.code = digital_code(self.product, "ASSIGNED-CODE")
        self.code.is_used = True
        self.code.order_item = self.item
        self.code.used_at = timezone.now()
        self.code.save()

    def test_staff_panel_rejects_editing_and_deleting_assigned_code(self):
        self.client.force_login(self.superuser)
        self.assertEqual(
            self.client.get(
                reverse("admin_model_edit", args=["codes", self.code.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("admin_model_edit", args=["codes", self.code.pk]),
                {
                    "product": self.product.pk,
                    "code": "CHANGED",
                    "pin": "",
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("admin_model_delete", args=["codes", self.code.pk])
            ).status_code,
            403,
        )
        self.assertTrue(DigitalCode.objects.filter(pk=self.code.pk).exists())

    def test_model_itself_rejects_editing_or_deleting_delivered_code(self):
        self.code.refresh_from_db()
        self.code.code = "REWRITTEN"
        with self.assertRaises(ValidationError):
            self.code.save()
        with self.assertRaises(ValidationError):
            self.code.delete()
        self.assertTrue(
            DigitalCode.objects.filter(pk=self.code.pk, code="ASSIGNED-CODE").exists()
        )

    def test_django_admin_rejects_change_form_for_assigned_code(self):
        self.client.force_login(self.superuser)
        url = f"/django-admin/store/digitalcode/{self.code.pk}/change/"
        # Viewing the read-only record is allowed; saving any change is not.
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(
            url,
            {
                "product": self.product.pk,
                "variant": "",
                "code": "HACKED-CODE",
                "pin": "",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.code.refresh_from_db()
        self.assertEqual(self.code.code, "ASSIGNED-CODE")

    def test_django_admin_bulk_delete_is_refused_if_any_code_is_assigned(self):
        unused = digital_code(self.product, "UNUSED-CODE")
        model_admin = admin.site._registry[DigitalCode]
        request = RequestFactory().get("/django-admin/store/digitalcode/")
        request.user = self.superuser
        request.session = {}
        setattr(request, "_messages", FallbackStorage(request))

        model_admin.delete_queryset(
            request, DigitalCode.objects.filter(pk__in=[self.code.pk, unused.pk])
        )

        self.assertTrue(DigitalCode.objects.filter(pk=self.code.pk).exists())
        self.assertTrue(DigitalCode.objects.filter(pk=unused.pk).exists())


class SensitiveAuditFailureTests(TestCase):
    def setUp(self):
        self.superuser = make_user(
            "09120000905", is_staff=True, is_superuser=True
        )
        self.coupon = Coupon.objects.create(
            code="SENSITIVE", kind=Coupon.KIND_FIXED, value=5000
        )
        self.client.force_login(self.superuser)
        self.client.raise_request_exception = False

    def test_sensitive_edit_is_rolled_back_when_audit_fails(self):
        with patch(
            "store.views.staff.log_action", side_effect=RuntimeError("audit down")
        ):
            response = self.client.post(
                reverse("admin_model_edit", args=["coupons", self.coupon.pk]),
                {
                    "code": self.coupon.code,
                    "kind": Coupon.KIND_FIXED,
                    "value": "9000",
                    "min_order_amount": "0",
                    "usage_limit": "",
                    "is_active": "on",
                },
            )
        self.assertEqual(response.status_code, 500)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.value, 5000)

    def test_sensitive_creation_is_rolled_back_when_audit_fails(self):
        with patch(
            "store.views.staff.log_action", side_effect=RuntimeError("audit down")
        ):
            response = self.client.post(
                reverse("admin_model_create", args=["coupons"]),
                {
                    "code": "NEWSENSITIVE",
                    "kind": Coupon.KIND_FIXED,
                    "value": "9000",
                    "min_order_amount": "0",
                    "usage_limit": "",
                    "is_active": "on",
                },
            )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Coupon.objects.filter(code="NEWSENSITIVE").exists())

    def test_sensitive_deletion_is_rolled_back_when_audit_fails(self):
        with patch(
            "store.views.staff.log_action", side_effect=RuntimeError("audit down")
        ):
            response = self.client.post(
                reverse("admin_model_delete", args=["coupons", self.coupon.pk])
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Coupon.objects.filter(pk=self.coupon.pk).exists())
