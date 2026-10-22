"""Model package.

The Django app label stays ``store`` so existing table names and migration
history remain valid.
"""

from .audit import AuditLog
from .catalog import Category, Discount, Product, ProductImage, ProductVariant
from .digital import DigitalCode
from .engagement import Notification, RecentlyViewed, Review, Wishlist
from .orders import Order, OrderItem
from .payments import Payment
from .promotions import (
    Coupon,
    CouponRedemption,
    LoyaltyAccount,
    LoyaltyTransaction,
    Referral,
)

__all__ = [
    "AuditLog",
    "Category",
    "Coupon",
    "CouponRedemption",
    "DigitalCode",
    "Discount",
    "LoyaltyAccount",
    "LoyaltyTransaction",
    "Notification",
    "Order",
    "OrderItem",
    "Payment",
    "Product",
    "ProductImage",
    "ProductVariant",
    "RecentlyViewed",
    "Referral",
    "Review",
    "Wishlist",
]
