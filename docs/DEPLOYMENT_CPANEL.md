# cPanel / CloudLinux / Passenger Deployment

This guide targets a cPanel account with **Setup Python App**, LiteSpeed (or
Apache) and MariaDB/MySQL. It does not assume root access, SSH, Redis, Celery or
Docker. Commands use placeholders:

- `CPANEL_USER` — cPanel account name
- `APP_ROOT` — application directory, e.g. `/home/CPANEL_USER/giftbaaz`
- `APP_NAME` — the Python application name in cPanel
- `DB_NAME`, `DB_USER`, `DB_PASSWORD` — database credentials

> Status: this procedure was written and reviewed locally but **not executed on
> the real server**. Treat the first deployment as a supervised change with a
> backup and a rollback plan.

## 1. Prerequisites

- Python 3.11 available in cPanel's Python selector.
- MariaDB 10.6+ or MySQL 8.0.11+.
- The domain (`giftbazz.ir`) pointed at the hosting account.
- A valid TLS certificate (AutoSSL is fine).
- Git access or an upload mechanism for the repository.
- cPanel access to: Python App, MySQL Databases, phpMyAdmin, Cron Jobs, File
  Manager/Terminal, SSL/TLS.

## 2. Create the database

In **MySQL Databases**:

1. Create a database (cPanel prefixes it, e.g. `CPANEL_USER_giftbaaz`).
2. Create a user with a long random password.
3. Add the user to the database with ALL PRIVILEGES.
4. Set the database charset to `utf8mb4` / `utf8mb4_unicode_ci`.

If the panel does not expose charset, run in phpMyAdmin:

```sql
ALTER DATABASE `CPANEL_USER_giftbaaz`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Verify:

```sql
SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'CPANEL_USER_giftbaaz';
```

Persian/Arabic inserts fail with **MySQL error 1366** when the charset is wrong.
Fix it before importing or creating data.

## 3. Upload the code

Preferred: clone the repository into `APP_ROOT` and check out the release
branch/commit.

```bash
cd /home/CPANEL_USER
git clone https://github.com/HesanBiyari/OnlineShop.git giftbaaz
cd giftbaaz
git checkout <release-tag-or-commit>
```

Do **not** upload:

- `.venv/`
- `staticfiles/` (regenerate on the server)
- `db.sqlite3`
- `.env` (create it on the server)
- local backups or `__pycache__`

If uploading a ZIP through File Manager, extract it so `manage.py` and
`passenger_wsgi.py` are directly inside `APP_ROOT`.

## 4. Create the Python application

In **Setup Python App -> Create Application**:

| Field | Value |
| --- | --- |
| Python version | 3.11 |
| Application root | `giftbaaz` (relative to home) |
| Application URL | `giftbazz.ir` (and `www` if used) |
| Application startup file | `passenger_wsgi.py` |
| Application entry point | `application` |

cPanel creates a virtualenv such as
`/home/CPANEL_USER/virtualenv/giftbaaz/3.11`.

Install dependencies using the panel's "Run Pip Install" or a terminal:

```bash
source /home/CPANEL_USER/virtualenv/giftbaaz/3.11/bin/activate
cd /home/CPANEL_USER/giftbaaz
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

`config/__init__.py` installs PyMySQL as the MySQLdb compatibility layer, so no
C compiler is required. Do not add `mysqlclient` on a host that cannot build it.

## 5. Configure environment variables

Use **Setup Python App -> Environment variables** (preferred) or a server-only
`.env` file in `APP_ROOT` with mode `600`.

At minimum:

```ini
DJANGO_ENV=production
DJANGO_SECRET_KEY=<64+ random characters>
DJANGO_ALLOWED_HOSTS=giftbazz.ir,www.giftbazz.ir
DJANGO_CSRF_TRUSTED_ORIGINS=https://giftbazz.ir,https://www.giftbazz.ir
SITE_DOMAIN=giftbazz.ir
SITE_URL=https://giftbazz.ir

DJANGO_DB_ENGINE=django.db.backends.mysql
DJANGO_DB_NAME=CPANEL_USER_giftbaaz
DJANGO_DB_USER=CPANEL_USER_giftbaaz
DJANGO_DB_PASSWORD=<database password>
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=3306

DJANGO_MEDIA_ROOT=/home/CPANEL_USER/giftbaaz/media
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false
DJANGO_SECURE_HSTS_PRELOAD=false
DJANGO_TRUST_PROXY_SSL=true

ZARINPAL_MERCHANT_ID=<real merchant id>
ZARINPAL_SANDBOX=false
PAYMENT_CURRENCY=IRR
PAYMENT_REDIRECT_REUSE_SECONDS=1800
PAYMENT_INITIATING_STALE_SECONDS=120
PAYMENT_VERIFYING_STALE_SECONDS=300
ORDER_PENDING_EXPIRY_HOURS=24
```

