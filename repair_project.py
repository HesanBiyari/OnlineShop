from pathlib import Path
from datetime import datetime
import re
import shutil

ROOT = Path(__file__).resolve().parent
BACKUP = ROOT / f".repair_backup_{datetime.now():%Y%m%d_%H%M%S}"
BACKUP.mkdir(parents=True, exist_ok=True)


def backup(rel):
    src = ROOT / rel
    if src.exists():
        dst = BACKUP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def write(rel, content):
    backup(rel)
    dst = ROOT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")


def replace_between(text, start, end, replacement):
    a = text.index(start)
    b = text.index(end, a)
    return text[:a] + replacement + text[b:]


# ------------------------------------------------------------
# 1) MODELS
# ------------------------------------------------------------
models = r'''from django.core.exceptions import ValidationError
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
        cached = getattr(self, "catalog_variants_cache", None)
        if cached is not None:
            return cached
        return self.variants.filter(is_active=True)

    @property
    def catalog_price(self):
        variants = list(self.catalog_variants)
        if variants:
            available = [v for v in variants if v.stock > 0]
            variants = available or variants
            return min(v.final_price for v in variants)
        return self.final_price

    @property
    def catalog_old_price(self):
        variants = list(self.catalog_variants)
        if variants:
            available = [v for v in variants if v.stock > 0]
            variants = available or variants
            if self.discount and self.discount.is_active_now:
                old_price = min(v.price for v in variants)
                new_price = min(v.final_price for v in variants)
                return old_price if old_price > new_price else None
            return None
        if self.discount and self.discount.is_active_now and self.price > self.final_price:
            return self.price
        return None

    @property
    def catalog_has_stock(self):
        variants = list(self.catalog_variants)
        if variants:
            return any(v.stock > 0 for v in variants)
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
    payment_ref = models.CharField(max_length=100, blank=True)
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
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
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

    def clean(self):
        if self.variant and self.variant.product_id != self.product_id:
            raise ValidationError("Variant باید متعلق به همین محصول باشد.")

    def __str__(self):
        return f"{self.product.name} - {self.code}"
'''
write("store/models.py", models)


# ------------------------------------------------------------
# 2) UTILS
# ------------------------------------------------------------
utils = r'''from django.utils import timezone

from .models import DigitalCode


def get_item_price(product, variant=None):
    return variant.final_price if variant else product.final_price


def get_item_stock(product, variant=None):
    return variant.stock if variant else product.stock


def deliver_digital_codes(order):
    all_delivered = True

    for item in order.items.select_related("product", "variant"):
        existing_codes = item.digital_codes.count()
        needed = item.quantity - existing_codes
        if needed <= 0:
            continue

        filters = {
            "product": item.product,
            "is_used": False,
            "order_item__isnull": True,
        }

        if item.variant:
            filters["variant"] = item.variant
        else:
            filters["variant__isnull"] = True

        codes = list(
            DigitalCode.objects
            .select_for_update()
            .filter(**filters)
            .order_by("id")[:needed]
        )

        if len(codes) < needed:
            all_delivered = False

        for code in codes:
            code.is_used = True
            code.used_at = timezone.now()
            code.order_item = item
            code.save(
                update_fields=[
                    "is_used",
                    "used_at",
                    "order_item",
                ]
            )

    return all_delivered
'''
write("store/utils.py", utils)


# ------------------------------------------------------------
# 3) VIEWS - patch only the broken/fragile functions in the current file
# ------------------------------------------------------------
views_path = ROOT / "store/views.py"
backup("store/views.py")
views = views_path.read_text(encoding="utf-8")

views = views.replace(
    "from django.db.models import Q, Prefetch",
    "from django.db.models import Min, Prefetch, Q\nfrom django.db.models.functions import Coalesce",
)
views = views.replace(
    "from django.utils import timezone",
    "from django.utils import timezone\nfrom django.utils.http import url_has_allowed_host_and_scheme",
)

