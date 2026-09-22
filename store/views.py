from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login,
    logout,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Prefetch
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone

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
from .utils import (
    deliver_digital_codes,
    get_item_price,
    get_item_stock,
)


def home(request):
    product_images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by(
            "-is_main",
            "id",
        ),
        to_attr="homepage_images",
    )

    products = (
        Product.objects
        .select_related("category", "discount")
        .prefetch_related(product_images)
        .order_by("-created_at")
    )

    featured_products = list(
        products
        .filter(discount__is_active=True)
        .order_by("-created_at")[:4]
    )

    featured_ids = {
        product.id
        for product in featured_products
    }

    if len(featured_products) < 4:
        extra_products = list(
            products
            .exclude(id__in=featured_ids)
            .order_by("-created_at")[
                :4 - len(featured_products)
            ]
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
    product_images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by(
            "-is_main",
            "id",
        ),
        to_attr="shop_images",
    )

    products = (
        Product.objects
        .select_related("category", "discount")
        .prefetch_related(product_images)
    )

    query = request.GET.get("q", "").strip()
    category_slug = request.GET.get(
        "category",
        "",
    ).strip()

    sort = request.GET.get(
        "sort",
        "newest",
    )

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
        )

    if category_slug:
        products = products.filter(
            category__slug=category_slug
        )

    if sort == "price_low":
        products = products.order_by("price")

    elif sort == "price_high":
        products = products.order_by("-price")

    elif sort == "name":
        products = products.order_by("name")

    else:
        products = products.order_by("-created_at")

    paginator = Paginator(
        products,
        12,
    )

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

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
    product_images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by(
            "-is_main",
            "id",
        ),
        to_attr="detail_images",
    )

    variants = Prefetch(
        "variants",
        queryset=ProductVariant.objects.filter(
            is_active=True,
        ).order_by("price"),
        to_attr="active_variants",
    )

    product = get_object_or_404(
        Product.objects
        .select_related(
            "category",
            "discount",
        )
        .prefetch_related(
            product_images,
            variants,
        ),
        pk=pk,
    )

    related_products = (
        Product.objects
        .filter(
            category=product.category,
        )
        .exclude(pk=product.pk)
        .select_related(
            "category",
            "discount",
        )
        .order_by("-created_at")[:4]
    )

    return render(
        request,
        "product_detail.html",
        {
            "product": product,
            "variants": product.active_variants,
            "related_products": related_products,
        },
    )


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("account")

    if request.method == "POST":
        form = SignUpForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(
                request,
                user,
            )

            messages.success(
                request,
                "حساب شما با موفقیت ساخته شد.",
            )

            return redirect("account")
    else:
        form = SignUpForm()

    return render(
        request,
        "signup.html",
        {
            "form": form,
        },
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect("account")

    if request.method == "POST":
        form = AuthenticationForm(
            request,
            data=request.POST,
        )

        if form.is_valid():
            user = form.get_user()

            login(
                request,
                user,
            )

            return redirect(
                request.GET.get(
                    "next",
                    "account",
                )
            )
    else:
        form = AuthenticationForm()

    return render(
        request,
        "login.html",
        {
            "form": form,
        },
    )


@login_required
def logout_view(request):
    if request.method == "POST":
        logout(request)

    return redirect("home")


@login_required
def account(request):
    orders = (
        Order.objects
        .filter(user=request.user)
        .order_by("-created_at")[:10]
    )

    return render(
        request,
        "account.html",
        {
            "orders": orders,
        },
    )


def get_cart_items(request):
    cart = request.session.get("cart", {})

    items = []
    total = 0

    for key, quantity in cart.items():
        try:
            product_id, variant_id = key.split(":", 1)
            quantity = int(quantity)

            if quantity <= 0:
                continue

        except (ValueError, TypeError):
            continue

        product = (
            Product.objects
            .select_related(
                "category",
                "discount",
            )
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by(
                        "-is_main",
                        "id",
                    ),
                    to_attr="cart_images",
                )
            )
            .filter(pk=product_id)
            .first()
        )

        if not product:
            continue

        variant = None

        if variant_id != "0":
            variant = product.variants.filter(
                pk=variant_id,
                is_active=True,
            ).first()

            if not variant:
                continue

        unit_price = get_item_price(
            product,
            variant,
        )

        item_total = unit_price * quantity

        image = (
            product.cart_images[0]
            if product.cart_images
            else None
        )

        items.append(
            {
                "key": key,
                "product": product,
                "variant": variant,
                "quantity": quantity,
                "unit_price": unit_price,
                "total": item_total,
                "image": image,
                "stock": get_item_stock(
                    product,
                    variant,
                ),
            }
        )

        total += item_total

    return items, total


