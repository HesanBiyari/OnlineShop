"""Forms used by the custom staff panel.

Each form lists its editable fields explicitly. This replaces the previous
``modelform_factory`` approach that let staff edit order totals, payment rows
and their own privilege flags.
"""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model

from store.models import (
    Category,
    Coupon,
    DigitalCode,
    Discount,
    Notification,
    Order,
    Product,
    ProductImage,
    ProductVariant,
    Review,
)
from store.services.images import validate_image_upload
from store.services.orders import cancel_pending_order, validate_staff_transition

User = get_user_model()


class StaffModelForm(forms.ModelForm):
    def __init__(self, *args, actor=None, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)


class CategoryStaffForm(StaffModelForm):
    class Meta:
        model = Category
        fields = ("name", "slug")


class ProductStaffForm(StaffModelForm):
    class Meta:
        model = Product
        fields = (
            "name",
            "category",
            "description",
            "price",
            "stock",
            "is_bestseller",
            "bestseller_priority",
        )
        widgets = {"description": forms.Textarea(attrs={"rows": 6})}


class VariantStaffForm(StaffModelForm):
    class Meta:
        model = ProductVariant
        fields = ("product", "name", "price", "stock", "sku", "is_active")


class ImageStaffForm(StaffModelForm):
    class Meta:
        model = ProductImage
        fields = ("product", "image", "alt_text", "is_main")

    def clean_image(self):
        image = self.cleaned_data.get("image")
        # Keep the existing stored file when editing without a new upload.
        from django.core.files.uploadedfile import UploadedFile

        if image and isinstance(image, UploadedFile):
            error = validate_image_upload(image)
            if error:
                raise forms.ValidationError(error)
        return image


class DiscountStaffForm(StaffModelForm):
    class Meta:
        model = Discount
        fields = ("product", "percent", "starts_at", "ends_at", "is_active")
        widgets = {
            "starts_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "ends_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = [
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
            ]


class CodeStaffForm(StaffModelForm):
    class Meta:
        model = DigitalCode
        fields = ("product", "variant", "code", "pin")

    def clean_code(self) -> str:
        code = (self.cleaned_data.get("code") or "").strip()
        if not code:
            raise forms.ValidationError("کد دیجیتال نمی‌تواند خالی باشد.")
        queryset = DigitalCode.objects.filter(code__iexact=code)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("این کد قبلاً ثبت شده است.")
        return code

    def clean(self):
        data = super().clean()
        product = data.get("product")
        variant = data.get("variant")
        if product and variant and variant.product_id != product.id:
            self.add_error("variant", "واریانت باید متعلق به همین محصول باشد.")
        return data


class OrderCancelMixin:
    """Release coupon/payment state when a human cancels a pending order."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.previous_status = (
            self.instance.status if self.instance.pk else None
        )

    def save(self, commit=True):
        was_pending = self.previous_status == Order.STATUS_PENDING
        instance = super().save(commit=commit)
        if was_pending and instance.status == Order.STATUS_CANCELED:
            actor = getattr(self, "actor", None)
            username = getattr(actor, "username", "staff")
            cancel_pending_order(
                instance.pk,
                reason=f"سفارش به‌صورت دستی توسط {username} لغو شد.",
            )
            if commit:
                instance.refresh_from_db()
        return instance


class OrderStaffForm(OrderCancelMixin, StaffModelForm):
    """Only the fulfilment status is editable; money and ownership are not."""

    class Meta:
        model = Order
        fields = ("status",)

    def clean_status(self):
        new_status = self.cleaned_data["status"]
        validate_staff_transition(self.instance, new_status)
        return new_status


class OrderAdminForm(OrderCancelMixin, StaffModelForm):
    """Same transition rules for the Django admin path."""

    class Meta:
        model = Order
        fields = "__all__"

    def clean_status(self):
        new_status = self.cleaned_data["status"]
        validate_staff_transition(self.instance, new_status)
        return new_status


class CouponStaffForm(StaffModelForm):
    class Meta:
        model = Coupon
        fields = (
            "code",
            "kind",
            "value",
            "min_order_amount",
            "usage_limit",
            "starts_at",
            "ends_at",
            "is_active",
        )
        widgets = {
            "starts_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "ends_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = [
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
            ]

    def clean_code(self) -> str:
        return self.cleaned_data["code"].strip().upper()


class ReviewStaffForm(StaffModelForm):
    class Meta:
        model = Review
        fields = ("rating", "title", "body", "is_approved")
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}


class NotificationStaffForm(StaffModelForm):
    class Meta:
        model = Notification
        fields = ("user", "title", "body")
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}


class UserStaffForm(StaffModelForm):
    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not getattr(self.actor, "is_superuser", False):
            self.fields.pop("is_staff", None)
            self.fields.pop("is_superuser", None)

    def clean(self):
        data = super().clean()
        if (
            not getattr(self.actor, "is_superuser", False)
            and self.instance.pk
            and (self.instance.is_staff or self.instance.is_superuser)
        ):
            raise forms.ValidationError(
                "فقط مدیر ارشد می‌تواند حساب‌های مدیریتی را تغییر دهد."
            )
        return data


class GroupStaffForm(forms.Form):
    name = forms.CharField(max_length=150, label="نام گروه")
    permissions = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label="دسترسی‌ها",
        widget=forms.SelectMultiple(attrs={"size": 15}),
    )

    def __init__(self, *args, **kwargs):
        from django.contrib.auth.models import Permission

        super().__init__(*args, **kwargs)
        self.fields["permissions"].queryset = Permission.objects.select_related(
            "content_type"
        ).order_by("content_type__app_label", "codename")
