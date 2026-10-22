"""Small display helpers for the custom staff panel."""

from __future__ import annotations

from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def field_value(obj, name):
    """Render a model field for list tables.

    Foreign keys use their ``__str__``, choice fields use their display label,
    money fields are grouped, and empty values become an em dash.
    """

    try:
        value = getattr(obj, name)
        if callable(value):
            value = value()
    except Exception:
        return "—"

    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, Decimal):
        return f"{value:,.0f}"

    try:
        field = obj._meta.get_field(name)
        choices = dict(getattr(field, "flatchoices", []) or [])
        if choices and value in choices:
            return choices[value]
    except Exception:
        pass

    text = str(value)
    return text if len(text) <= 60 else text[:57] + "..."
