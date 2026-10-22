"""Local development settings.

Never use these values on a public server.
"""

from __future__ import annotations

from config.env import env_bool, env_list, env_str

from .base import *  # noqa: F401,F403

DEBUG = True

# A predictable development key keeps sessions stable across reloads. Production
# refuses to start without a real DJANGO_SECRET_KEY (see prod.py).
SECRET_KEY = env_str(
    "DJANGO_SECRET_KEY",
    "dev-only-insecure-secret-key-do-not-use-in-production-0000000000",
)

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost,testserver,[::1]",
)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

EMAIL_BACKEND = env_str(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)

# Plain storage avoids requiring collectstatic before every local page load.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

ZARINPAL_SANDBOX = env_bool("ZARINPAL_SANDBOX", True)