home_fn = r'''def home(request):
    product_images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("-is_main", "id"),
        to_attr="homepage_images",
    )
    catalog_variants = Prefetch(
        "variants",
        queryset=ProductVariant.objects.filter(is_active=True).order_by("price"),
        to_attr="catalog_variants_cache",
    )

    products = (
        Product.objects
        .select_related("category", "discount")
        .prefetch_related(product_images, catalog_variants)
        .order_by("-created_at")
    )

    now = timezone.now()
    featured_products = list(
        products
        .filter(discount__is_active=True)
        .filter(
            Q(discount__starts_at__isnull=True)
            | Q(discount__starts_at__lte=now)
        )
        .filter(
            Q(discount__ends_at__isnull=True)
            | Q(discount__ends_at__gte=now)
        )
        .order_by("-created_at")[:4]
    )

    featured_ids = {product.id for product in featured_products}

    if len(featured_products) < 4:
        extra_products = list(
            products
            .exclude(id__in=featured_ids)
            .order_by("-created_at")[:4 - len(featured_products)]
        )
        featured_products.extend(extra_products)

    return render(
        request,
        "home.html",
        {
            "categories": Category.objects.order_by("name")[:5],
            "featured_products": featured_products,
            "new_products": list(products[:4]),
        },
    )


'''
views = replace_between(views, "def home(request):", "def shop(request):", home_fn)

shop_fn = r'''def shop(request):
    product_images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("-is_main", "id"),
        to_attr="shop_images",
    )
    catalog_variants = Prefetch(
        "variants",
        queryset=ProductVariant.objects.filter(is_active=True).order_by("price"),
        to_attr="catalog_variants_cache",
    )

    products = (
        Product.objects
        .select_related("category", "discount")
        .prefetch_related(product_images, catalog_variants)
        .annotate(
            min_variant_price=Min(
                "variants__price",
                filter=Q(variants__is_active=True),
            )
        )
        .annotate(
            catalog_sort_price=Coalesce(
                "min_variant_price",
                "price",
            )
        )
    )

    query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "").strip()
    sort = request.GET.get("sort", "newest")

    if sort not in {"newest", "price_low", "price_high", "name"}:
        sort = "newest"

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
        )

    if category_slug:
        products = products.filter(category__slug=category_slug)

    if sort == "price_low":
        products = products.order_by("catalog_sort_price", "-created_at")
    elif sort == "price_high":
        products = products.order_by("-catalog_sort_price", "-created_at")
    elif sort == "name":
        products = products.order_by("name", "-created_at")
    else:
        products = products.order_by("-created_at")

    page_obj = Paginator(products, 12).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "shop.html",
        {
            "page_obj": page_obj,
            "categories": Category.objects.order_by("name"),
            "search_query": query,
            "selected_category": category_slug,
            "selected_sort": sort,
        },
    )


'''
views = replace_between(views, "def shop(request):", "def product_detail(request, pk):", shop_fn)

product_fn = r'''def product_detail(request, pk):
    product_images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("-is_main", "id"),
        to_attr="detail_images",
    )
    variants = Prefetch(
        "variants",
        queryset=ProductVariant.objects.filter(is_active=True).order_by("price"),
        to_attr="active_variants",
    )

    product = get_object_or_404(
        Product.objects
        .select_related("category", "discount")
        .prefetch_related(product_images, variants),
        pk=pk,
    )

    related_products = (
        Product.objects
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .select_related("category", "discount")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.order_by("-is_main", "id"),
                to_attr="related_images",
            ),
            Prefetch(
                "variants",
                queryset=ProductVariant.objects.filter(is_active=True).order_by("price"),
                to_attr="catalog_variants_cache",
            ),
        )
        .order_by("-created_at")[:4]
    )

    has_available_variants = any(
        variant.stock > 0
        for variant in product.active_variants
    )

    return render(
        request,
        "product_detail.html",
        {
            "product": product,
            "variants": product.active_variants,
            "has_available_variants": has_available_variants,
            "related_products": related_products,
        },
    )


'''
views = replace_between(views, "def product_detail(request, pk):", "def signup_view(request):", product_fn)