Generate the secret locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

`prod.py` refuses to start when the secret is missing/short, allowed hosts or
CSRF origins are empty, or SQLite is selected. This is intentional.

Keep HSTS at `0` until HTTPS and the callback URL are confirmed, then raise it
to `31536000` and restart. Enable include-subdomains only if every subdomain is
HTTPS; do not enable `preload` casually because removal takes months. Boolean
values are strict (`true/false`, `1/0`, `yes/no`, `on/off`); unknown values make
the app fail to start instead of silently choosing a default.

## 6. Migrate, collect static, verify

```bash
source /home/CPANEL_USER/virtualenv/giftbaaz/3.11/bin/activate
cd /home/CPANEL_USER/giftbaaz

python manage.py migrate --plan
python manage.py migrate
python manage.py check --deploy
python manage.py collectstatic --noinput
python manage.py createsuperuser   # first install only
```

For an existing database, read `docs/DATABASE_MIGRATION.md` first and take a
backup. `collectstatic` must succeed before WhiteNoise can serve hashed assets.

Permissions:

```bash
find . -type d -exec chmod 755 {} \;
find . -type f -exec chmod 644 {} \;
chmod 600 .env 2>/dev/null || true
```

`media/` must be writable by the application user (usually the cPanel user):

```bash
mkdir -p /home/CPANEL_USER/giftbaaz/media
chmod 755 /home/CPANEL_USER/giftbaaz/media
```

## 7. Static and media files

- **Static**: `/static/` is served by WhiteNoise from `staticfiles/`. No web
  server alias is required. If assets 404, re-run `collectstatic`, confirm the
  manifest exists, and restart Passenger.
- **Media**: uploaded product images are not served by WhiteNoise. Serve them
  with LiteSpeed/Apache. Two common layouts:

  **Option A — media inside `public_html`**

  ```bash
  mkdir -p /home/CPANEL_USER/public_html/media
  ```

  Set `DJANGO_MEDIA_ROOT=/home/CPANEL_USER/public_html/media`.

  **Option B — symlink**

  ```bash
  ln -s /home/CPANEL_USER/giftbaaz/media /home/CPANEL_USER/public_html/media
  ```

  Confirm the host follows symlinks. Test by opening an uploaded image URL.

Add `/home/CPANEL_USER/public_html/media/.htaccess`:

```apache
Options -Indexes -ExecCGI
php_flag engine off
<FilesMatch "\.(php|php[0-9]|phtml|phar|cgi|pl|py|sh)$">
  Require all denied
</FilesMatch>
```

Never allow script execution or directory listing in `media/`.

## 8. Restart the application

After changing code or environment variables:

```bash
mkdir -p /home/CPANEL_USER/giftbaaz/tmp
touch /home/CPANEL_USER/giftbaaz/tmp/restart.txt
```

or use **Setup Python App -> Restart**. Passenger also restarts when the
application is restarted from the panel.

## 9. Cron for fulfilment retries

Paid orders whose stock or digital codes were unavailable remain `processing`.
`process_orders` also reconciles stale `verifying` payments and cancels
abandoned unpaid orders whose coupon reservation is still held. It retries each
missing fulfilment step idempotently.

In **Cron Jobs**, add (every 5 minutes):

```cron
*/5 * * * * cd /home/CPANEL_USER/giftbaaz && /home/CPANEL_USER/virtualenv/giftbaaz/3.11/bin/python manage.py process_orders >> /home/CPANEL_USER/logs/process_orders.log 2>&1
```

Create the log directory first. Check the log after the first runs. The command
is idempotent and locks order/payment/code rows; a single scheduled job is
enough. Alert on non-zero exit or repeated `pending=` counts.

## 10. Smoke-test checklist

Run after every deployment:

