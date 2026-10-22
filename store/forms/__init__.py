"""Form package."""

from .auth import (
    CheckoutForm,
    CouponForm,
    PhoneLoginForm,
    PhoneSignupForm,
    ReviewForm,
)
from .staff import (
    CategoryStaffForm,
    CodeStaffForm,
    CouponStaffForm,
    DiscountStaffForm,
    GroupStaffForm,
    ImageStaffForm,
    NotificationStaffForm,
    OrderStaffForm,
    ProductStaffForm,
    ReviewStaffForm,
    UserStaffForm,
    VariantStaffForm,
)

__all__ = [
    "CategoryStaffForm",
    "CheckoutForm",
    "CodeStaffForm",
    "CouponForm",
    "CouponStaffForm",
    "DiscountStaffForm",
    "GroupStaffForm",
    "ImageStaffForm",
    "NotificationStaffForm",
    "OrderStaffForm",
    "PhoneLoginForm",
    "PhoneSignupForm",
    "ProductStaffForm",
    "ReviewForm",
    "ReviewStaffForm",
    "UserStaffForm",
    "VariantStaffForm",
]