login_fn = r'''def login_view(request):
    if request.user.is_authenticated:
        return redirect("account")

    next_url = request.POST.get("next") or request.GET.get("next")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())

            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect("account")
    else:
        form = AuthenticationForm()

    return render(
        request,
        "login.html",
        {
            "form": form,
            "next": next_url or "",
        },
    )


'''
views = replace_between(views, "def login_view(request):", "@login_required\ndef logout_view", login_fn)

cart_fn = r'''def get_cart_items(request):
    cart = request.session.get("cart", {})
    items = []
    total = 0
    invalid_keys = set()

    for key, raw_quantity in cart.items():
        try:
            product_id, variant_id = key.split(":", 1)
            quantity = int(raw_quantity)
            if quantity <= 0:
                raise ValueError
        except (ValueError, TypeError):
            invalid_keys.add(key)
            continue

        product = (
            Product.objects
            .select_related("category", "discount")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_main", "id"),
                    to_attr="cart_images",
                )
            )
            .filter(pk=product_id)
            .first()
        )

        if not product:
            invalid_keys.add(key)
            continue

        variant = None
        if variant_id != "0":
            variant = product.variants.filter(
                pk=variant_id,
                is_active=True,
            ).first()
            if not variant:
                invalid_keys.add(key)
                continue

        stock = get_item_stock(product, variant)
        if stock <= 0:
            invalid_keys.add(key)
            continue

        quantity = min(quantity, stock)
        unit_price = get_item_price(product, variant)
        item_total = unit_price * quantity

        items.append({
            "key": key,
            "product": product,
            "variant": variant,
            "quantity": quantity,
            "unit_price": unit_price,
            "total": item_total,
            "image": product.cart_images[0] if product.cart_images else None,
            "stock": stock,
        })
        total += item_total

    if invalid_keys:
        request.session["cart"] = {
            key: quantity
            for key, quantity in cart.items()
            if key not in invalid_keys
        }
        request.session.modified = True

    return items, total


'''
views = replace_between(views, "def get_cart_items(request):", "def cart_view(request):", cart_fn)

remove_fn = r'''def remove_from_cart(request, key):
    if request.method != "POST":
        return redirect("cart")

    cart = request.session.get("cart", {})
    cart.pop(key, None)
    request.session["cart"] = cart
    request.session.modified = True
    return redirect("cart")


'''
views = replace_between(views, "def remove_from_cart(request, key):", "def clear_cart(request):", remove_fn)

views_path.write_text(views, encoding="utf-8")


