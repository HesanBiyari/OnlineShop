from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.PositiveIntegerField()
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("-created_at",)),
            models.Index(fields=("category",)),
        ]

    def __str__(self):
        return self.name

    def _active_variant_list(self):
        prefetched = getattr(self, "active_variants", None)
        if prefetched is not None:
            return list(prefetched)
        return list(self.variants.filter(is_active=True).order_by("price", "id"))

    @property
    def final_price(self):
        discount = getattr(self, "discount", None)
        if discount and discount.is_active_now:
            discount_amount = self.price * discount.percent // 100
            return max(0, self.price - discount_amount)
        return self.price

    @property
    def catalog_has_stock(self):
        """Whether the item can currently be added to the cart.

        Once a product has active variants, the cart requires a variant and the
        product-level stock is no longer a valid fallback.
        """
        variants = self._active_variant_list()
        if variants:
            return any(variant.stock > 0 for variant in variants)
        return self.stock > 0

    @property
    def catalog_price(self):
        """Lowest variant price, preferring variants that are currently in stock."""
        variants = self._active_variant_list()
        if variants:
            available = [variant.final_price for variant in variants if variant.stock > 0]
            prices = available or [variant.final_price for variant in variants]
            return min(prices)
        return self.final_price

    @property
    def catalog_old_price(self):
        """Raw price corresponding to the catalog price when a live discount exists."""
        discount = getattr(self, "discount", None)
        if not discount or not discount.is_active_now:
            return None
        variants = self._active_variant_list()
        if variants:
            available = [variant.price for variant in variants if variant.stock > 0]
            prices = available or [variant.price for variant in variants]
            return min(prices)
        return self.price


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    name = models.CharField(max_length=150)
    price = models.PositiveIntegerField()
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("price", "id")
        indexes = [
            models.Index(fields=("product", "is_active")),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    def clean(self):
        if self.product_id is None:
            return

    @property
    def final_price(self):
        discount = getattr(self.product, "discount", None)
        if discount and discount.is_active_now:
            discount_amount = self.price * discount.percent // 100
            return max(0, self.price - discount_amount)
        return self.price


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=200, blank=True)
    is_main = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("product",),
                condition=Q(is_main=True),
                name="one_main_image_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} - Image"


class Discount(models.Model):
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="discount",
    )
    percent = models.PositiveIntegerField()
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(percent__gte=0) & Q(percent__lte=100),
                name="discount_percent_0_100",
            ),
            models.CheckConstraint(
                condition=Q(starts_at__isnull=True)
                | Q(ends_at__isnull=True)
                | Q(starts_at__lte=F("ends_at")),
                name="discount_start_before_end",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.percent}%"

    def clean(self):
        if not 0 <= self.percent <= 100:
            raise ValidationError({"percent": "درصد تخفیف باید بین ۰ تا ۱۰۰ باشد."})
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValidationError({"ends_at": "زمان پایان تخفیف نمی‌تواند قبل از شروع آن باشد."})

    @property
    def is_active_now(self):
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "در انتظار پرداخت"),
        ("paid", "پرداخت شده"),
        ("processing", "در حال پردازش"),
        ("completed", "تکمیل شده"),
        ("canceled", "لغو شده"),
    ]

    user = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    total_amount = models.PositiveIntegerField(default=0)
    payment_ref = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("payment_ref",),
                condition=~Q(payment_ref=""),
                name="unique_non_empty_payment_ref",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "-created_at")),
            models.Index(fields=("status", "-created_at")),
        ]

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    product_name = models.CharField(max_length=200)
    variant_name = models.CharField(max_length=150, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.PositiveIntegerField(default=0)
    total_price = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="order_item_quantity_gte_1",
            ),
        ]
        indexes = [
            models.Index(fields=("order",)),
            models.Index(fields=("product",)),
        ]

    def clean(self):
        if self.variant_id and self.product_id:
            if self.variant.product_id != self.product_id:
                raise ValidationError("Variant باید متعلق به همین محصول باشد.")

    def __str__(self):
        return f"{self.product_name} - Order #{self.order.id}"


class DigitalCode(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="digital_codes",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="digital_codes",
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=500, unique=True)
    pin = models.CharField(max_length=200, blank=True)
    is_used = models.BooleanField(default=False)
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="digital_codes",
    )
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("product", "variant", "is_used")),
            models.Index(fields=("order_item",)),
        ]

    def clean(self):
        if self.variant and self.variant.product_id != self.product_id:
            raise ValidationError("Variant باید متعلق به همین محصول باشد.")
        if self.is_used and self.order_item_id is None:
            raise ValidationError("کد مصرف‌شده باید به یک آیتم سفارش متصل باشد.")

    def __str__(self):
        return f"{self.product.name} - {self.code}"
