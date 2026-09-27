from .admin_panel_views import dashboard, logout_view, model_create, model_delete, model_edit, model_list
from django.urls import path

from .views import account, add_to_cart, cart_view, checkout, clear_cart, home, logout_view, order_detail, orders, product_detail, remove_from_cart, shop, update_cart
from .auth_flows import login_view, signup_view
from .payment_flows import payment, payment_callback
from .static_pages import about, contact, faq, guide, terms, privacy, robots
from .advanced_views import analytics, codes_export, codes_import, coupon_apply, coupon_remove, loyalty, notifications, referral, referral_apply, review_submit, wishlist, wishlist_toggle
# GIFTWEB_FINAL_PACKAGE_V1

urlpatterns = [
    path('dashboard/', dashboard, name='admin_dashboard'),
    path('dashboard/logout/', logout_view, name='admin_dashboard_logout'),
    path('dashboard/<str:key>/', model_list, name='admin_model_list'),
    path('dashboard/<str:key>/add/', model_create, name='admin_model_create'),
    path('dashboard/<str:key>/<int:pk>/edit/', model_edit, name='admin_model_edit'),
    path('dashboard/<str:key>/<int:pk>/delete/', model_delete, name='admin_model_delete'),

    path('robots.txt', robots, name='robots'),
    path("", home, name="home"),
    path("shop/", shop, name="shop"),
    path("about/", about, name="about"),
    path("contact/", contact, name="contact"),
    path("faq/", faq, name="faq"),
    path("guide/", guide, name="guide"),
    path("terms/", terms, name="terms"),
    path("privacy/", privacy, name="privacy"),
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
    path('wishlist/', wishlist, name='wishlist'),
    path('wishlist/toggle/<int:product_id>/', wishlist_toggle, name='wishlist_toggle'),
    path('product/<int:product_id>/review/', review_submit, name='review_submit'),
    path('coupon/apply/', coupon_apply, name='coupon_apply'),
    path('coupon/remove/', coupon_remove, name='coupon_remove'),
    path('notifications/', notifications, name='notifications'),
    path('referral/', referral, name='referral'),
    path('referral/apply/', referral_apply, name='referral_apply'),
    path('loyalty/', loyalty, name='loyalty'),
    path('admin-tools/codes/export/', codes_export, name='codes_export'),
    path('admin-tools/codes/import/', codes_import, name='codes_import'),
    path('admin-tools/analytics/', analytics, name='analytics'),]
