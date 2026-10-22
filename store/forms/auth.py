"""Authentication and checkout forms."""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from store.services.auth import normalize_phone

User = get_user_model()


class PhoneSignupForm(forms.Form):
    phone = forms.CharField(max_length=30, min_length=10, label="شماره موبایل")
    email = forms.EmailField(required=True, label="ایمیل")
    password1 = forms.CharField(
        label="رمز عبور", widget=forms.PasswordInput, strip=False
    )
    password2 = forms.CharField(
        label="تکرار رمز عبور", widget=forms.PasswordInput, strip=False
    )

    def clean_phone(self) -> str:
        try:
            phone = normalize_phone(self.cleaned_data["phone"])
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        if User.objects.filter(username=phone).exists():
            raise forms.ValidationError("این شماره موبایل قبلاً ثبت شده است.")
        return phone

    def clean_email(self) -> str:
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
        if password1 and data.get("phone") and data.get("email"):
            candidate = User(username=data["phone"], email=data["email"])
            try:
                validate_password(password1, user=candidate)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return data

    def save(self):
        user = User(
            username=self.cleaned_data["phone"],
            email=self.cleaned_data["email"],
        )
        user.set_password(self.cleaned_data["password1"])
        user.save()
        return user


class PhoneLoginForm(forms.Form):
    phone = forms.CharField(max_length=30, label="شماره موبایل")
    password = forms.CharField(
        label="رمز عبور", widget=forms.PasswordInput, strip=False
    )

    def clean_phone(self) -> str:
        raw = str(self.cleaned_data["phone"] or "").strip()
        try:
            return normalize_phone(raw)
        except ValueError as exc:
            # Staff accounts created with ``createsuperuser`` (and legacy
            # accounts from before phone signup) may use a plain username.
            # Existing usernames stay usable; new signups still require a
            # valid Iranian mobile number.
            if raw and User.objects.filter(username=raw).exists():
                return raw
            raise forms.ValidationError(str(exc)) from exc


class CheckoutForm(forms.Form):
    full_name = forms.CharField(
        max_length=150,
        min_length=3,
        label="نام و نام خانوادگی",
        strip=True,
    )
    email = forms.EmailField(label="ایمیل")
    phone = forms.CharField(
        max_length=30,
        min_length=10,
        label="شماره موبایل",
        strip=True,
    )

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()

    def clean_phone(self) -> str:
        try:
            return normalize_phone(self.cleaned_data["phone"])
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc


class ReviewForm(forms.Form):
    rating = forms.TypedChoiceField(
        label="امتیاز",
        choices=[(str(value), str(value)) for value in range(5, 0, -1)],
        coerce=int,
        initial=5,
    )
    title = forms.CharField(
        max_length=120, required=False, label="عنوان", strip=True
    )
    body = forms.CharField(
        max_length=2000,
        label="نظر",
        widget=forms.Textarea,
        strip=True,
    )


class CouponForm(forms.Form):
    code = forms.CharField(max_length=50, label="کد تخفیف", strip=True)

    def clean_code(self) -> str:
        return self.cleaned_data["code"].upper()
