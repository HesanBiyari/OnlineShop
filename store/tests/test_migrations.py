"""Legacy-data migration rehearsal for the fulfilment markers."""

from __future__ import annotations

from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from store.models import Order


class FulfilmentBackfillMigrationTests(TransactionTestCase):
    migrate_from = [("store", "0013_auditlog_alter_digitalcode_options_and_more")]
    migrate_to = [("store", "0015_backfill_fulfilment_markers")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        User = old_apps.get_model("auth", "User")
        StoreOrder = old_apps.get_model("store", "Order")
        Payment = old_apps.get_model("store", "Payment")

        user = User.objects.create(username="migration-buyer", password="x")
        now = timezone.now()
        statuses = {
            "pending": Order.STATUS_PENDING,
            "paid": Order.STATUS_PAID,
            "processing": Order.STATUS_PROCESSING,
            "completed": Order.STATUS_COMPLETED,
        }
        self.order_ids = {}
        for key, status in statuses.items():
            order = StoreOrder.objects.create(
                user=user,
                full_name="Migration Buyer",
                email="migration@example.com",
                phone="09120000000",
                total_amount=Decimal("100000"),
                status=status,
                paid_at=None if status == Order.STATUS_PENDING else now,
            )
            Payment.objects.create(
                order=order,
                amount=Decimal("100000"),
                currency="IRR",
                gateway="zarinpal",
                status=(
                    "created" if status == Order.STATUS_PENDING else "paid"
                ),
                paid_at=None if status == Order.STATUS_PENDING else now,
            )
            self.order_ids[key] = order.pk

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)

    def test_legacy_paid_orders_are_marked_without_double_deduction(self):
        pending = Order.objects.get(pk=self.order_ids["pending"])
        paid = Order.objects.get(pk=self.order_ids["paid"])
        processing = Order.objects.get(pk=self.order_ids["processing"])
        completed = Order.objects.get(pk=self.order_ids["completed"])

        self.assertIsNone(pending.stock_consumed_at)
        self.assertIsNone(pending.fulfillment_notified_at)
        for order in (paid, processing, completed):
            self.assertIsNotNone(order.stock_consumed_at)

        self.assertIsNone(paid.fulfillment_notified_at)
        self.assertIsNone(processing.fulfillment_notified_at)
        self.assertIsNotNone(completed.fulfillment_notified_at)
