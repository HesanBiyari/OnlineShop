from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "config" / "settings.py"
REQUIREMENTS = ROOT / "requirements.txt"


def die(message: str) -> None:
    print(f"\n[ERROR] {message}")
    raise SystemExit(1)


def backup(path: Path) -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.bak_{stamp}"))


def write_file(path: Path, content: str, backup_existing: bool = True) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and backup_existing:
        backup(path)
    path.write_text(content, encoding="utf-8")


def patch_once(text: str, pattern: str, replacement: str, label: str) -> str:
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        die(f"Safe patch failed: {label}")
    return new


def run(cmd: list[str], env: dict[str, str]) -> int:
    print("\n$ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, env=env).returncode


def main() -> None:
    if not (ROOT / "manage.py").exists() or not SETTINGS.exists():
        die("Run this file from the OnlineShop project root.")

    settings = SETTINGS.read_text(encoding="utf-8")

    settings = patch_once(
        settings,
        r'DEBUG = env_bool\("DJANGO_DEBUG", True\)',
        'DEBUG = env_bool("DJANGO_DEBUG", False)',
        "production-safe DEBUG default",
    )

    secret_pattern = r"""if not SECRET_KEY:\n    if DEBUG:\n        # Development only\. Set DJANGO_SECRET_KEY in production\.\n        SECRET_KEY = get_random_secret_key\(\)\n    else:\n        raise ImproperlyConfigured\("DJANGO_SECRET_KEY must be set when DEBUG=False"\)"""
    secret_replacement = """if not SECRET_KEY:
    if DEBUG:
        # Development-only fallback. Production requires a persistent secret.
        SECRET_KEY = get_random_secret_key()
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DEBUG=False"
        )"""
    settings = patch_once(
        settings,
        secret_pattern,
        secret_replacement,
        "production SECRET_KEY guard",
    )

    db_block = """if DB_ENGINE == "django.db.backends.postgresql":
    DATABASES["default"].update({
        "USER": os.getenv("DJANGO_DB_USER", ""),
        "PASSWORD": os.getenv("DJANGO_DB_PASSWORD", ""),
        "HOST": os.getenv("DJANGO_DB_HOST", "localhost"),
        "PORT": os.getenv("DJANGO_DB_PORT", "5432"),
    })
"""
    if "Production must not run on SQLite" not in settings:
        if db_block not in settings:
            die("Database configuration block not found.")
        settings = settings.replace(
            db_block,
            db_block + """if not DEBUG and DB_ENGINE == "django.db.backends.sqlite3":
    raise ImproperlyConfigured(
        "Production must not run on SQLite. Configure a server database."
    )
""",
            1,
        )

    if '"whitenoise.middleware.WhiteNoiseMiddleware"' not in settings:
        settings = patch_once(
            settings,
            r'MIDDLEWARE = \[\n    "django\.middleware\.security\.SecurityMiddleware",',
            'MIDDLEWARE = [\n    "django.middleware.security.SecurityMiddleware",\n    "whitenoise.middleware.WhiteNoiseMiddleware",',
            "WhiteNoise middleware",
        )

    if "CompressedManifestStaticFilesStorage" not in settings:
        static_block = """STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
"""
        if static_block not in settings:
            die("Static configuration block not found.")
        settings = settings.replace(
            static_block,
            static_block + """STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
""",
            1,
        )

    settings = patch_once(
        settings,
        r'SECURE_SSL_REDIRECT = env_bool\("DJANGO_SECURE_SSL_REDIRECT", False\)',
        'SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)',
        "HTTPS redirect",
    )
    write_file(SETTINGS, settings)

    requirements = REQUIREMENTS.read_text(encoding="utf-8")
    if not re.search(r"(?m)^whitenoise([<>=!~]|$)", requirements):
        write_file(REQUIREMENTS, requirements.rstrip() + "\nwhitenoise>=6.9,<7\n")

    env_example = """# Production environment - put real values in cPanel, not Git.
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=CHANGE_ME_TO_A_LONG_RANDOM_SECRET
DJANGO_ALLOWED_HOSTS=example.com,www.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com

# SQLite is rejected when DJANGO_DEBUG=false.
DJANGO_DB_ENGINE=django.db.backends.postgresql
DJANGO_DB_NAME=CHANGE_ME
DJANGO_DB_USER=CHANGE_ME
DJANGO_DB_PASSWORD=CHANGE_ME
DJANGO_DB_HOST=127.0.0.1
DJANGO_DB_PORT=5432

DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false
DJANGO_SECURE_HSTS_PRELOAD=false
DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY=same-origin
DJANGO_SECURE_REFERRER_POLICY=same-origin

PAYMENT_GATEWAY=zarinpal
ZARINPAL_MERCHANT_ID=CHANGE_ME
ZARINPAL_SANDBOX=false
PAYMENT_CURRENCY=IRR
PAYMENT_TIMEOUT=15

DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mail.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=CHANGE_ME
EMAIL_HOST_PASSWORD=CHANGE_ME
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
DEFAULT_FROM_EMAIL=no-reply@example.com
"""
    write_file(ROOT / ".env.example", env_example, backup_existing=False)

    gitignore_path = ROOT / ".gitignore"
    gitignore = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    for line in [".env\n", ".env.*\n", "!.env.example\n", "staticfiles/\n"]:
        if line.rstrip("\n") not in gitignore.splitlines():
            if gitignore and not gitignore.endswith("\n"):
                gitignore += "\n"
            gitignore += line
    write_file(gitignore_path, gitignore, backup_existing=False)

    media_htaccess = """# Uploaded media is data, not executable application code.
Options -ExecCGI
<FilesMatch "\\.(php|php[0-9]?|phtml|phar|cgi|pl|py|jsp|asp|aspx)$">
    Require all denied
</FilesMatch>
"""
    write_file(ROOT / "media" / ".htaccess", media_htaccess, backup_existing=False)

    deployment = """# Production deployment

## cPanel / Passenger
Project root: OnlineShop root
WSGI: config.wsgi:application

Install:
    pip install -r requirements.txt

Server commands:
    python manage.py migrate
    python manage.py collectstatic --noinput
    python manage.py check --deploy

Set in hosting environment:
- DJANGO_DEBUG=false
- DJANGO_SECRET_KEY=<persistent random secret>
- DJANGO_ALLOWED_HOSTS=your-domain.tld,www.your-domain.tld
- DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.tld,https://www.your-domain.tld
- production database variables
- ZARINPAL_MERCHANT_ID=<real merchant id>
- ZARINPAL_SANDBOX=false
- SMTP variables if email is used

Do not use SQLite in production.

Static files are collected to staticfiles/ and WhiteNoise can serve them.
Media stays under media/ and must be served as files, never executed.

Before launch, verify HTTPS, ZarinPal callback, one real low-value payment,
digital-code delivery, and repeated callback idempotency.

Cron:
    python manage.py process_orders
Recommended interval: 1-5 minutes, subject to host limits.
"""
    write_file(ROOT / "DEPLOYMENT.md", deployment, backup_existing=False)

    cron = """# Cron example - replace paths with your cPanel values.
cd /home/CPANEL_USER/ONLINE_SHOP_ROOT && /home/CPANEL_USER/virtualenv/ONLINE_SHOP_ROOT/3.12/bin/python manage.py process_orders >> /home/CPANEL_USER/logs/process_orders.log 2>&1
"""
    write_file(ROOT / "CRON.md", cron, backup_existing=False)

    ci = """name: Django CI
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: Django check
        env:
          DJANGO_DEBUG: "true"
          DJANGO_SECRET_KEY: "ci-only-secret"
        run: python manage.py check
      - name: Migration check
        env:
          DJANGO_DEBUG: "true"
          DJANGO_SECRET_KEY: "ci-only-secret"
        run: python manage.py makemigrations --check --dry-run
      - name: Tests
        env:
          DJANGO_DEBUG: "true"
          DJANGO_SECRET_KEY: "ci-only-secret"
        run: python manage.py test
      - name: Collect static
        env:
          DJANGO_DEBUG: "true"
          DJANGO_SECRET_KEY: "ci-only-secret"
        run: python manage.py collectstatic --noinput
"""
    write_file(ROOT / ".github" / "workflows" / "ci.yml", ci, backup_existing=False)

    env = os.environ.copy()
    env["DJANGO_DEBUG"] = "true"
    env["DJANGO_SECRET_KEY"] = "repair-script-local-secret"

    checks = [
        [sys.executable, "manage.py", "check"],
        [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
        [sys.executable, "manage.py", "collectstatic", "--noinput"],
        [sys.executable, "manage.py", "test"],
    ]

    for pass_no in (1, 2):
        print("\n" + "=" * 70)
        print(f"VERIFICATION PASS {pass_no}")
        print("=" * 70)
        for cmd in checks:
            if run(cmd, env):
                die(f"Verification pass {pass_no} failed: {' '.join(cmd)}")

    print("\n" + "=" * 70)
    print("REPAIR COMPLETE - BOTH VERIFICATION PASSES PASSED")
    print("=" * 70)
    print("Configure production environment variables, then run check --deploy on the server.")


if __name__ == "__main__":
    main()
