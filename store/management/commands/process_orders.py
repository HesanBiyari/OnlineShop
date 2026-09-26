from django.core.management.base import BaseCommand

from store.models import Order
from store.utils import deliver_digital_codes


class Command(BaseCommand):
    help = "Retry paid/processing orders and complete digital-code delivery idempotently."

    def handle(self, *args, **options):
        orders = Order.objects.filter(status__in=("paid", "processing")).order_by("created_at", "id")
        processed = completed = pending = 0
        for order in orders:
            processed += 1
            try:
                delivered = deliver_digital_codes(order)
                if delivered:
                    order.status = "completed"
                    order.save(update_fields=["status"])
                    completed += 1
                else:
                    if order.status != "processing":
                        order.status = "processing"
                        order.save(update_fields=["status"])
                    pending += 1
            except Exception as exc:
                self.stderr.write(f"Order #{order.pk}: {exc}")
                pending += 1
        self.stdout.write(self.style.SUCCESS(f"Processed={processed} completed={completed} pending={pending}"))