# ------------------------------------------------------------
# 4) BASE TEMPLATE
# ------------------------------------------------------------
base = r'''{% load static %}
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Giftweb{% endblock %}</title>
    <link rel="stylesheet" href="{% static 'css/style.css' %}">
</head>
<body>
<header class="site-header">
    <div class="container header-content">
        <a href="{% url 'home' %}" class="logo">Giftweb</a>

        <form class="search-box" action="{% url 'shop' %}" method="get">
            <input type="text" name="q" value="{{ request.GET.q }}" placeholder="جستجوی محصول...">
            <button type="submit">جستجو</button>
        </form>

        <div class="header-actions">
            {% if user.is_authenticated %}
                <a href="{% url 'account' %}">حساب من</a>
                <form method="post" action="{% url 'logout' %}">
                    {% csrf_token %}
                    <button type="submit" class="header-button">خروج</button>
                </form>
            {% else %}
                <a href="{% url 'login' %}">ورود</a>
                <a href="{% url 'signup' %}">ثبت‌نام</a>
            {% endif %}
            <a href="{% url 'cart' %}">
                سبد خرید{% if cart_count %} ({{ cart_count }}){% endif %}
            </a>
        </div>
    </div>
</header>

<nav class="navbar">
    <div class="container">
        <div class="nav-links">
            <a href="{% url 'home' %}">خانه</a>
            <a href="{% url 'shop' %}">فروشگاه</a>
            <a href="{% url 'shop' %}">گیفت کارت</a>
            <a href="{% url 'shop' %}">دسته‌بندی‌ها</a>
        </div>
    </div>
</nav>

{% if messages %}
    <div class="messages container">
        {% for message in messages %}
            <div class="message {{ message.tags }}">{{ message }}</div>
        {% endfor %}
    </div>
{% endif %}

<main>{% block content %}{% endblock %}</main>

<footer class="site-footer">
    <div class="container footer-content">
        <div>
            <h3>Giftweb</h3>
            <p>فروشگاه محصولات دیجیتال</p>
        </div>
        <div>
            <h4>دسترسی سریع</h4>
            <a href="{% url 'home' %}">خانه</a>
            <a href="{% url 'shop' %}">فروشگاه</a>
            <a href="{% url 'account' %}">حساب کاربری</a>
        </div>
        <div>
            <h4>راهنما</h4>
            <a href="{% url 'shop' %}">محصولات</a>
            <a href="{% url 'cart' %}">سبد خرید</a>
        </div>
    </div>
    <div class="footer-bottom">
        <p>© 2026 Giftweb</p>
    </div>
</footer>
</body>
</html>
'''
write("templates/base.html", base)


