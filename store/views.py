from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import render

from .models import Category, Product, ProductImage


def home(request):

    product_images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("-is_main", "id"),
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

    featured_ids = {product.id for product in featured_products}

    if len(featured_products) < 4:

        extra_products = list(
            products
            .exclude(id__in=featured_ids)
            .order_by("-created_at")[:4 - len(featured_products)]
        )

        featured_products.extend(extra_products)

    new_products = list(products[:4])

    categories = Category.objects.order_by("name")[:5]

    context = {
        "categories": categories,
        "featured_products": featured_products,
        "new_products": new_products,
    }

    return render(request, "home.html", context)


def shop(request):

    product_images = Prefetch(
        "images",
        queryset=ProductImage.objects.order_by("-is_main", "id"),
        to_attr="shop_images",
    )

    products = (
        Product.objects
        .select_related("category", "discount")
        .prefetch_related(product_images)
        .all()
    )

    categories = Category.objects.order_by("name")

    # Search
    search_query = request.GET.get("q", "").strip()

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(category__name__icontains=search_query)
        )

    # Category filter
    category_slug = request.GET.get("category", "").strip()

    if category_slug:
        products = products.filter(
            category__slug=category_slug
        )

    # Sorting
    sort = request.GET.get("sort", "newest")

    if sort == "price_low":
        products = products.order_by("price")

    elif sort == "price_high":
        products = products.order_by("-price")

    elif sort == "name":
        products = products.order_by("name")

    else:
        products = products.order_by("-created_at")

    # Pagination
    paginator = Paginator(products, 12)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)

    context = {
        "products": page_obj,
        "page_obj": page_obj,
        "categories": categories,
        "search_query": search_query,
        "selected_category": category_slug,
        "selected_sort": sort,
    }

    return render(request, "shop.html", context)