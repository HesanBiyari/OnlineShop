from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label="ایمیل",
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "password1",
            "password2",
        )

    def clean_email(self):
        email = self.cleaned_data["email"]

        if User.objects.filter(
            email__iexact=email
        ).exists():
            raise forms.ValidationError(
                "این ایمیل قبلاً ثبت شده است."
            )

        return email


class CheckoutForm(forms.Form):
    full_name = forms.CharField(
        max_length=150,
        label="نام و نام خانوادگی",
    )

    email = forms.EmailField(
        label="ایمیل",
    )

    phone = forms.CharField(
        max_length=30,
        label="شماره موبایل",
    )