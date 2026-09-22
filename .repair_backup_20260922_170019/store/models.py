from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.PositiveIntegerField()
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def final_price(self):
        discount = getattr(self, "discount", None)

        if discount and discount.is_active_now:
            discount_amount = self.price * discount.percent // 100
            return self.price - discount_amount

        return self.price
    
    @property
    def catalog_variants(self):
        if hasattr(self, "catalog_variants_cache"):
            return self.catalog_variants_cache

        return self.variants.filter(
            is_active=True
        )


    @property
    def catalog_price(self):
        variants = list(self.catalog_variants)

        if variants:
            available_variants = [
                variant
                for variant in variants
                if variant.stock > 0
            ]

            variants = available_variants or variants

            return min(
                variant.final_price
                for variant in variants
            )

        return self.final_price


    @property
    def catalog_old_price(self):
        variants = list(self.catalog_variants)

        if variants:
            available_variants = [
                variant
                for variant in variants
                if variant.stock > 0
            ]

            variants = available_variants or variants

            if self.discount and self.discount.is_active_now:
                old_price = min(
                    variant.price
                    for variant in variants
                )

                final_price = min(
                    variant.final_price
                    for variant in variants
                )

                if old_price > final_price:
                    return old_price

            return None

        if (
            self.discount
            and self.discount.is_active_now
            and self.price > self.final_price
        ):
            return self.price

        return None


    @property
    def catalog_has_stock(self):
        variants = list(self.catalog_variants)

        if variants:
            return any(
                variant.stock > 0
                for variant in variants
            )

        return self.stock > 0


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

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    @property
    def final_price(self):
        discount = getattr(self.product, "discount", None)

        if discount and discount.is_active_now:
            discount_amount = self.price * discount.percent // 100
            return self.price - discount_amount

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

    def __str__(self):
        return f"{self.product.name} - {self.percent}%"

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
    payment_ref = models.CharField(
        max_length=100,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

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
    variant_name = models.CharField(
        max_length=150,
        blank=True,
    )

    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.PositiveIntegerField(default=0)
    total_price = models.PositiveIntegerField(default=0)

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

    code = models.CharField(
        max_length=500,
        unique=True,
    )

    pin = models.CharField(
        max_length=200,
        blank=True,
    )

    is_used = models.BooleanField(default=False)

    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="digital_codes",
    )

    used_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    def clean(self):
        if self.variant and self.variant.product_id != self.product_id:
            raise ValidationError(
                "Variant باید متعلق به همین محصول باشد."
            )

    def __str__(self):
        return f"{self.product.name} - {self.code}"
