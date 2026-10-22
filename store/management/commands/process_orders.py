"""Retry digital delivery for paid/processing orders.

Safe to run repeatedly (for example from cPanel cron). Deliveries are
idempotent and all-or-nothing per order line.
"""

from django.core.management.base import BaseCommand

from store.models import Order
from store.services.digital import deliver_digital_codes


class Command(BaseCommand):
    help = "Retry paid/processing orders and complete digital-code delivery idempotently."

    def handle(self, *args, **options):
        orders = (
            Order.objects.filter(
                status__in=(Order.STATUS_PAID, Order.STATUS_PROCESSING)
            )
            .order_by("created_at", "id")
        )
        processed = completed = pending = 0

        for order in orders.iterator():
            processed += 1
            try:
                delivered = deliver_digital_codes(order)
                if delivered:
                    order.status = Order.STATUS_COMPLETED
                    order.save(update_fields=["status"])
                    completed += 1
                else:
                    if order.status != Order.STATUS_PROCESSING:
                        order.status = Order.STATUS_PROCESSING
                        order.save(update_fields=["status"])
                    pending += 1
            except Exception as exc:  # pragma: no cover - operational command
                self.stderr.write(f"Order #{order.pk}: {exc}")
                pending += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed={processed} completed={completed} pending={pending}"
            )
        )
