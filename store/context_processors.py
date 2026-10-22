"""Template context shared by every page."""

from __future__ import annotations

from store.services.cart import get_cart_count


def store_context(request):
    context = {"cart_count": get_cart_count(request)}
    if request.user.is_authenticated and request.user.is_staff:
        from store.views.staff import can_view_codes

        context["staff_can_view_codes"] = can_view_codes(request.user)
    return context
