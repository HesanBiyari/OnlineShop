"""Payment attempts attached one-to-one to orders."""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from .common import money_field


class Payment(models.Model):
    STATUS_CREATED = "created"
    STATUS_REDIRECTED = "redirected"
    STATUS_VERIFYING = "verifying"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"

    STATUS_CHOICES = [
        (STATUS_CREATED, "ایجاد شد"),
        (STATUS_REDIRECTED, "ارسال به درگاه"),
        (STATUS_VERIFYING, "در حال تأیید"),
        (STATUS_PAID, "پرداخت موفق"),
        (STATUS_FAILED, "ناموفق"),
        (STATUS_CANCELED, "لغو شده"),
    ]

    order = models.OneToOneField(
        "store.Order", on_delete=models.PROTECT, related_name="payment"
    )
    gateway = models.CharField(max_length=40, default="zarinpal")
    amount = money_field()
    currency = models.CharField(max_length=10, default="IRR")
    # NULL is allowed so MariaDB/MySQL can store multiple rows that have not
    # received an authority yet while keeping issued authorities unique.
    authority = models.CharField(max_length=120, blank=True, null=True, unique=True)
    reference_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_CREATED
    )
    gateway_code = models.CharField(max_length=30, blank=True)
    gateway_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "-created_at")),
            models.Index(fields=("gateway", "authority")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0),
                name="payment_amount_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return f"Payment #{self.id} - Order #{self.order_id}"

    @property
    def is_successful(self) -> bool:
        return self.status == self.STATUS_PAID