def cart_view(request):
    items, total = get_cart_items(request)

    return render(
        request,
        "cart.html",
        {
            "items": items,
            "total": total,
        },
    )


def add_to_cart(request, pk):
    if request.method != "POST":
        return redirect(
            "product_detail",
            pk=pk,
        )

    product = get_object_or_404(
        Product,
        pk=pk,
    )

    variant_id = request.POST.get(
        "variant_id",
        "",
    )

    try:
        quantity = int(
            request.POST.get(
                "quantity",
                1,
            )
        )
    except ValueError:
        quantity = 1

    quantity = max(
        quantity,
        1,
    )

    active_variants = product.variants.filter(
        is_active=True,
    )

    variant = None

    if active_variants.exists():
        if not variant_id:
            messages.error(
                request,
                "لطفاً یک گزینه محصول را انتخاب کنید.",
            )

            return redirect(
                "product_detail",
                pk=pk,
            )

        variant = active_variants.filter(
            pk=variant_id,
        ).first()

        if not variant:
            messages.error(
                request,
                "گزینه انتخاب‌شده معتبر نیست.",
            )

            return redirect(
                "product_detail",
                pk=pk,
            )

    stock = get_item_stock(
        product,
        variant,
    )

    if stock <= 0:
        messages.error(
            request,
            "این محصول موجود نیست.",
        )

        return redirect(
            "product_detail",
            pk=pk,
        )

    quantity = min(
        quantity,
        stock,
    )

    cart = request.session.get(
        "cart",
        {},
    )

    key = f"{product.id}:{variant.id if variant else 0}"

    current_quantity = int(
        cart.get(
            key,
            0,
        )
    )

    cart[key] = min(
        current_quantity + quantity,
        stock,
    )

    request.session["cart"] = cart
    request.session.modified = True

    messages.success(
        request,
        "محصول به سبد خرید اضافه شد.",
    )

    return redirect("cart")


def update_cart(request):
    if request.method != "POST":
        return redirect("cart")

    cart = request.session.get(
        "cart",
        {},
    )

    for key in list(cart.keys()):
        field_name = f"quantity_{key}"

        if field_name not in request.POST:
            continue

        try:
            quantity = int(
                request.POST[field_name]
            )
        except ValueError:
            quantity = 1

        try:
            product_id, variant_id = key.split(
                ":",
                1,
            )
        except ValueError:
            cart.pop(key, None)
            continue

        product = Product.objects.filter(
            pk=product_id,
        ).first()

        if not product:
            cart.pop(key, None)
            continue

        variant = None

        if variant_id != "0":
            variant = product.variants.filter(
                pk=variant_id,
                is_active=True,
            ).first()

        if variant_id != "0" and not variant:
            cart.pop(key, None)
            continue

        stock = get_item_stock(
            product,
            variant,
        )

        if quantity <= 0 or stock <= 0:
            cart.pop(key, None)
        else:
            cart[key] = min(
                quantity,
                stock,
            )

    request.session["cart"] = cart
    request.session.modified = True

    messages.success(
        request,
        "سبد خرید به‌روزرسانی شد.",
    )

    return redirect("cart")


def remove_from_cart(request, key):
    cart = request.session.get(
        "cart",
        {},
    )

    cart.pop(
        key,
        None,
    )

    request.session["cart"] = cart
    request.session.modified = True

    return redirect("cart")


def clear_cart(request):
    if request.method == "POST":
        request.session["cart"] = {}
        request.session.modified = True

    return redirect("cart")


