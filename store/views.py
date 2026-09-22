from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import CheckoutForm, SignUpForm
from .models import (
    Category,
    DigitalCode,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductVariant,
)
from .utils import deliver_digital_codes, get_item_price, get_item_stock


def active_discount_q(now=None):
    now = now or timezone.now()
    return (
        Q(discount__is_active=True)
        & (Q(discount__starts_at__isnull=True) | Q(discount__starts_at__lte=now))
        & (Q(discount__ends_at__isnull=True) | Q(discount__ends_at__gte=now))
    )


def product_queryset():
    product_images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("-is_main", "id"),
        to_attr="display_images",
    )
    active_variants = Prefetch(
        "variants",
        queryset=ProductVariant.objects.filter(is_active=True).order_by("price", "id"),
        to_attr="active_variants",
    )
    return (
        Product.objects.select_related("category", "discount")
        .prefetch_related(product_images, active_variants)
    )


def home(request):
    products = product_queryset().order_by("-created_at", "-id")
    featured_products = list(products.filter(active_discount_q())[:4])
    featured_ids = {product.id for product in featured_products}

    if len(featured_products) < 4:
        extra_products = list(
            products.exclude(id__in=featured_ids)[: 4 - len(featured_products)]
        )
        featured_products.extend(extra_products)

    new_products = list(products[:4])
    categories = Category.objects.order_by("name")[:5]

    return render(
        request,
        "home.html",
        {
            "categories": categories,
            "featured_products": featured_products,
            "new_products": new_products,
        },
    )


def shop(request):
    products = product_queryset()
    query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "").strip()
    sort = request.GET.get("sort", "newest")

    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    if category_slug:
        products = products.filter(category__slug=category_slug)

    if sort == "price_low":
        # Database-level sorting remains stable and pagination-safe.
        products = products.order_by("price", "id")
    elif sort == "price_high":
        products = products.order_by("-price", "-id")
    elif sort == "name":
        products = products.order_by("name", "id")
    else:
        products = products.order_by("-created_at", "-id")

    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    categories = Category.objects.order_by("name")

    return render(
        request,
        "shop.html",
        {
            "page_obj": page_obj,
            "categories": categories,
            "query": query,
            "selected_category": category_slug,
            "selected_sort": sort,
        },
    )


def product_detail(request, pk):
    product = get_object_or_404(product_queryset(), pk=pk)
    related_products = (
        product_queryset()
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .order_by("-created_at", "-id")[:4]
    )
    variants = list(getattr(product, "active_variants", []))
    return render(
        request,
        "product_detail.html",
        {
            "product": product,
            "variants": variants,
            "related_products": related_products,
        },
    )


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("account")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "حساب شما با موفقیت ساخته شد.")
        return redirect("account")
    return render(request, "signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("account")

    form = AuthenticationForm(
        request,
        data=request.POST if request.method == "POST" else None,
    )
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("account")

    return render(
        request,
        "login.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")


@login_required
def account(request):
    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related("items")
        .order_by("-created_at", "-id")[:10]
    )
    return render(request, "account.html", {"orders": orders})


