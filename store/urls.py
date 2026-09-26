from django.urls import path

from .views import account, add_to_cart, cart_view, checkout, clear_cart, home, logout_view, order_detail, orders, product_detail, remove_from_cart, shop, update_cart
from .auth_flows import login_view, signup_view
from .payment_flows import payment, payment_callback

urlpatterns = [
    path("", home, name="home"),
    path("shop/", shop, name="shop"),
    path("product/<int:pk>/", product_detail, name="product_detail"),
    path("signup/", signup_view, name="signup"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("account/", account, name="account"),
    path("cart/", cart_view, name="cart"),
    path("cart/add/<int:pk>/", add_to_cart, name="add_to_cart"),
    path("cart/update/", update_cart, name="update_cart"),
    path("cart/remove/<str:key>/", remove_from_cart, name="remove_from_cart"),
    path("cart/clear/", clear_cart, name="clear_cart"),
    path("checkout/", checkout, name="checkout"),
    path("payment/<int:order_id>/", payment, name="payment"),
    path("payment/<int:order_id>/callback/", payment_callback, name="payment_callback"),
    path("payment/<int:order_id>/success/", payment_callback, name="payment_success"),
    path("orders/", orders, name="orders"),
    path("orders/<int:order_id>/", order_detail, name="order_detail"),
]