- [ ] `https://giftbazz.ir/` loads over HTTPS with valid certificate.
- [ ] `/shop/`, a product page, search, category filter and sorting work.
- [ ] Add to cart, update quantity, remove, clear.
- [ ] Signup with a new mobile number; login/logout.
- [ ] Checkout with and without a coupon; totals match the cart.
- [ ] Payment initiation redirects to ZarinPal with the correct amount.
- [ ] Callback returns to the site; order becomes paid/completed.
- [ ] Digital codes are visible only to the order owner.
- [ ] Replaying the callback does not duplicate stock deduction or codes.
- [ ] `/orders/` and another user's order URL (must be 404/403).
- [ ] `/dashboard/` loads for staff; non-staff is rejected.
- [ ] Code export works only with `store.export_digitalcode`; audit row exists.
- [ ] `/django-admin/` loads; code screens are gated.
- [ ] `/sitemap.xml` and `/robots.txt` render with the production domain.
- [ ] 404 page renders.
- [ ] `python manage.py check --deploy` passes (enable HSTS to clear warnings).
- [ ] Cron log shows a successful `process_orders` run.
- [ ] Media image URL loads and cannot execute scripts.
- [ ] A zero-total coupon order completes without a gateway.
- [ ] A repeated callback does not create a second stock/code/notification.
- [ ] Staff cannot manually cancel an order while its gateway attempt is live.

## 11. Logs and diagnostics

- cPanel Python App shows stdout/stderr and Passenger errors.
- Django logs to the console (Passenger captures it).
- `process_orders` writes to the cron log.
- For a 500, temporarily inspect the Passenger error log; never enable
  `DEBUG=true` on the public site.
- `python manage.py check --deploy` catches missing security settings.

## 12. Updating the application

```bash
cd /home/CPANEL_USER/giftbaaz
git fetch --all --tags
git checkout <new-release>
source /home/CPANEL_USER/virtualenv/giftbaaz/3.11/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
touch tmp/restart.txt
```

Take a database and media backup before `migrate`. Deploy during low traffic.

## 13. Rollback

1. Put the site in maintenance mode (panel or a temporary `.htaccess` rule).
2. Restore the database backup if the release included a migration.
3. `git checkout <previous-release>`.
4. Reinstall requirements if they changed.
5. `python manage.py collectstatic --noinput`.
6. `touch tmp/restart.txt`.
7. Re-run the smoke checklist.

Do not reverse a migration on production unless you have rehearsed it; restoring
the backup is safer. See `docs/DATABASE_MIGRATION.md`.

## 14. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| 500 on every page | missing/short `DJANGO_SECRET_KEY` | set a 50+ char secret, restart |
| `DisallowedHost` / 400 | host not in `DJANGO_ALLOWED_HOSTS` | add domain and `www`, restart |
| CSRF verification failed | origin missing or wrong scheme | set `DJANGO_CSRF_TRUSTED_ORIGINS=https://...` |
| `Incorrect string value` / 1366 | database/table not `utf8mb4` | convert charset, retry insert |
| Static assets 404 | `collectstatic` not run or app not restarted | run it, check `staticfiles/staticfiles.json`, restart |
| Media 404 | media not under `public_html` or wrong `DJANGO_MEDIA_ROOT` | fix path/symlink, permissions |
| `mysqlclient` build error | wrong requirement installed | use `requirements.txt` with PyMySQL |
| `OperationalError (2002)` | wrong DB host/socket | use `localhost` or the panel's socket path |
| App uses old code | Passenger not restarted | `touch tmp/restart.txt` |
| 502/503 from Passenger | startup exception | read the Python app error log |
| Login loop | `SESSION_COOKIE_SECURE` without HTTPS, or proxy header missing | fix TLS / `DJANGO_TRUST_PROXY_SSL` |
| Callback fails | HTTP instead of HTTPS or wrong `SITE_URL` | use the canonical HTTPS domain |
| Cron does nothing | wrong virtualenv/python path | use the absolute interpreter path |
| Admin date filters empty; reports fine | MySQL timezone tables not loaded | Ask the host to load them, or rely on the app's revenue reports which use explicit UTC bounds |
| HSTS deploy warning W004 (or W005/W021) | HSTS is opt-in and still disabled | Enable seconds/include/preload after HTTPS is verified |

## 15. Security hardening after launch

- Keep `DJANGO_DEBUG=false` and `ZARINPAL_SANDBOX=false`.
- Restrict `/django-admin/` by IP or strong staff accounts; the custom panel is
  the normal interface.
- Enforce HTTPS and enable HSTS after verification.
- Use unique staff accounts and least-privilege groups; `groups`/`audit` are
  superuser-only.
- Back up the database and media daily; keep at least one off-account copy.
- Review `store_auditlog` for code exports/imports and order status changes. It
  is append-only in the app/admin, but restrict direct DB/phpMyAdmin access.
- Monitor `process_orders` failures and `processing` orders.
- Keep dependencies updated within the pinned Django 5.2 line and re-run tests.
