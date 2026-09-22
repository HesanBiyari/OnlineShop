import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


PHONE_RE = re.compile(r"^(?:\+98|0098|0)?9\d{9}$")


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, label="ایمیل")

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("این ایمیل قبلاً ثبت شده است.")
        return email


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

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_phone(self):
        phone = self.cleaned_data["phone"].replace(" ", "").replace("-", "")
        if not PHONE_RE.fullmatch(phone):
            raise forms.ValidationError("شماره موبایل معتبر نیست.")
        return phone