# ------------------------------------------------------------
# 5) SHOP TEMPLATE
# ------------------------------------------------------------
shop = r'''{% extends "base.html" %}

{% block title %}فروشگاه | Giftweb{% endblock %}

{% block content %}
<section class="shop-page">
    <div class="container">
        <div class="shop-header">
            <div>
                <span class="section-label">فروشگاه</span>
                <h1>محصولات دیجیتال</h1>
                {% if search_query %}
                    <p>نتایج جستجو برای: <strong>{{ search_query }}</strong></p>
                {% else %}
                    <p>محصولات مورد نیازت را پیدا کن.</p>
                {% endif %}
            </div>
        </div>

        <div class="shop-toolbar">
            <form method="get" class="shop-search">
                {% if selected_category %}
                    <input type="hidden" name="category" value="{{ selected_category }}">
                {% endif %}
                {% if selected_sort != "newest" %}
                    <input type="hidden" name="sort" value="{{ selected_sort }}">
                {% endif %}
                <input type="text" name="q" value="{{ search_query }}" placeholder="جستجوی محصول...">
                <button type="submit">جستجو</button>
            </form>

            <form method="get" class="sort-form">
                {% if search_query %}
                    <input type="hidden" name="q" value="{{ search_query }}">
                {% endif %}
                {% if selected_category %}
                    <input type="hidden" name="category" value="{{ selected_category }}">
                {% endif %}
                <select name="sort" onchange="this.form.submit()">
                    <option value="newest" {% if selected_sort == "newest" %}selected{% endif %}>جدیدترین</option>
                    <option value="price_low" {% if selected_sort == "price_low" %}selected{% endif %}>ارزان‌ترین</option>
                    <option value="price_high" {% if selected_sort == "price_high" %}selected{% endif %}>گران‌ترین</option>
                    <option value="name" {% if selected_sort == "name" %}selected{% endif %}>نام</option>
                </select>
            </form>
        </div>

        <div class="shop-layout">
            <aside class="shop-sidebar">
                <div class="filter-box">
                    <h3>دسته‌بندی‌ها</h3>
                    <div class="category-filters">
                        <a href="{% url 'shop' %}{% if search_query %}?q={{ search_query|urlencode }}{% endif %}{% if selected_sort != 'newest' %}{% if search_query %}&{% else %}?{% endif %}sort={{ selected_sort }}{% endif %}"
                           class="{% if not selected_category %}active{% endif %}">
                            همه محصولات
                        </a>
                        {% for category in categories %}
                            <a href="{% url 'shop' %}?category={{ category.slug }}{% if search_query %}&q={{ search_query|urlencode }}{% endif %}{% if selected_sort != 'newest' %}&sort={{ selected_sort }}{% endif %}"
                               class="{% if selected_category == category.slug %}active{% endif %}">
                                {{ category.name }}
                            </a>
                        {% empty %}
                            <p>دسته‌بندی‌ای وجود ندارد.</p>
                        {% endfor %}
                    </div>
                </div>
            </aside>

            <div class="shop-products">
                <div class="shop-results">
                    <span>{{ page_obj.paginator.count }} محصول</span>
                </div>

                <div class="products-grid shop-products-grid">
                    {% for product in page_obj %}
                        <article class="product-card">
                            <div class="product-image">
                                {% if product.discount and product.discount.is_active_now %}
                                    <span class="product-badge">
                                        {{ product.discount.percent }}٪ تخفیف
                                    </span>
                                {% endif %}

                                {% with image=product.shop_images|first %}
                                    {% if image %}
                                        <img src="{{ image.image.url }}"
                                             alt="{{ image.alt_text|default:product.name }}">
                                    {% else %}
                                        <div class="product-placeholder">🎁</div>
                                    {% endif %}
                                {% endwith %}
                            </div>

                            <div class="product-info">
                                {% if product.category %}
                                    <span class="product-category">{{ product.category.name }}</span>
                                {% endif %}

                                <h3>{{ product.name }}</h3>

                                <div class="product-price">
                                    {% if product.catalog_old_price %}
                                        <span class="old-price">
                                            {{ product.catalog_old_price|floatformat:0 }} تومان
                                        </span>
                                    {% endif %}
                                    <strong>
                                        {% if product.catalog_variants %}از {% endif %}
                                        {{ product.catalog_price|floatformat:0 }} تومان
                                    </strong>
                                </div>

                                {% if product.catalog_has_stock %}
                                    <span class="stock-status available">موجود</span>
                                {% else %}
                                    <span class="stock-status unavailable">ناموجود</span>
                                {% endif %}

                                <a href="{% url 'product_detail' product.id %}" class="product-button">
                                    مشاهده محصول
                                </a>
                            </div>
                        </article>
                    {% empty %}
                        <div class="no-products">
                            {% if search_query %}
                                محصولی برای «{{ search_query }}» پیدا نشد.
                            {% else %}
                                محصولی برای نمایش وجود ندارد.
                            {% endif %}
                        </div>
                    {% endfor %}
                </div>

                {% if page_obj.paginator.num_pages > 1 %}
                    <div class="pagination">
                        {% if page_obj.has_previous %}
                            <a href="?{% if search_query %}q={{ search_query|urlencode }}&{% endif %}{% if selected_category %}category={{ selected_category }}&{% endif %}sort={{ selected_sort }}&page={{ page_obj.previous_page_number }}">قبلی</a>
                        {% endif %}

                        {% for num in page_obj.paginator.page_range %}
                            {% if page_obj.number == num %}
                                <span class="active">{{ num }}</span>
                            {% else %}
                                <a href="?{% if search_query %}q={{ search_query|urlencode }}&{% endif %}{% if selected_category %}category={{ selected_category }}&{% endif %}sort={{ selected_sort }}&page={{ num }}">{{ num }}</a>
                            {% endif %}
                        {% endfor %}

                        {% if page_obj.has_next %}
                            <a href="?{% if search_query %}q={{ search_query|urlencode }}&{% endif %}{% if selected_category %}category={{ selected_category }}&{% endif %}sort={{ selected_sort }}&page={{ page_obj.next_page_number }}">بعدی</a>
                        {% endif %}
                    </div>
                {% endif %}
            </div>
        </div>
    </div>
</section>
{% endblock %}
'''
write("store/templates/shop.html", shop)