def _safe_positive_int(value, default=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _parse_cart_key(key):
    try:
        product_id, variant_id = str(key).split(":", 1)
        product_id = int(product_id)
        variant_id = int(variant_id)
    except (TypeError, ValueError):
        return None
    if product_id <= 0 or variant_id < 0:
        return None
    return product_id, variant_id


def get_cart_items(request, *, lock=False):
    cart = request.session.get("cart", {})
    if not isinstance(cart, dict) or not cart:
        return [], 0

    entries = []
    product_ids = set()
    for key, raw_quantity in list(cart.items()):
        parsed = _parse_cart_key(key)
        if parsed is None:
            continue
        quantity = _safe_positive_int(raw_quantity, 0)
        if quantity <= 0:
            continue
        product_id, variant_id = parsed
        entries.append((str(key), product_id, variant_id, quantity))
        product_ids.add(product_id)

    if not entries:
        return [], 0

    image_prefetch = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("-is_main", "id"),
        to_attr="display_images",
    )
    variant_queryset = ProductVariant.objects.filter(is_active=True).order_by("price", "id")
    if lock:
        variant_queryset = variant_queryset.select_for_update()

    variant_prefetch = Prefetch(
        "variants",
        queryset=variant_queryset,
        to_attr="cart_variants",
    )

    products_query = (
        Product.objects.filter(id__in=product_ids)
        .select_related("category", "discount")
        .prefetch_related(image_prefetch, variant_prefetch)
    )
    if lock:
        products_query = products_query.select_for_update()

    products = products_query
    products_by_id = {product.id: product for product in products}
    items = []
    total = 0
    cleaned_cart = {}

    for key, product_id, variant_id, quantity in entries:
        product = products_by_id.get(product_id)
        if not product:
            continue

        variants_by_id = {
            variant.id: variant for variant in getattr(product, "cart_variants", [])
        }
        variant = variants_by_id.get(variant_id) if variant_id else None
        if variant_id and not variant:
            continue

        stock = get_item_stock(product, variant)
        quantity = min(quantity, stock)
        if quantity <= 0:
            continue

        unit_price = get_item_price(product, variant)
        item_total = unit_price * quantity
        images = getattr(product, "display_images", [])
        image = images[0] if images else None
        cleaned_cart[key] = quantity
        items.append(
            {
                "key": key,
                "product": product,
                "variant": variant,
                "quantity": quantity,
                "unit_price": unit_price,
                "total": item_total,
                "image": image,
                "stock": stock,
            }
        )
        total += item_total

    if cleaned_cart != cart:
        request.session["cart"] = cleaned_cart
        request.session.modified = True

    return items, total


@login_required if False else lambda f: f

def cart_view(request):
    items, total = get_cart_items(request)
    return render(request, "cart.html", {"items": items, "total": total})


@require_POST
def add_to_cart(request, pk):
    product = get_object_or_404(Product.objects.prefetch_related("variants"), pk=pk)
    raw_variant_id = request.POST.get("variant_id", "")
    quantity = _safe_positive_int(request.POST.get("quantity", 1), 1)

    active_variants = product.variants.filter(is_active=True)
    variant = None
    if active_variants.exists():
        try:
            variant = active_variants.get(pk=int(raw_variant_id))
        except (TypeError, ValueError, ProductVariant.DoesNotExist):
            messages.error(request, "گزینه انتخاب‌شده معتبر نیست.")
            return redirect("product_detail", pk=pk)
    elif raw_variant_id not in {"", "0"}:
        messages.error(request, "گزینه انتخاب‌شده معتبر نیست.")
        return redirect("product_detail", pk=pk)

    stock = get_item_stock(product, variant)
    if stock <= 0:
        messages.error(request, "این محصول موجود نیست.")
        return redirect("product_detail", pk=pk)

    cart = request.session.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}

    key = f"{product.id}:{variant.id if variant else 0}"
    current_quantity = _safe_positive_int(cart.get(key, 0), 0)
    cart[key] = min(current_quantity + quantity, stock)
    request.session["cart"] = cart
    request.session.modified = True
    messages.success(request, "محصول به سبد خرید اضافه شد.")
    return redirect("cart")


@require_POST
def update_cart(request):
    cart = request.session.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}

    cleaned_cart = {}
    product_ids = []
    parsed_keys = {}
    for key in cart:
        parsed = _parse_cart_key(key)
        if parsed:
            parsed_keys[key] = parsed
            product_ids.append(parsed[0])

    products = {
        product.id: product
        for product in Product.objects.filter(id__in=set(product_ids)).select_related("discount")
    }

    for key, (product_id, variant_id) in parsed_keys.items():
        field_name = f"quantity_{key}"
        if field_name not in request.POST:
            cleaned_cart[key] = cart[key]
            continue

        quantity = _safe_positive_int(request.POST.get(field_name), 0)
        product = products.get(product_id)
        if not product:
            continue

        variant = None
        if variant_id:
            variant = product.variants.filter(pk=variant_id, is_active=True).first()
            if not variant:
                continue

        stock = get_item_stock(product, variant)
        if quantity > 0 and stock > 0:
            cleaned_cart[key] = min(quantity, stock)

    request.session["cart"] = cleaned_cart
    request.session.modified = True
    messages.success(request, "سبد خرید به‌روزرسانی شد.")
    return redirect("cart")


