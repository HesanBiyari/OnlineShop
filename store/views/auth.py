"""Signup, login and logout."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from store.forms import PhoneLoginForm, PhoneSignupForm
from store.services.auth import (
    clear_failed_logins,
    is_locked_out,
    register_failed_login,
)


def _safe_next(request, candidate: str) -> str:
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return ""


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("account")

    form = PhoneSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "حساب شما با موفقیت ساخته شد.")
        return redirect("account")

    return render(request, "signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("account")

    next_url = request.POST.get("next") or request.GET.get("next", "")
    form = PhoneLoginForm(request.POST or None)
    login_error = ""

    if request.method == "POST" and form.is_valid():
        phone = form.cleaned_data["phone"]
        if is_locked_out(request, phone):
            login_error = (
                "تلاش‌های ناموفق زیاد بوده است. لطفاً چند دقیقه بعد دوباره تلاش کنید."
            )
        else:
            user = authenticate(
                request,
                username=phone,
                password=form.cleaned_data["password"],
            )
            if user is not None and user.is_active:
                login(request, user)
                clear_failed_logins(request, phone)
                safe_next = _safe_next(request, next_url)
                return redirect(safe_next or "account")
            register_failed_login(request, phone)
            login_error = "شماره موبایل یا رمز عبور صحیح نیست."

    return render(
        request,
        "login.html",
        {
            "form": form,
            "phone": request.POST.get("phone", "") if request.method == "POST" else "",
            "next": next_url,
            "login_error": login_error,
        },
    )


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")
