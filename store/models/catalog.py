"""Catalog domain: categories, products, variants, images and discounts."""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

from .common import money_field


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return f"{reverse('shop')}?category={self.slug}"


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
    price = money_field()
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    is_bestseller = models.BooleanField(
        default=False,
        verbose_name="پرفروش",
        help_text="نمایش محصول در بخش پرفروش‌های صفحه اصلی.",
    )
    bestseller_priority = models.PositiveSmallIntegerField(
        default=100,
        verbose_name="اولویت پرفروش",
        help_text="عدد کمتر = نمایش زودتر در بخش پرفروش‌ها.",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("-created_at",)),
            models.Index(fields=("category",)),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="product_price_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("product_detail", args=[self.pk])

    def _active_variant_list(self) -> list[ProductVariant]:
        prefetched = getattr(self, "active_variants", None)
        if prefetched is not None:
            return list(prefetched)
        return list(self.variants.filter(is_active=True).order_by("price", "id"))

    @property
    def final_price(self) -> Decimal:
        price = Decimal(self.price)
        discount = getattr(self, "discount", None)
        if discount and discount.is_active_now:
            discount_amount = (
                price * Decimal(discount.percent) / Decimal(100)
            ).quantize(Decimal("1"), rounding=ROUND_FLOOR)
            return max(Decimal("0"), price - discount_amount)
        return price

    @property
    def catalog_has_stock(self) -> bool:
        """Whether the product can currently be added to the cart.

        Once a product has active variants, the cart requires a variant and the
        product-level stock is not a valid fallback.
        """

        variants = self._active_variant_list()
        if variants:
            return any(variant.stock > 0 for variant in variants)
        return self.stock > 0

    @property
    def catalog_price(self) -> Decimal:
        """Lowest variant price, preferring variants that are in stock."""

        variants = self._active_variant_list()
        if variants:
            available = [
                variant.final_price for variant in variants if variant.stock > 0
            ]
            prices = available or [variant.final_price for variant in variants]
            return min(prices)
        return self.final_price

    @property
    def catalog_old_price(self) -> Decimal | None:
        """Raw price matching the catalog price when a live discount exists."""

        discount = getattr(self, "discount", None)
        if not discount or not discount.is_active_now:
            return None
        variants = self._active_variant_list()
        if variants:
            available = [variant.price for variant in variants if variant.stock > 0]
            prices = available or [variant.price for variant in variants]
            return min(prices)
        return Decimal(self.price)


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    name = models.CharField(max_length=150)
    price = money_field()
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("price", "id")
        indexes = [
            models.Index(fields=("product", "is_active")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="variant_price_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} - {self.name}"

    @property
    def final_price(self) -> Decimal:
        price = Decimal(self.price)
        discount = getattr(self.product, "discount", None)
        if discount and discount.is_active_now:
            discount_amount = (
                price * Decimal(discount.percent) / Decimal(100)
            ).quantize(Decimal("1"), rounding=ROUND_FLOOR)
            return max(Decimal("0"), price - discount_amount)
        return price


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=200, blank=True)
    is_main = models.BooleanField(default=False)

    # MySQL/MariaDB do not support partial (conditional) unique indexes. The
    # "at most one main image" rule is enforced in save() under a row lock and
    # is covered by tests. Do not reintroduce a conditional UniqueConstraint
    # here: it would be silently skipped on MariaDB and would desynchronise the
    # migration state.

    def __str__(self) -> str:
        return f"{self.product.name} - Image"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            # Serialise image ordering per product on databases that support row
            # locks (MySQL/MariaDB/PostgreSQL). SQLite ignores the lock.
            if self.product_id:
                Product.objects.select_for_update().filter(pk=self.product_id).exists()
                siblings = ProductImage.objects.filter(product_id=self.product_id)
                if self.pk:
                    siblings = siblings.exclude(pk=self.pk)
                if self.is_main:
                    siblings.filter(is_main=True).update(is_main=False)
                elif not siblings.filter(is_main=True).exists():
                    # The first uploaded image becomes the main image.
                    self.is_main = True
            super().save(*args, **kwargs)


class Discount(models.Model):
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="discount",
    )
    percent = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
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

    def __str__(self) -> str:
        return f"{self.product.name} - {self.percent}%"

    def clean(self) -> None:
        if not 0 <= self.percent <= 100:
            raise ValidationError({"percent": "درصد تخفیف باید بین ۰ تا ۱۰۰ باشد."})
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValidationError(
                {"ends_at": "زمان پایان تخفیف نمی‌تواند قبل از شروع آن باشد."}
            )

    @property
    def is_active_now(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True