@require_POST
def remove_from_cart(request, key):
    cart = request.session.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}
    cart.pop(key, None)
    request.session["cart"] = cart
    request.session.modified = True
    return redirect("cart")


@require_POST
def clear_cart(request):
    request.session["cart"] = {}
    request.session.modified = True
    return redirect("cart")


@login_required
def checkout(request):
    items, total = get_cart_items(request)
    if not items:
        messages.error(request, "سبد خرید شما خالی است.")
        return redirect("shop")

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Lock and re-read everything so price and stock are current at order creation.
                locked_items, locked_total = get_cart_items(request, lock=True)
                if not locked_items:
                    messages.error(request, "سبد خرید شما دیگر موجود نیست.")
                    return redirect("cart")

                order = Order.objects.create(
                    user=request.user,
                    full_name=form.cleaned_data["full_name"],
                    email=form.cleaned_data["email"],
                    phone=form.cleaned_data["phone"],
                    total_amount=locked_total,
                )
                OrderItem.objects.bulk_create(
                    [
                        OrderItem(
                            order=order,
                            product=item["product"],
                            variant=item["variant"],
                            product_name=item["product"].name,
                            variant_name=item["variant"].name if item["variant"] else "",
                            quantity=item["quantity"],
                            unit_price=item["unit_price"],
                            total_price=item["total"],
                        )
                        for item in locked_items
                    ]
                )
            return redirect("payment", order_id=order.id)
    else:
        form = CheckoutForm(initial={"email": request.user.email})

    return render(
        request,
        "checkout.html",
        {"form": form, "items": items, "total": total},
    )


@login_required
def payment(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    if order.status != "pending":
        return redirect("order_detail", order_id=order.id)
    return render(request, "payment.html", {"order": order})


@login_required
@require_POST
def payment_success(request, order_id):
    # LOCAL/DEMO payment completion only. A real gateway callback must verify the gateway result.
    with transaction.atomic():
        order = get_object_or_404(
            Order.objects.select_for_update(),
            pk=order_id,
            user=request.user,
        )
        if order.status != "pending":
            return redirect("order_detail", order_id=order.id)

        for item in order.items.select_related("product", "variant"):
            if item.variant_id:
                variant = ProductVariant.objects.select_for_update().get(pk=item.variant_id)
                if not variant.is_active or variant.stock < item.quantity:
                    order.status = "canceled"
                    order.save(update_fields=["status"])
                    messages.error(request, "موجودی یکی از گزینه‌های محصول دیگر کافی نیست.")
                    return redirect("cart")
                variant.stock -= item.quantity
                variant.save(update_fields=["stock"])
            else:
                product = Product.objects.select_for_update().get(pk=item.product_id)
                if product.stock < item.quantity:
                    order.status = "canceled"
                    order.save(update_fields=["status"])
                    messages.error(request, "موجودی یکی از محصولات دیگر کافی نیست.")
                    return redirect("cart")
                product.stock -= item.quantity
                product.save(update_fields=["stock"])

        now = timezone.now()
        order.payment_ref = f"DEMO-{order.id}-{int(now.timestamp())}"
        order.paid_at = now
        delivered = deliver_digital_codes(order)
        order.status = "completed" if delivered else "processing"
        order.save(update_fields=["status", "payment_ref", "paid_at"])

    request.session["cart"] = {}
    request.session.modified = True
    return redirect("order_detail", order_id=order.id)


@login_required
def orders(request):
    queryset = Order.objects.filter(user=request.user).order_by("-created_at", "-id")
    paginator = Paginator(queryset, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "orders.html", {"page_obj": page_obj})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__digital_codes"),
        pk=order_id,
        user=request.user,
    )
    return render(request, "order_detail.html", {"order": order})
