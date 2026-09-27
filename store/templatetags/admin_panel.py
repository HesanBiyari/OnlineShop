from django import template
register=template.Library()
@register.filter
def field_value(obj,name):
    try:
        value=getattr(obj,name)
        if callable(value): value=value()
        return value if value not in (None,'') else '—'
    except Exception:
        return '—'
