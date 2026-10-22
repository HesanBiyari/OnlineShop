"""View package. URL names are kept stable for existing templates and links."""

from .account import account, order_detail, orders
from .auth import login_view, logout_view, signup_view
from .cart import add_to_cart, cart_view, clear_cart, remove_from_cart, update_cart
from .catalog import home, product_detail, shop
from .checkout import checkout
from .engagement import (
    coupon_apply,
    coupon_remove,
    loyalty,
    notifications,
    referral,
    referral_apply,
    review_submit,
    wishlist,
    wishlist_toggle,
)
from .pages import (
    about,
    contact,
    faq,
    guide,
    page_not_found,
    permission_denied,
    privacy,
    robots,
    server_error,
    terms,
)
from .payments import payment, payment_callback
from .staff import (
    analytics,
    codes_export,
    codes_import,
    dashboard,
    logout_view as admin_logout_view,
    model_create,
    model_delete,
    model_edit,
    model_list,
)

__all__ = [
    "about",
    "account",
    "add_to_cart",
    "admin_logout_view",
    "analytics",
    "cart_view",
    "checkout",
    "clear_cart",
    "codes_export",
    "codes_import",
    "contact",
    "coupon_apply",
    "coupon_remove",
    "dashboard",
    "faq",
    "guide",
    "home",
    "login_view",
    "logout_view",
    "loyalty",
    "model_create",
    "model_delete",
    "model_edit",
    "model_list",
    "notifications",
    "order_detail",
    "orders",
    "page_not_found",
    "payment",
    "payment_callback",
    "permission_denied",
    "privacy",
    "product_detail",
    "referral",
    "referral_apply",
    "remove_from_cart",
    "review_submit",
    "robots",
    "server_error",
    "shop",
    "signup_view",
    "terms",
    "update_cart",
]
