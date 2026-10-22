"""Authentication helpers: phone normalisation and login throttling."""

from __future__ import annotations

import hashlib
import logging
import re

from django.conf import settings
from django.core.cache import cache

from store.models import AuditLog

from .audit import client_ip, log_action

logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^(?:\+98|0098|98|0)?9\d{9}$")

FAILURE_KEY = "auth-fail:{digest}"


def normalize_phone(value: str) -> str:
    """Normalise Iranian mobile numbers to ``09xxxxxxxxx``.

    Raises ``ValueError`` when the number is not a valid mobile number.
    """

    phone = str(value or "").strip().replace(" ", "").replace("-", "")
    if phone.startswith("+98"):
        phone = "0" + phone[3:]
    elif phone.startswith("0098"):
        phone = "0" + phone[4:]
    elif phone.startswith("98") and len(phone) == 12:
        phone = "0" + phone[2:]
    if not PHONE_RE.fullmatch(phone):
        raise ValueError("شماره موبایل معتبر نیست.")
    return phone


def throttle_identity(request, identifier: str) -> str:
    raw = f"{client_ip(request) or 'unknown'}|{identifier}".lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _key(identity: str) -> str:
    return FAILURE_KEY.format(digest=identity)


def is_locked_out(request, identifier: str) -> bool:
    attempts = cache.get(_key(throttle_identity(request, identifier)), 0) or 0
    return attempts >= int(getattr(settings, "AUTH_MAX_ATTEMPTS", 5))


def register_failed_login(request, identifier: str) -> None:
    identity = throttle_identity(request, identifier)
    key = _key(identity)
    lockout = int(getattr(settings, "AUTH_LOCKOUT_SECONDS", 900))

    cache.add(key, 0, timeout=lockout)
    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=lockout)
        attempts = 1

    if attempts == int(getattr(settings, "AUTH_MAX_ATTEMPTS", 5)):
        try:
            log_action(
                action=AuditLog.ACTION_LOGIN_LOCKOUT,
                target_type="auth",
                target_id=identifier,
                details={"attempts": attempts},
                request=request,
            )
        except Exception:  # pragma: no cover - audit must not break login
            logger.exception("Could not write login lockout audit entry")


def clear_failed_logins(request, identifier: str) -> None:
    cache.delete(_key(throttle_identity(request, identifier)))
