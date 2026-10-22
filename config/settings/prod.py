"""Production settings for cPanel / CloudLinux / Passenger.

Every value that differs between installations comes from the environment.
The module deliberately fails fast rather than silently running with unsafe
defaults.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_int, env_list, env_str

from .base import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = env_str("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set in production. Generate one with "
        "`python -c \"import secrets; print(secrets.token_urlsafe(64))\"`."
    )
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be at least 50 characters in production."
    )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list the public host name(s)."
    )

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured(
        "DJANGO_CSRF_TRUSTED_ORIGINS must list the https origin(s)."
    )

if DB_ENGINE == "django.db.backends.sqlite3":
    raise ImproperlyConfigured(
        "Production must use MariaDB/MySQL. Set DJANGO_DB_ENGINE to "
        "django.db.backends.mysql."
    )

# ---------------------------------------------------------------------------
# Static files: hashed, compressed manifest served by WhiteNoise.
# ---------------------------------------------------------------------------
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# WhiteNoise should not try to serve user uploads.
WHITENOISE_USE_FINDERS = False
WHITENOISE_AUTOREFRESH = False

# ---------------------------------------------------------------------------
# Transport security
# ---------------------------------------------------------------------------
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", True
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env_str(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)

# ---------------------------------------------------------------------------
# Payments: sandbox must be disabled explicitly in production.
# ---------------------------------------------------------------------------
ZARINPAL_SANDBOX = env_bool("ZARINPAL_SANDBOX", False)
if ZARINPAL_SANDBOX:
    # Not fatal: a staging deployment may intentionally use the sandbox.
    import logging

    logging.getLogger("store").warning(
        "ZARINPAL_SANDBOX is enabled with production settings."
    )

# ---------------------------------------------------------------------------
# Logging: Passenger captures stdout/stderr, so keep the console handler and
# avoid writing secrets to files.
# ---------------------------------------------------------------------------
LOGGING["root"]["level"] = env_str("DJANGO_LOG_LEVEL", "INFO").upper()  # noqa: F405