@login_required
def checkout(request):
    items, total = get_cart_items(request)

    if not items:
        messages.error(
            request,
            "سبد خرید شما خالی است.",
        )

        return redirect("shop")

    if request.method == "POST":
        form = CheckoutForm(
            request.POST,
        )

        if form.is_valid():
            with transaction.atomic():
                for item in items:
                    stock = get_item_stock(
                        item["product"],
                        item["variant"],
                    )

                    if item["quantity"] > stock:
                        messages.error(
                            request,
                            f"موجودی «{item['product'].name}» کافی نیست.",
                        )

                        return redirect("cart")

                order = Order.objects.create(
                    user=request.user,
                    full_name=form.cleaned_data[
                        "full_name"
                    ],
                    email=form.cleaned_data[
                        "email"
                    ],
                    phone=form.cleaned_data[
                        "phone"
                    ],
                    total_amount=total,
                )

                for item in items:
                    OrderItem.objects.create(
                        order=order,
                        product=item["product"],
                        variant=item["variant"],
                        product_name=item["product"].name,
                        variant_name=(
                            item["variant"].name
                            if item["variant"]
                            else ""
                        ),
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                        total_price=item["total"],
                    )

            return redirect(
                "payment",
                order_id=order.id,
            )
    else:
        form = CheckoutForm(
            initial={
                "email": request.user.email,
            }
        )

    return render(
        request,
        "checkout.html",
        {
            "form": form,
            "items": items,
            "total": total,
        },
    )


@login_required
def payment(request, order_id):
    order = get_object_or_404(
        Order,
        pk=order_id,
        user=request.user,
    )

    if order.status != "pending":
        return redirect(
            "order_detail",
            order_id=order.id,
        )

    return render(
        request,
        "payment.html",
        {
            "order": order,
        },
    )


@login_required
def payment_success(request, order_id):
    if request.method != "POST":
        return redirect(
            "payment",
            order_id=order_id,
        )

    with transaction.atomic():
        order = get_object_or_404(
            Order.objects.select_for_update(),
            pk=order_id,
            user=request.user,
        )

        if order.status != "pending":
            return redirect(
                "order_detail",
                order_id=order.id,
            )

        for item in order.items.select_related(
            "product",
            "variant",
        ):
            if item.variant:
                variant = (
                    ProductVariant.objects
                    .select_for_update()
                    .get(pk=item.variant_id)
                )

                if variant.stock < item.quantity:
                    order.status = "canceled"
                    order.save(
                        update_fields=["status"]
                    )

                    messages.error(
                        request,
                        "موجودی یکی از محصولات دیگر کافی نیست.",
                    )

                    return redirect("cart")

                variant.stock -= item.quantity
                variant.save(
                    update_fields=["stock"]
                )

            else:
                product = (
                    Product.objects
                    .select_for_update()
                    .get(pk=item.product_id)
                )

                if product.stock < item.quantity:
                    order.status = "canceled"
                    order.save(
                        update_fields=["status"]
                    )

                    messages.error(
                        request,
                        "موجودی یکی از محصولات دیگر کافی نیست.",
                    )

                    return redirect("cart")

                product.stock -= item.quantity
                product.save(
                    update_fields=["stock"]
                )

        order.status = "paid"
        order.payment_ref = (
            f"DEMO-{order.id}-{int(timezone.now().timestamp())}"
        )
        order.paid_at = timezone.now()

        delivered = deliver_digital_codes(order)

        order.status = (
            "completed"
            if delivered
            else "processing"
        )

        order.save(
            update_fields=[
                "status",
                "payment_ref",
                "paid_at",
            ]
        )

    request.session["cart"] = {}
    request.session.modified = True

    return redirect(
        "order_detail",
        order_id=order.id,
    )


@login_required
def orders(request):
    user_orders = (
        Order.objects
        .filter(user=request.user)
        .order_by("-created_at")
    )

    return render(
        request,
        "orders.html",
        {
            "orders": user_orders,
        },
    )


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects
        .prefetch_related(
            "items__digital_codes",
        ),
        pk=order_id,
        user=request.user,
    )

    return render(
        request,
        "order_detail.html",
        {
            "order": order,
        },
    )