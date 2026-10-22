"""Coupons, loyalty, referrals and their ledger rows."""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .common import money_field


class Coupon(models.Model):
    KIND_PERCENT = "percent"
    KIND_FIXED = "fixed"
    KIND_CHOICES = [
        (KIND_PERCENT, "درصدی"),
        (KIND_FIXED, "مبلغ ثابت"),
    ]

    code = models.CharField(max_length=50, unique=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_PERCENT)
    value = money_field()
    min_order_amount = money_field(default=0)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.kind == self.KIND_PERCENT and self.value > 100:
            raise ValidationError({"value": "درصد باید بین ۰ و ۱۰۰ باشد."})
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValidationError(
                {"ends_at": "زمان پایان نمی‌تواند قبل از شروع باشد."}
            )

    @property
    def is_valid_now(self) -> bool:
        now = timezone.now()
        return (
            self.is_active
            and (not self.starts_at or now >= self.starts_at)
            and (not self.ends_at or now <= self.ends_at)
            and (self.usage_limit is None or self.used_count < self.usage_limit)
        )

    def discount_for(self, amount: Decimal | int) -> Decimal:
        """Discount for an order total, never more than the total itself."""

        amount = Decimal(amount)
        if amount < Decimal(self.min_order_amount) or not self.is_valid_now:
            return Decimal("0")
        if self.kind == self.KIND_PERCENT:
            raw = (amount * Decimal(self.value) / Decimal(100)).quantize(
                Decimal("1"), rounding=ROUND_FLOOR
            )
        else:
            raw = Decimal(self.value)
        return max(Decimal("0"), min(amount, raw))


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(
        Coupon, on_delete=models.PROTECT, related_name="redemptions"
    )
    order = models.OneToOneField(
        "store.Order", on_delete=models.CASCADE, related_name="coupon_redemption"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="coupon_redemptions",
    )
    amount = money_field(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.coupon.code} - Order #{self.order_id}"


class Referral(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_profile",
    )
    code = models.CharField(max_length=32, unique=True)
    referred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user_id} - {self.code}"


class LoyaltyAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="loyalty",
    )
    points = models.PositiveIntegerField(default=0)
    lifetime_points = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id} - {self.points} points"


class LoyaltyTransaction(models.Model):
    account = models.ForeignKey(
        LoyaltyAccount, on_delete=models.CASCADE, related_name="transactions"
    )
    points = models.IntegerField()
    reason = models.CharField(max_length=160)
    order = models.ForeignKey(
        "store.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loyalty_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.account_id} - {self.points}"
