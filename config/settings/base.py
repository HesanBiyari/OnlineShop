"""Shared Django settings for Giftbaaz.

Production-specific and development-specific values live in ``prod.py`` and
``dev.py``. Secrets are only read from the environment.
"""

from __future__ import annotations

from pathlib import Path

from config.env import (
    BASE_DIR,
    env_bool,
    env_int,
    env_list,
    env_str,
)

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
DEBUG = False
SECRET_KEY = env_str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "store",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "store.context_processors.store_context",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_ENGINE = env_str("DJANGO_DB_ENGINE", "django.db.backends.sqlite3")
DB_IS_SERVER = DB_ENGINE in {
    "django.db.backends.mysql",
    "django.db.backends.postgresql",
}

DATABASES = {
    "default": {
        "ENGINE": DB_ENGINE,
        "NAME": env_str("DJANGO_DB_NAME", str(BASE_DIR / "db.sqlite3")),
        "CONN_MAX_AGE": env_int("DJANGO_DB_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": True,
    }
}

if DB_ENGINE == "django.db.backends.mysql":
    DATABASES["default"].update(
        {
            "USER": env_str("DJANGO_DB_USER"),
            "PASSWORD": env_str("DJANGO_DB_PASSWORD"),
            "HOST": env_str("DJANGO_DB_HOST", "localhost"),
            "PORT": env_str("DJANGO_DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    )
elif DB_ENGINE == "django.db.backends.postgresql":
    DATABASES["default"].update(
        {
            "USER": env_str("DJANGO_DB_USER"),
            "PASSWORD": env_str("DJANGO_DB_PASSWORD"),
            "HOST": env_str("DJANGO_DB_HOST", "localhost"),
            "PORT": env_str("DJANGO_DB_PORT", "5432"),
        }
    )

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/account/"
LOGOUT_REDIRECT_URL = "/"

AUTH_MAX_ATTEMPTS = env_int("AUTH_MAX_ATTEMPTS", 5)
AUTH_LOCKOUT_SECONDS = env_int("AUTH_LOCKOUT_SECONDS", 900)

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static and media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env_str("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 5 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int("FILE_UPLOAD_MAX_MEMORY_SIZE", 5 * 1024 * 1024)
DATA_UPLOAD_MAX_NUMBER_FIELDS = env_int("DATA_UPLOAD_MAX_NUMBER_FIELDS", 2000)

PRODUCT_IMAGE_MAX_BYTES = env_int("PRODUCT_IMAGE_MAX_BYTES", 5 * 1024 * 1024)
PRODUCT_IMAGE_MAX_DIMENSION = env_int("PRODUCT_IMAGE_MAX_DIMENSION", 4000)
DIGITAL_CODE_IMPORT_MAX_BYTES = env_int(
    "DIGITAL_CODE_IMPORT_MAX_BYTES", 2 * 1024 * 1024
)
DIGITAL_CODE_IMPORT_MAX_ROWS = env_int("DIGITAL_CODE_IMPORT_MAX_ROWS", 10000)

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env_str(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env_str("EMAIL_HOST")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 15)
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "webmaster@localhost")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ---------------------------------------------------------------------------
# Payments (ZarinPal is the only gateway implemented in the current product)
# ---------------------------------------------------------------------------
PAYMENT_GATEWAY = env_str("PAYMENT_GATEWAY", "zarinpal").lower()
PAYMENT_CURRENCY = env_str("PAYMENT_CURRENCY", "IRR").upper()
PAYMENT_TIMEOUT = env_int("PAYMENT_TIMEOUT", 15)
PAYMENT_REDIRECT_REUSE_SECONDS = env_int("PAYMENT_REDIRECT_REUSE_SECONDS", 1800)
PAYMENT_INITIATING_STALE_SECONDS = env_int("PAYMENT_INITIATING_STALE_SECONDS", 60)

ZARINPAL_MERCHANT_ID = env_str("ZARINPAL_MERCHANT_ID")
ZARINPAL_SANDBOX = env_bool("ZARINPAL_SANDBOX", True)

# ---------------------------------------------------------------------------
# Security defaults (production overrides these)
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = env_str("DJANGO_SECURE_REFERRER_POLICY", "same-origin")
SECURE_CROSS_ORIGIN_OPENER_POLICY = env_str(
    "DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin"
)
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

TRUST_PROXY_SSL = env_bool("DJANGO_TRUST_PROXY_SSL", True)
if TRUST_PROXY_SSL:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Caching: local memory only. No Redis is required on shared hosting.
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "giftbaaz-local",
    }
}

# ---------------------------------------------------------------------------
# Logging: safe by default; never log request bodies, tokens or card data.
# ---------------------------------------------------------------------------
LOG_LEVEL = env_str("DJANGO_LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "store": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

SITE_NAME = env_str("SITE_NAME", "Giftbaaz")
SITE_DOMAIN = env_str("SITE_DOMAIN", "giftbazz.ir")
# Optional absolute base URL (for example https://giftbazz.ir). The payment
# view normally passes a request-built callback URL; this is a fallback for
# management commands and non-request callers.
SITE_URL = env_str("SITE_URL", "").rstrip("/")