# ------------------------------------------------------------
# 6) PRODUCT DETAIL TEMPLATE
# ------------------------------------------------------------
product_detail = r'''{% extends "base.html" %}

{% block title %}{{ product.name }} | Giftweb{% endblock %}

{% block content %}
<section class="product-detail-page">
    <div class="container">
        <div class="product-detail">
            <div class="product-detail-image">
                {% if product.detail_images %}
                    <img src="{{ product.detail_images.0.image.url }}"
                         alt="{{ product.detail_images.0.alt_text|default:product.name }}">
                {% else %}
                    <div class="product-placeholder">🎁</div>
                {% endif %}
            </div>

            <div class="product-detail-info">
                {% if product.category %}
                    <span class="product-category">{{ product.category.name }}</span>
                {% endif %}

                <h1>{{ product.name }}</h1>
                <div class="product-description">{{ product.description|linebreaks }}</div>

                <form method="post"
                      action="{% url 'add_to_cart' product.id %}"
                      class="product-buy-form">
                    {% csrf_token %}

                    {% if variants %}
                        <div class="variant-selection">
                            <label for="variant_id">انتخاب گزینه</label>
                            <select name="variant_id" id="variant_id" required>
                                <option value="">انتخاب کنید</option>
                                {% for variant in variants %}
                                    <option value="{{ variant.id }}" {% if variant.stock <= 0 %}disabled{% endif %}>
                                        {{ variant.name }} - {{ variant.final_price|floatformat:0 }} تومان
                                        {% if variant.stock <= 0 %}- ناموجود{% endif %}
                                    </option>
                                {% endfor %}
                            </select>
                        </div>

                        {% if not has_available_variants %}
                            <div class="stock-status unavailable">همه گزینه‌های این محصول ناموجود هستند.</div>
                        {% endif %}
                    {% else %}
                        <div class="product-detail-price">
                            {% if product.catalog_old_price %}
                                <span class="old-price">{{ product.catalog_old_price|floatformat:0 }} تومان</span>
                            {% endif %}
                            <strong>{{ product.catalog_price|floatformat:0 }} تومان</strong>
                        </div>
                    {% endif %}

                    <div class="quantity-row">
                        <label for="quantity">تعداد</label>
                        <input type="number" name="quantity" id="quantity" value="1" min="1" max="100">
                    </div>

                    {% if variants %}
                        {% if has_available_variants %}
                            <button type="submit" class="product-button">افزودن به سبد خرید</button>
                        {% else %}
                            <button type="button" class="product-button" disabled>ناموجود</button>
                        {% endif %}
                    {% elif product.stock > 0 %}
                        <button type="submit" class="product-button">افزودن به سبد خرید</button>
                    {% else %}
                        <button type="button" class="product-button" disabled>ناموجود</button>
                    {% endif %}
                </form>
            </div>
        </div>

        {% if related_products %}
            <section class="related-products">
                <div class="section-heading"><h2>محصولات مرتبط</h2></div>
                <div class="products-grid">
                    {% for related in related_products %}
                        <article class="product-card">
                            <div class="product-image">
                                {% with image=related.related_images|first %}
                                    {% if image %}
                                        <img src="{{ image.image.url }}" alt="{{ image.alt_text|default:related.name }}">
                                    {% else %}
                                        <span class="product-placeholder">🎁</span>
                                    {% endif %}
                                {% endwith %}
                            </div>
                            <div class="product-info">
                                {% if related.category %}<span class="product-category">{{ related.category.name }}</span>{% endif %}
                                <h3>{{ related.name }}</h3>
                                <strong>{{ related.catalog_price|floatformat:0 }} تومان</strong>
                                <a href="{% url 'product_detail' related.id %}" class="product-button">مشاهده محصول</a>
                            </div>
                        </article>
                    {% endfor %}
                </div>
            </section>
        {% endif %}
    </div>
</section>
{% endblock %}
'''
write("store/templates/product_detail.html", product_detail)


