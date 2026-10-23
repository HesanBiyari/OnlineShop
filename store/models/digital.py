"""Digital inventory (gift-card codes and PINs)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q


class DigitalCodeQuerySet(models.QuerySet):
    """Refuse bulk deletion of codes that were already delivered."""

    def delete(self):
        # Lock the rows before checking. Otherwise a concurrent delivery could
        # assign a code after the check but before the DELETE.
        with transaction.atomic():
            rows = list(self.select_for_update())
            if any(row.is_used or row.order_item_id for row in rows):
                raise ValidationError(
                    "کدهای تخصیص‌یافته یا استفاده‌شده از طریق این مسیر قابل حذف نیستند."
                )
            ids = [row.pk for row in rows]
            if not ids:
                return 0, {}
            return (
                models.QuerySet(self.model, using=self.db)
                .filter(pk__in=ids)
                .delete()
            )


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

    objects = DigitalCodeQuerySet.as_manager()

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

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self._state.adding and self.pk:
                # Lock the row so a concurrent delivery cannot mark it used
                # after the check while this save writes stale values back.
                old = (
                    type(self)
                    .objects.select_for_update()
                    .filter(pk=self.pk)
                    .values(
                        "is_used",
                        "order_item_id",
                        "used_at",
                        "code",
                        "pin",
                        "product_id",
                        "variant_id",
                    )
                    .first()
                )
                if old and old["is_used"]:
                    protected = (
                        "is_used",
                        "order_item_id",
                        "used_at",
                        "code",
                        "pin",
                        "product_id",
                        "variant_id",
                    )
                    if any(
                        getattr(self, field) != old[field] for field in protected
                    ):
                        raise ValidationError(
                            "کد تحویل‌شده قابل ویرایش نیست؛ برای اصلاح به جریان ویژه نیاز است."
                        )
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            locked = (
                type(self)
                .objects.select_for_update()
                .filter(pk=self.pk)
                .first()
            )
            if locked is None:
                return 0, {}
            if locked.is_used or locked.order_item_id:
                raise ValidationError(
                    "کد تخصیص‌یافته یا استفاده‌شده قابل حذف نیست."
                )
            return models.Model.delete(locked, *args, **kwargs)

    def __str__(self) -> str:
        return f"{self.product_id} - {self.code}"
