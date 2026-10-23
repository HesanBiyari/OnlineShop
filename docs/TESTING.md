# Testing

## 1. Test suite layout

```
store/tests/
  helpers.py               users, products, orders, fake gateway
  test_auth.py             signup/login, phone normalization, lockout, safe next
  test_cart.py             session cart, tampering, stock clamping, variants
  test_checkout.py         order creation, coupons, totals, row locking
  test_concurrency.py      MariaDB-only simultaneous checkout/delivery
  test_coupon_lifecycle.py coupon reservation, expiry and release
  test_digital.py          all-or-nothing delivery, idempotency, shortages
  test_fulfillment.py      durable stock/code/loyalty/notification steps
  test_hardening.py        env parsing, revenue periods, notifications, uploads
  test_migrations.py       0013 -> 0015 legacy-data rehearsal
  test_order_state.py      transition rules and manual cancellation
  test_pages.py            public pages, sitemap, error pages, smoke tests
  test_payments.py         initiation, callback, amount/authority, reconciliation
  test_permissions_extra.py code permissions, audit-fail-closed, admin guards
  test_security.py         ownership, CSRF, method restrictions, permissions
  test_staff.py            staff CRUD, code import/export, audit, restrictions
  test_zero_orders.py      fully discounted orders without a gateway
```

155 tests total. Four concurrency tests require a real MariaDB/MySQL database and
are skipped on SQLite.

External boundaries are replaced in tests:

- `store.services.payments.get_gateway` is patched with `FakeGateway`;
- email uses the locmem backend;
- cache uses locmem;
- media writes to a temporary directory;
- the default database is in-memory SQLite.

## 2. Commands

### SQLite (default, fast)

```bash
export DJANGO_ENV=test          # Windows: $env:DJANGO_ENV="test"
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

### Real MariaDB/MySQL (same engine as production)

Start with a test database and a user that may create/drop it. Example local
values:

```bash
export DJANGO_ENV=test
export DJANGO_TEST_DB_ENGINE=django.db.backends.mysql
export DJANGO_TEST_DB_NAME=giftbaaz_test
export DJANGO_TEST_DB_TEST_NAME=test_giftbaaz_test
export DJANGO_DB_USER=giftbaaz
export DJANGO_DB_PASSWORD=testpass
export DJANGO_DB_HOST=127.0.0.1
export DJANGO_DB_PORT=3307

python manage.py test
```

The test database is created with `utf8mb4` / `utf8mb4_unicode_ci` (see
`config/settings/test.py`). Do not point these variables at production.

### Production settings checks

```bash
export DJANGO_ENV=production
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
export DJANGO_ALLOWED_HOSTS=giftbazz.ir,www.giftbazz.ir
export DJANGO_CSRF_TRUSTED_ORIGINS=https://giftbazz.ir,https://www.giftbazz.ir
export DJANGO_DB_ENGINE=django.db.backends.mysql
export DJANGO_DB_NAME=giftbaaz
export DJANGO_DB_USER=u
export DJANGO_DB_PASSWORD=p
export DJANGO_SECURE_HSTS_SECONDS=31536000
export DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=true
export DJANGO_SECURE_HSTS_PRELOAD=true

