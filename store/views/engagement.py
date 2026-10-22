"""Wishlist, reviews, coupons, notifications, referrals and loyalty."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from store.forms import CouponForm, ReviewForm
from store.models import (
    Coupon,
    Notification,
    Product,
    Referral,
    Review,
    Wishlist,
)
from store.services.cart import get_cart_items
from store.services.promotions import (
    ensure_loyalty,
    ensure_referral,
    reserve_coupon,
)


def _safe_next(request, candidate: str) -> str:
    candidate = str(candidate or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return ""


@login_required
@require_POST
def wishlist_toggle(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    item, created = Wishlist.objects.get_or_create(
        user=request.user, product=product
    )
    if created:
        messages.success(request, "به علاقه‌مندی‌ها اضافه شد.")
    else:
        item.delete()
        messages.success(request, "از علاقه‌مندی‌ها حذف شد.")

    next_url = _safe_next(request, request.POST.get("next", ""))
    if next_url:
        return redirect(next_url)
    return redirect("product_detail", pk=product.pk)


@login_required
def wishlist(request):
    products = (
        Product.objects.filter(wishlists__user=request.user)
        .select_related("category", "discount")
        .prefetch_related("images", "variants")
        .order_by("-wishlists__created_at")
    )
    return render(request, "wishlist.html", {"products": products})


@login_required
@require_POST
def review_submit(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    form = ReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "نظر شما معتبر نیست.")
        return redirect("product_detail", pk=product.pk)

    Review.objects.update_or_create(
        user=request.user,
        product=product,
        defaults={
            "rating": form.cleaned_data["rating"],
            "title": form.cleaned_data["title"],
            "body": form.cleaned_data["body"],
            "is_approved": False,
        },
    )
    messages.success(request, "نظر ثبت شد و پس از بررسی نمایش داده می‌شود.")
    return redirect("product_detail", pk=product.pk)


@login_required
@require_POST
def coupon_apply(request):
    form = CouponForm(request.POST)
    if not form.is_valid():
        messages.error(request, "کد تخفیف معتبر نیست.")
        return redirect("checkout")

    items, total = get_cart_items(request)
    if not items:
        messages.error(request, "سبد خرید شما خالی است.")
        return redirect("cart")

    coupon, discount, error = reserve_coupon(
        request.user, form.cleaned_data["code"], total
    )
    if error:
        messages.error(request, error)
        return redirect("checkout")

    request.session["coupon_code"] = coupon.code
    # Display-only hint; checkout always recalculates.
    request.session["coupon_discount"] = str(discount)
    request.session.modified = True
    messages.success(request, f"تخفیف {discount:,.0f} تومان اعمال شد.")
    return redirect("checkout")


@login_required
@require_POST
def coupon_remove(request):
    request.session.pop("coupon_code", None)
    request.session.pop("coupon_discount", None)
    request.session.modified = True
    return redirect("checkout")


@login_required
def notifications(request):
    rows = Notification.objects.filter(user=request.user)
    unread = rows.filter(is_read=False)
    unread.update(is_read=True)
    return render(request, "notifications.html", {"notifications": rows})


@login_required
def referral(request):
    return render(request, "referral.html", {"referral": ensure_referral(request.user)})


@login_required
@require_POST
def referral_apply(request):
    code = str(request.POST.get("code", "")).strip().upper()
    referred = (
        Referral.objects.filter(code=code).select_related("user").first()
        if code
        else None
    )
    mine = ensure_referral(request.user)

    if (
        referred is None
        or referred.user_id == request.user.pk
        or mine.referred_by_id
    ):
        messages.error(request, "کد معرفی معتبر نیست یا قبلاً ثبت شده است.")
    else:
        mine.referred_by = referred.user
        mine.save(update_fields=["referred_by"])
        messages.success(request, "کد معرفی ثبت شد.")
    return redirect("referral")


@login_required
def loyalty(request):
    return render(request, "loyalty.html", {"loyalty": ensure_loyalty(request.user)})
