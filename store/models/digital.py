"""Digital inventory (gift-card codes and PINs)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class DigitalCode(models.Model):
    product = models.ForeignKey(
        "store.Product",
        on_delete=models.CASCADE,
        related_name="digital_codes",
    )
    variant = models.ForeignKey(
        "store.ProductVariant",
        on_delete=models.CASCADE,
        related_name="digital_codes",
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=255, unique=True)
    pin = models.CharField(max_length=200, blank=True)
    is_used = models.BooleanField(default=False)
    order_item = models.ForeignKey(
        "store.OrderItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="digital_codes",
    )
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("product", "variant", "is_used")),
            models.Index(fields=("order_item",)),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(is_used=False, used_at__isnull=True, order_item__isnull=True)
                    | Q(is_used=True, used_at__isnull=False, order_item__isnull=False)
                ),
                name="digitalcode_usage_state_consistent",
            ),
        ]
        permissions = [
            ("export_digitalcode", "Can export digital codes and PINs"),
        ]

    def clean(self) -> None:
        if self.variant and self.variant.product_id != self.product_id:
            raise ValidationError("واریانت باید متعلق به همین محصول باشد.")
        if self.is_used and (self.order_item_id is None or self.used_at is None):
            raise ValidationError(
                "کد مصرف‌شده باید زمان استفاده و آیتم سفارش داشته باشد."
            )
        if not self.is_used and (
            self.order_item_id is not None or self.used_at is not None
        ):
            raise ValidationError(
                "کد مصرف‌نشده نباید به سفارش یا زمان استفاده متصل باشد."
            )

    def __str__(self) -> str:
        return f"{self.product_id} - {self.code}"