python manage.py check --deploy
python manage.py collectstatic --noinput
```

`check --deploy` does not require the database to be reachable. HSTS is opt-in;
with the default `DJANGO_SECURE_HSTS_SECONDS=0`, Django reports W004; enabling
seconds without include-subdomains/preload adds W005/W021. That is deliberate.
Enable and validate HSTS over real HTTPS before treating the deployment check as
clean.

## 3. Results recorded on 2026-10-22

Environment: Windows, project virtualenv, Python **3.14.0**, Django 5.2.17.
Target runtime is Python 3.11; see limitations.

| Check | Command | Result |
| --- | --- | --- |
| Django check | `DJANGO_ENV=test manage.py check` | `System check identified no issues (0 silenced).` |
| Migration drift | `manage.py makemigrations --check --dry-run` | `No changes detected` |
| Test suite (SQLite) | `manage.py test` | `Ran 155 tests ... OK (skipped=4)` |
| Test suite (MariaDB 11.4.5) | same with `DJANGO_TEST_DB_ENGINE=...mysql` | `Ran 155 tests ... OK` |
| Deployment check | production env + HSTS enabled + `check --deploy` | no issues |
| Static files | `collectstatic --noinput` | succeeded |
| Dependency consistency | `python -m pip check` | `No broken requirements found.` |
| Syntax/import compile | `python -m compileall -q config store` | OK |
| Migration rehearsal | automated `0013 -> 0015` with legacy rows | markers correct on SQLite and MariaDB |
| Earlier money migration | empty DB `0012 -> 0013` with integer rows | values preserved, `decimal(14,0)` |

Note for PowerShell users: Django writes progress to stderr; PowerShell may
report `Exited with code 1` even when the run ends with `OK`. Verify the final
`OK`/`Ran N tests` lines (or check `$LASTEXITCODE` from `cmd`).

## 4. What the tests prove

- **Money integrity**: cart and checkout ignore client-supplied prices; totals
  are recomputed from `DecimalField` values; constraints exist in the schema.
- **Coupons**: expired, invalid, over-limit and already-redeemed coupons reject
  the order instead of silently charging full price; failed payments release a
  reservation exactly once.
- **Payments**: initiation is POST-only and claims an `initiating` attempt;
  callback requires a matching authority and amount; `already paid` is
  idempotent; wrong authority/order is rejected; network uncertainty stays
  `verifying` and is confirmed by reconciliation exactly once; definitive
  failure cancels and releases the coupon; stock shortage keeps `processing`.
- **Fulfilment/order state**: stock and delivery have durable markers; a cron
  retry finishes missing steps without repeating earlier ones; zero-total orders
  use the same paid path; multiple lines for one product are checked against
  combined stock; manual completion requires consumed stock; manual cancellation
  releases a coupon and marks the payment canceled.
- **Digital delivery**: per-line all-or-nothing; repeated calls assign nothing
  new; no cross-product/variant assignment; delivered codes cannot be edited,
  deleted or bulk-deleted even under a concurrent read; import duplicates are
  rejected before insert.
- **Authorization**: non-owners get 404 for orders; non-staff cannot open the
  panel; staff without export permission cannot list/view/export codes; code
  change also needs export; staff cannot grant themselves privileges;
  `groups`/`audit` are superuser-only; orders cannot be added or deleted in
  Django admin; the audit log is append-only.
- **Audit**: if an audit insert fails, a sensitive create/edit/delete rolls back
  and the user gets an error; a code export is built before the audit and is not
  sent if auditing fails.
- **CSRF/methods**: state-changing endpoints reject GET where appropriate and
  CSRF-less POSTs; notifications are marked read only by POST.
- **Auth**: mobile normalization, duplicate prevention, password validation,
  lockout after repeated failures, safe redirect handling.
- **Data/reporting**: revenue uses `paid_at`; local-day reports use explicit UTC
  boundaries instead of MySQL `__date`/`CONVERT_TZ`; `env_bool` rejects unknown
  values; malicious/non-image uploads are rejected by both forms and model save.
- **Pages**: public routes render, sitemap/robots work, 404/403 handlers render.

## 5. Manual browser checks

A seeded local database was used with `DJANGO_ENV=development` and the
development server. Checked: home, shop, product detail, login, signup, cart,
checkout, staff dashboard, staff product list, product add/edit form, code import
and analytics. No failed network requests were observed. Staff table headers
were translated to Persian and wrapping was fixed after these checks.

These are visual smoke checks, not automated visual regression tests.

## 6. Continuous integration

`.github/workflows/ci.yml` runs on push/pull request with Python 3.11:

1. install `requirements.txt`;
2. `manage.py check`;
3. `makemigrations --check --dry-run`;
4. `collectstatic --noinput`;
5. `manage.py test`.

CI uses SQLite only. Run the MariaDB command above locally or in a dedicated
job before a production release.

## 7. Known limitations

| Limitation | Impact |
| --- | --- |
| Local interpreter is Python 3.14, not 3.11 | Syntax/behavior differences are unlikely but not fully excluded; run the suite once in the server virtualenv |
| MariaDB tests used a local portable 11.4.5 instance | Production version/data volume not exercised |
| Four concurrency tests are skipped on SQLite | They require MariaDB/MySQL; they ran and passed locally on MariaDB |
| MySQL timezone tables may be empty on cPanel | Reports avoid `__date`/`CONVERT_TZ`; Django admin date filters may still appear empty until the host loads timezone tables |
| Gateway is mocked | Real ZarinPal request/verify/callback behavior unverified |
| No real SMTP credentials | Real email delivery unverified |
| No load/penetration tests | Concurrency at production traffic and hostile input beyond the suite unverified |
| No browser automation in CI | UI regressions require manual checks |

## 8. Adding tests

1. Put shared factories in `store/tests/helpers.py`.
2. Use `TestCase` (not `TransactionTestCase`) unless testing real commit/lock
   behavior across connections.
3. Patch `store.services.payments.get_gateway`, not the old
   `store.payment_flows` module.
4. For payments, assert both the HTTP outcome and the database state (order
   status, payment status, stock, code assignment, coupon redemption).
5. For staff permissions, create users with `is_staff=True` and explicit
   `Permission` rows; superuser-only resources must also be tested as a
   non-superuser staff member.
