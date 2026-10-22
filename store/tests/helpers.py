"""Shared test helpers for the Giftbaaz store suite."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model

from store.models import (
    Category,
    DigitalCode,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductVariant,
)

User = get_user_model()

PASSWORD = "StrongPass!234"


def make_user(username: str = "09120000000", **kwargs):
    defaults = {"email": f"{username}@example.com", "password": PASSWORD}
    defaults.update(kwargs)
    return User.objects.create_user(username=username, **defaults)


def make_category(name: str = "Category", slug: str = "category"):
    return Category.objects.create(name=name, slug=slug)


def make_product(
    *,
    name: str = "Gift Card",
    price: int | Decimal = 100_000,
    stock: int = 10,
    category: Category | None = None,
    **kwargs,
):
    return Product.objects.create(
        category=category,
        name=name,
        price=Decimal(price),
        stock=stock,
        **kwargs,
    )


def make_variant(
    product: Product,
    *,
    name: str = "10 USD",
    price: int | Decimal = 100_000,
    stock: int = 2,
    sku: str = "SKU-1",
    is_active: bool = True,
):
    return ProductVariant.objects.create(
        product=product,
        name=name,
        price=Decimal(price),
        stock=stock,
        sku=sku,
        is_active=is_active,
    )


def make_order(
    user,
    product: Product,
    *,
    quantity: int = 1,
    variant: ProductVariant | None = None,
    unit_price: int | Decimal | None = None,
    total_amount: int | Decimal | None = None,
    status: str = Order.STATUS_PENDING,
    authority: str | None = "AUTH-TEST",
    payment_status: str = Payment.STATUS_REDIRECTED,
    full_name: str = "Test Buyer",
    email: str = "buyer@example.com",
    phone: str = "09121234567",
):
    price = Decimal(unit_price if unit_price is not None else product.price)
    total = Decimal(total_amount if total_amount is not None else price * quantity)
    order = Order.objects.create(
        user=user,
        full_name=full_name,
        email=email,
        phone=phone,
        total_amount=total,
        status=status,
    )
    item = OrderItem.objects.create(
        order=order,
        product=product,
        variant=variant,
        product_name=product.name,
        variant_name=variant.name if variant else "",
        quantity=quantity,
        unit_price=price,
        total_price=total,
    )
    Payment.objects.create(
        order=order,
        amount=total,
        currency="IRR",
        gateway="zarinpal",
        authority=authority,
        status=payment_status,
    )
    return order, item


class FakeGateway:
    """Deterministic stand-in for the ZarinPal client."""

    start_url = "https://sandbox.zarinpal.test/pg/StartPay/"

    def __init__(self, create_result=None, verify_result=None):
        self.create_result = create_result
        self.verify_result = verify_result
        self.create_calls = []
        self.verify_calls = []

    def create_payment(self, **kwargs):
        self.create_calls.append(kwargs)
        if self.create_result is not None:
            return self.create_result
        from store.services.gateway import GatewayResult

        return GatewayResult(
            True,
            code="100",
            message="Success",
            authority="NEW-AUTHORITY",
            redirect_url=self.start_url + "NEW-AUTHORITY",
        )

    def verify_payment(self, *, amount_toman, authority):
        self.verify_calls.append((amount_toman, authority))
        if self.verify_result is not None:
            return self.verify_result
        from store.services.gateway import GatewayResult

        return GatewayResult(
            True,
            code="100",
            message="Paid",
            reference_id="REF-123",
            authority=authority,
        )


def digital_code(product, code, *, variant=None, **kwargs):
    return DigitalCode.objects.create(
        product=product,
        variant=variant,
        code=code,
        **kwargs,
    )