# ------------------------------------------------------------
# 7) CART TEMPLATE
# ------------------------------------------------------------
cart = r'''{% extends "base.html" %}

{% block title %}سبد خرید | Giftweb{% endblock %}

{% block content %}
<section class="cart-page">
    <div class="container">
        <h1>سبد خرید</h1>

        {% if items %}
            <form method="post" action="{% url 'update_cart' %}">
                {% csrf_token %}
                <div class="cart-list">
                    {% for item in items %}
                        <div class="cart-item">
                            <div class="cart-item-image">
                                {% if item.image %}
                                    <img src="{{ item.image.image.url }}" alt="{{ item.product.name }}">
                                {% else %}
                                    🎁
                                {% endif %}
                            </div>

                            <div class="cart-item-info">
                                <h3>{{ item.product.name }}</h3>
                                {% if item.variant %}<p>{{ item.variant.name }}</p>{% endif %}
                                <strong>{{ item.unit_price|floatformat:0 }} تومان</strong>
                            </div>

                            <div class="cart-item-quantity">
                                <input type="number"
                                       name="quantity_{{ item.key }}"
                                       value="{{ item.quantity }}"
                                       min="1"
                                       max="{{ item.stock }}">
                            </div>

                            <div class="cart-item-total">
                                {{ item.total|floatformat:0 }} تومان
                            </div>

                            <div>
                                <button type="submit" form="remove-{{ forloop.counter }}" class="remove-link">حذف</button>
                            </div>
                        </div>
                    {% endfor %}
                </div>
                <button type="submit" class="product-button">به‌روزرسانی سبد</button>
            </form>

            {% for item in items %}
                <form id="remove-{{ forloop.counter }}"
                      method="post"
                      action="{% url 'remove_from_cart' item.key %}">
                    {% csrf_token %}
                </form>
            {% endfor %}

            <div class="cart-summary">
                <h2>مجموع: {{ total|floatformat:0 }} تومان</h2>
                <div class="cart-actions">
                    <a href="{% url 'shop' %}" class="secondary-button">ادامه خرید</a>
                    <a href="{% url 'checkout' %}" class="product-button">ادامه و ثبت سفارش</a>
                </div>

                <form method="post" action="{% url 'clear_cart' %}">
                    {% csrf_token %}
                    <button type="submit" class="danger-button">خالی کردن سبد</button>
                </form>
            </div>
        {% else %}
            <div class="no-products">سبد خرید شما خالی است.</div>
        {% endif %}
    </div>
</section>
{% endblock %}
'''
write("store/templates/cart.html", cart)


# ------------------------------------------------------------
# 8) LOGIN TEMPLATE
# ------------------------------------------------------------
login = r'''{% extends "base.html" %}

{% block title %}ورود | Giftweb{% endblock %}

{% block content %}
<section class="auth-page">
    <div class="auth-card">
        <h1>ورود به حساب</h1>

        <form method="post">
            {% csrf_token %}
            {% if next %}
                <input type="hidden" name="next" value="{{ next }}">
            {% endif %}
            {{ form.as_p }}
            <button type="submit" class="product-button">ورود</button>
        </form>

        <p>
            حساب ندارید؟
            <a href="{% url 'signup' %}">ثبت‌نام کنید</a>
        </p>
    </div>
</section>
{% endblock %}
'''
write("store/templates/login.html", login)


# ------------------------------------------------------------
# 9) HOME - preserve design, repair links/prices/stock/discounts
# ------------------------------------------------------------
home_path = ROOT / "store/templates/home.html"
home = home_path.read_text(encoding="utf-8")
backup("store/templates/home.html")

