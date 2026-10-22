"""Coupons, loyalty, referrals, notifications and recent views."""

from __future__ import annotations

import secrets
import string
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from store.models import (
    Coupon,
    CouponRedemption,
    LoyaltyAccount,
    LoyaltyTransaction,
    Notification,
    Order,
    RecentlyViewed,
    Referral,
)


def referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "GW-" + "".join(secrets.choice(alphabet) for _ in range(10))


def ensure_referral(user, referred_by=None) -> Referral:
    existing = Referral.objects.filter(user=user).first()
    if existing:
        if referred_by and not existing.referred_by_id and referred_by.pk != user.pk:
            existing.referred_by = referred_by
            existing.save(update_fields=["referred_by"])
        return existing

    for _ in range(10):
        try:
            with transaction.atomic():
                return Referral.objects.create(
                    user=user,
                    code=referral_code(),
                    referred_by=referred_by,
                )
        except IntegrityError:
            continue
    # Extremely unlikely; surface a clear error instead of looping forever.
    raise RuntimeError("Could not allocate a unique referral code.")


def ensure_loyalty(user) -> LoyaltyAccount:
    account, _ = LoyaltyAccount.objects.get_or_create(user=user)
    return account


def notify(user, title: str, body: str = "") -> Notification:
    return Notification.objects.create(user=user, title=title[:160], body=body)


def award_points(
    user, points: int, reason: str, order: Order | None = None
) -> int:
    if points <= 0:
        return 0
    with transaction.atomic():
        account, _ = LoyaltyAccount.objects.select_for_update().get_or_create(
            user=user
        )
        account.points += points
        account.lifetime_points += points
        account.save(update_fields=["points", "lifetime_points", "updated_at"])
        LoyaltyTransaction.objects.create(
            account=account,
            points=points,
            reason=reason[:160],
            order=order,
        )
    return points


def finalize_advanced_order(order: Order) -> bool:
    """Award loyalty points and notify exactly once per order."""

    if LoyaltyTransaction.objects.filter(order=order, reason="خرید").exists():
        return False

    points = int(Decimal(order.total_amount) // Decimal("10000"))
    award_points(order.user, points, "خرید", order)
    notify(
        order.user,
        "پرداخت موفق",
        f"سفارش #{order.id} با موفقیت تأیید شد.",
    )
    ensure_referral(order.user)
    return True


def reserve_coupon(user, code: str, amount: Decimal) -> tuple[Coupon | None, Decimal, str]:
    """Validate a coupon for the current user and cart total.

    The session stores only the code; the discount is always recalculated from
    the cart total at checkout.
    """

    code = str(code or "").strip().upper()
    if not code:
        return None, Decimal("0"), "کد تخفیف را وارد کنید."

    with transaction.atomic():
        coupon = Coupon.objects.select_for_update().filter(code=code).first()
        if not coupon or not coupon.is_valid_now:
            return None, Decimal("0"), "کد تخفیف معتبر یا فعال نیست."
        if CouponRedemption.objects.filter(coupon=coupon, user=user).exists():
            return None, Decimal("0"), "این کد قبلاً استفاده شده است."

        discount = coupon.discount_for(amount)
        if discount <= 0:
            return None, Decimal("0"), "شرایط استفاده از این کد برای سفارش برقرار نیست."
        return coupon, discount, ""


def release_coupon_for_order(order: Order) -> bool:
    """Release a coupon reservation exactly once after a failed payment."""

    with transaction.atomic():
        redemption = (
            CouponRedemption.objects.select_for_update()
            .filter(order=order)
            .first()
        )
        if redemption is None:
            return False

        coupon = Coupon.objects.select_for_update().get(pk=redemption.coupon_id)
        if coupon.used_count:
            coupon.used_count -= 1
            coupon.save(update_fields=["used_count"])
        redemption.delete()
        return True


def record_recent_view(request, product) -> None:
    if not request.session.session_key:
        request.session.create()

    if request.user.is_authenticated:
        queryset = RecentlyViewed.objects.filter(
            user=request.user, session_key="", product=product
        )
        defaults = {"user": request.user, "session_key": ""}
    else:
        queryset = RecentlyViewed.objects.filter(
            user__isnull=True,
            session_key=request.session.session_key,
            product=product,
        )
        defaults = {"user": None, "session_key": request.session.session_key}

    row = queryset.first()
    if row:
        row.viewed_at = timezone.now()
        row.save(update_fields=["viewed_at"])
    else:
        RecentlyViewed.objects.create(product=product, **defaults)
