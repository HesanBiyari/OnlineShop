"""Audit helpers for sensitive staff and security events."""

from __future__ import annotations

import ipaddress
from decimal import Decimal

from store.models import AuditLog


def client_ip(request) -> str | None:
    """Return the direct peer address as a valid IP, or ``None``.

    ``X-Forwarded-For`` is deliberately ignored: on shared hosting it can be
    supplied by the client unless the proxy is known to overwrite it.
    """

    if request is None:
        return None
    raw = str(request.META.get("REMOTE_ADDR", "")).strip()
    if not raw:
        return None
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def log_action(
    *,
    action: str,
    actor=None,
    target_type: str = "",
    target_id: str | int = "",
    details: dict | None = None,
    request=None,
) -> AuditLog:
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action[:64],
        target_type=str(target_type)[:64],
        target_id=str(target_id)[:64],
        details=_json_safe(details or {}),
        ip_address=client_ip(request),
    )
