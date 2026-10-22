"""Static pages, robots.txt and error handlers."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render


def about(request):
    return render(request, "about.html")


def contact(request):
    return render(request, "contact.html")


def faq(request):
    return render(request, "faq.html")


def guide(request):
    return render(request, "guide.html")


def terms(request):
    return render(request, "terms.html")


def privacy(request):
    return render(request, "privacy.html")


def robots(request):
    domain = str(getattr(settings, "SITE_DOMAIN", "giftbazz.ir")).strip()
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /dashboard/\n"
        "Disallow: /django-admin/\n"
        "Disallow: /admin-tools/\n"
        "Disallow: /cart/\n"
        "Disallow: /checkout/\n"
        "Disallow: /payment/\n"
        "Disallow: /account/\n"
        "Disallow: /orders/\n"
        f"Sitemap: https://{domain}/sitemap.xml\n"
    )
    response = HttpResponse(body, content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"
    return response


def permission_denied(request, exception=None):
    response = render(request, "403.html", status=403)
    response["Cache-Control"] = "no-store"
    return response


def page_not_found(request, exception=None):
    response = render(request, "404.html", status=404)
    response["Cache-Control"] = "no-store"
    return response


def server_error(request):
    response = render(request, "500.html", status=500)
    response["Cache-Control"] = "no-store"
    return response
