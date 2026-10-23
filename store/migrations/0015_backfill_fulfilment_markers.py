"""Backfill fulfilment markers for orders created before 0014.

The old code had no durable "stock consumed" marker. An existing ``processing``
order could either be waiting for stock (nothing deducted) or already have had
stock deducted and be waiting for digital codes. The database cannot distinguish
the two cases. To avoid silently deducting stock a second time, every legacy
paid/processing/completed order is treated as already having consumed its stock.
Any legacy stock-shortage order must be reconciled by staff.

Existing completed orders also receive a notification marker so this migration
does not send a burst of old "order completed" notifications.
"""

from __future__ import annotations

from django.db import migrations
from django.utils import timezone


def backfill_fulfilment_markers(apps, schema_editor):
    Order = apps.get_model("store", "Order")
    now = timezone.now()
    legacy = Order.objects.filter(
        status__in=("paid", "processing", "completed"),
        stock_consumed_at__isnull=True,
    )
    for order in legacy.iterator():
        marker = order.paid_at or order.created_at or now
        updates = {"stock_consumed_at": marker}
        if order.status == "completed" and order.fulfillment_notified_at is None:
            updates["fulfillment_notified_at"] = marker
        Order.objects.filter(pk=order.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0014_audit_hardening"),
    ]

    operations = [
        migrations.RunPython(
            backfill_fulfilment_markers, migrations.RunPython.noop
        ),
    ]
