"""Orders and order lines."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .common import money_field


class Order(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELED = "canceled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "در انتظار پرداخت"),
        (STATUS_PAID, "پرداخت شده"),
        (STATUS_PROCESSING, "در حال پردازش"),
        (STATUS_COMPLETED, "تکمیل شده"),
        (STATUS_CANCELED, "لغو شده"),
    ]
    PAID_STATUSES = (STATUS_PAID, STATUS_PROCESSING, STATUS_COMPLETED)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    total_amount = money_field(default=0)
    # MySQL allows several NULL values in a unique index but not several empty
    # strings. This column therefore stays non-unique and callbacks are made
    # idempotent through the one-to-one Payment row instead of a partial index.
    payment_ref = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("user", "-created_at")),
            models.Index(fields=("status", "-created_at")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_amount__gte=0),
                name="order_total_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return f"Order #{self.id} - {self.user_id}"

    @property
    def is_paid(self) -> bool:
        return self.status in self.PAID_STATUSES


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "store.Product",
        on_delete=models.PROTECT,
    )
    variant = models.ForeignKey(
        "store.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    product_name = models.CharField(max_length=200)
    variant_name = models.CharField(max_length=150, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = money_field(default=0)
    total_price = money_field(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="order_item_quantity_gte_1",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0),
                name="order_item_unit_price_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(total_price__gte=0),
                name="order_item_total_price_gte_0",
            ),
        ]
        indexes = [
            models.Index(fields=("order",)),
            models.Index(fields=("product",)),
        ]

    def clean(self) -> None:
        if self.variant_id and self.product_id:
            if self.variant.product_id != self.product_id:
                raise ValidationError("واریانت باید متعلق به همین محصول باشد.")

    def __str__(self) -> str:
        return f"{self.product_name} - Order #{self.order_id}"
