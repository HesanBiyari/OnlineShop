def cart_context(request):
    cart = request.session.get("cart", {})
    cart_count = 0

    if isinstance(cart, dict):
        for quantity in cart.values():
            try:
                cart_count += max(0, int(quantity))
            except (TypeError, ValueError):
                continue

    return {"cart_count": cart_count}
