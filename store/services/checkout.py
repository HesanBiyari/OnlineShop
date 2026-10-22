"""Order creation from the server-side cart."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import transaction

from store.models import (
    Coupon,
    CouponRedemption,
    Order,
    OrderItem,
    Payment,
)

from .cart import get_cart_items


class CheckoutError(Exception):
    """Base error carrying a safe, user-facing message."""


class CartEmptyError(CheckoutError):
    pass


class CouponNoLongerValidError(CheckoutError):
    pass


def create_order_from_cart(request, cleaned_data: dict) -> Order:
    """Create an order, its lines, coupon redemption and payment row.

    All prices, stock and coupon values are recalculated while the relevant
    rows are locked. The client only supplies contact fields.
    """

    with transaction.atomic():
        items, subtotal = get_cart_items(request, lock=True)
        if not items:
            raise CartEmptyError("سبد خرید شما خالی است.")

        coupon: Coupon | None = None
        discount = Decimal("0")
        coupon_code = str(request.session.get("coupon_code") or "").strip().upper()

        if coupon_code:
            coupon = (
                Coupon.objects.select_for_update().filter(code=coupon_code).first()
            )
            if coupon is None or not coupon.is_valid_now:
                raise CouponNoLongerValidError(
                    "کد تخفیف دیگر برای این سبد معتبر نیست."
                )
            if CouponRedemption.objects.filter(
                coupon=coupon, user=request.user
            ).exists():
                raise CouponNoLongerValidError(
                    "این کد تخفیف قبلاً توسط شما استفاده شده است."
                )
            discount = coupon.discount_for(subtotal)
            if discount <= 0:
                raise CouponNoLongerValidError(
                    "کد تخفیف دیگر برای این سبد معتبر نیست."
                )

        total = max(Decimal("0"), subtotal - discount)
        order = Order.objects.create(
            user=request.user,
            full_name=cleaned_data["full_name"],
            email=cleaned_data["email"],
            phone=cleaned_data["phone"],
            total_amount=total,
            status=Order.STATUS_PENDING,
        )

        if coupon is not None:
            coupon.used_count += 1
            coupon.save(update_fields=["used_count"])
            CouponRedemption.objects.create(
                coupon=coupon,
                order=order,
                user=request.user,
                amount=discount,
            )
            request.session.pop("coupon_code", None)
            request.session.pop("coupon_discount", None)
            request.session.modified = True

        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    product=item["product"],
                    variant=item["variant"],
                    product_name=item["product"].name,
                    variant_name=item["variant"].name if item["variant"] else "",
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    total_price=item["total"],
                )
                for item in items
            ]
        )

        Payment.objects.create(
            order=order,
            amount=total,
            currency=str(getattr(settings, "PAYMENT_CURRENCY", "IRR")).upper(),
            gateway=str(getattr(settings, "PAYMENT_GATEWAY", "zarinpal")),
            status=Payment.STATUS_CREATED,
        )

        return order
