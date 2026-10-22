"""Settings used by the automated test suite.

The suite must never reach a real database, gateway or mail server.
"""

from __future__ import annotations

import os
import tempfile

from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-only-secret-key-not-used-outside-tests-000000000000"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

if os.getenv("DJANGO_TEST_DB_ENGINE", "") == "django.db.backends.mysql":
    # Optional real-MariaDB run: proves the migrations and queries on the same
    # engine as production. CI/local defaults stay on in-memory SQLite.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DJANGO_TEST_DB_NAME", "giftbaaz_test"),
            "USER": os.getenv("DJANGO_DB_USER", ""),
            "PASSWORD": os.getenv("DJANGO_DB_PASSWORD", ""),
            "HOST": os.getenv("DJANGO_DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DJANGO_DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            "TEST": {
                "NAME": os.getenv("DJANGO_TEST_DB_TEST_NAME", "test_giftbaaz_test"),
                "CHARSET": "utf8mb4",
                "COLLATION": "utf8mb4_unicode_ci",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
            "TEST": {"NAME": ":memory:"},
        }
    }

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "giftbaaz-tests",
    }
}

MEDIA_ROOT = tempfile.mkdtemp(prefix="giftbaaz-test-media-")

ZARINPAL_MERCHANT_ID = "test-merchant-id"
ZARINPAL_SANDBOX = True
PAYMENT_GATEWAY = "zarinpal"
PAYMENT_CURRENCY = "IRR"

# Keep throttling enabled but short so tests can prove the behaviour.
AUTH_MAX_ATTEMPTS = 5
AUTH_LOCKOUT_SECONDS = 900

LOGGING["root"]["level"] = "CRITICAL"  # noqa: F405
LOGGING["loggers"]["django.request"]["level"] = "CRITICAL"  # noqa: F405
LOGGING["loggers"]["store"]["level"] = "CRITICAL"  # noqa: F405
