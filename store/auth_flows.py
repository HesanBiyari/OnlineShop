from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django import forms
import re

PHONE_RE = re.compile(r"^(?:\+98|0098|98|0)?9\d{9}$")


def normalize_phone(value: str) -> str:
    phone = str(value or "").strip().replace(" ", "").replace("-", "")
    if phone.startswith("+98"):
        phone = "0" + phone[3:]
    elif phone.startswith("0098"):
        phone = "0" + phone[4:]
    elif phone.startswith("98"):
        phone = "0" + phone[2:]
    if not PHONE_RE.fullmatch(phone):
        raise forms.ValidationError("شماره موبایل معتبر نیست.")
    return phone


class PhoneSignupForm(forms.Form):
    phone = forms.CharField(max_length=30, min_length=10, label="شماره موبایل")
    email = forms.EmailField(required=True, label="ایمیل")
    password1 = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)
    password2 = forms.CharField(label="تکرار رمز عبور", widget=forms.PasswordInput)

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if User.objects.filter(username=phone).exists():
            raise forms.ValidationError("این شماره موبایل قبلاً ثبت شده است.")
        return phone

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("این ایمیل قبلاً ثبت شده است.")
        return email

    def clean(self):
        data = super().clean()
        password1 = data.get("password1")
        password2 = data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "رمزهای عبور یکسان نیستند.")
        return data

    def save(self):
        phone = self.cleaned_data["phone"]
        user = User(username=phone, email=self.cleaned_data["email"])
        user.set_password(self.cleaned_data["password1"])
        user.save()
        return user


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
    phone = request.POST.get("phone", "").strip() if request.method == "POST" else ""
    password = request.POST.get("password", "") if request.method == "POST" else ""
    user = None
    if request.method == "POST":
        try:
            phone = normalize_phone(phone)
        except forms.ValidationError:
            pass
        user = authenticate(request, username=phone, password=password)
        if user is not None and user.is_active:
            login(request, user)
            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(next_url)
            return redirect("account")
    return render(request, "login.html", {"phone": phone, "next": request.GET.get("next", ""), "login_error": request.method == "POST"})
