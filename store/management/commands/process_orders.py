"""Retry payment reconciliation and paid-order fulfilment.

Safe to run repeatedly (for example from cPanel cron). Each step is durable:
stock consumption, code delivery, loyalty and notifications are all idempotent.
"""

from __future__ import annotations

from itertools import chain

from django.core.management.base import BaseCommand

from store.models import Order, Payment
from store.services.orders import fulfill_paid_order, release_expired_pending_orders
from store.services.payments import reconcile_verifying_payments


class Command(BaseCommand):
    help = (
        "Reconcile stale payments, cancel abandoned orders and retry paid-order "
        "fulfilment (stock, digital codes, loyalty and notifications)."
    )

    def handle(self, *args, **options):
        expired = release_expired_pending_orders()
        reconciled = reconcile_verifying_payments()

        orders = (
            Order.objects.filter(
                status__in=(
                    Order.STATUS_PAID,
                    Order.STATUS_PROCESSING,
                ),
                payment__status=Payment.STATUS_PAID,
            )
            .order_by("created_at", "id")
        )
        # Completed orders with a missing delivery notification are retried too.
        notify_orders = (
            Order.objects.filter(
                status=Order.STATUS_COMPLETED,
                fulfillment_notified_at__isnull=True,
                payment__status=Payment.STATUS_PAID,
            )
            .order_by("created_at", "id")[:100]
        )

        processed = completed = pending = notified = 0
        for order in chain(orders.iterator(), notify_orders.iterator()):
            processed += 1
            try:
                result = fulfill_paid_order(order)
                if result.completed:
                    completed += 1
                else:
                    pending += 1
                if result.notified:
                    notified += 1
            except Exception as exc:  # pragma: no cover - operational command
                self.stderr.write(f"Order #{order.pk}: {exc}")
                pending += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed={processed} completed={completed} pending={pending} "
                f"notified={notified} expired={expired} reconciled={reconciled}"
            )
        )