home = home.replace('href="#" class="btn btn-primary"', 'href="{% url \'shop\' %}" class="btn btn-primary"')
home = home.replace('href="#" class="btn btn-secondary"', 'href="{% url \'shop\' %}" class="btn btn-secondary"')
home = home.replace('<a href="#" class="category-card">', '<a href="{% url \'shop\' %}?category={{ category.slug }}" class="category-card">')
home = home.replace('<a href="#" class="view-all">', '<a href="{% url \'shop\' %}" class="view-all">')

home = re.sub(
    r'<a href="#" class="product-button">\s*مشاهده محصول\s*</a>',
    '<a href="{% url \'product_detail\' product.id %}" class="product-button">\n                                مشاهده محصول\n                            </a>',
    home,
)

home = home.replace(
    '{% if product.discount %}\n                            {% if product.discount.is_active %}',
    '{% if product.discount and product.discount.is_active_now %}',
)

home = home.replace(
    '''<div class="product-price">\n                            {% if product.discount and product.discount.is_active %}\n\n                                <span class="old-price">\n                                    {{ product.price|floatformat:0 }}\n                                    تومان\n                                </span>\n\n                                <strong>\n                                    {{ product.final_price|floatformat:0 }}\n                                    تومان\n                                </strong>\n                            {% else %}\n\n                                <strong>\n                                    {{ product.price|floatformat:0 }}\n                                    تومان\n                                </strong>\n\n                            {% endif %}\n                        </div>''',
    '''<div class="product-price">\n                            {% if product.catalog_old_price %}\n                                <span class="old-price">\n                                    {{ product.catalog_old_price|floatformat:0 }} تومان\n                                </span>\n                            {% endif %}\n                            <strong>\n                                {% if product.catalog_variants %}از {% endif %}\n                                {{ product.catalog_price|floatformat:0 }} تومان\n                            </strong>\n                        </div>''',
)

home = home.replace(
    '''<div class="product-price">\n                            <strong>\n                                {{ product.price|floatformat:0 }}\n                                تومان\n                            </strong>\n                        </div>''',
    '''<div class="product-price">\n                            {% if product.catalog_old_price %}\n                                <span class="old-price">\n                                    {{ product.catalog_old_price|floatformat:0 }} تومان\n                                </span>\n                            {% endif %}\n                            <strong>\n                                {% if product.catalog_variants %}از {% endif %}\n                                {{ product.catalog_price|floatformat:0 }} تومان\n                            </strong>\n                        </div>''',
)

home = re.sub(
    r'{% if product\.stock > 0 %}(.*?)%\s*else\s*%}(.*?)%\s*endif\s*%}',
    r'{% if product.catalog_has_stock %}\1{% else %}\2{% endif %}',
    home,
    flags=re.DOTALL,
)

home_path.write_text(home, encoding="utf-8")


# ------------------------------------------------------------
# 10) SETTINGS - remove leaked hard-coded key and old EMAIL_BACKEND conflicts
# ------------------------------------------------------------
settings_path = ROOT / "config/settings.py"
settings = settings_path.read_text(encoding="utf-8")
backup("config/settings.py")

if "import os" not in settings:
    settings = settings.replace(
        "from pathlib import Path",
        "import os\nfrom pathlib import Path",
        1,
    )

settings = re.sub(
    r'^SECRET_KEY\s*=.*$',
    'SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-secret-key-change-before-production")',
    settings,
    flags=re.MULTILINE,
)
settings = re.sub(
    r'^\s*EMAIL_BACKEND\s*=.*\n',
    '',
    settings,
    flags=re.MULTILINE,
)
settings_path.write_text(settings, encoding="utf-8")


print("Repair complete.")
print(f"Backup: {BACKUP}")
print("Next commands:")
print("  python manage.py check")
print("  python manage.py makemigrations")
print("  python manage.py migrate")
print("  python manage.py runserver")
