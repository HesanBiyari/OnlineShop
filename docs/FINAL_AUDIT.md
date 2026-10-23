# Final Audit

Date: 2026-10-22
Branch: `rebuild/clean-architecture`
Repository: `https://github.com/HesanBiyari/OnlineShop`
Baseline before rebuild: `f22ffcc`
Current commit: `57c84bc` (`Rebuild store architecture, payments, tests and docs`)

## 1. Summary

The storefront is implemented as a package-based Django 5.2 application without
changing the app label `store`, the existing table names or the public URL
surface. The earlier rebuild was committed and pushed as `57c84bc`.

This audit-hardening pass addressed the findings in the external review:
payment initiation/verification state, idempotent fulfilment, stock and digital
code delivery, coupon release, zero-total orders, staff/admin permissions,
audit fail-closed behaviour, notification methods, revenue dates, HSTS/env
parsing, image validation, and migration safety.

**The audit changes are currently uncommitted.** Nothing was committed, pushed,
merged, deployed or run against production during this pass. Do not treat the
working tree as released code.

## 2. Completed

### 2.1 Payments and order state

- [x] Added `Payment.STATUS_INITIATING` and an atomic claim before the gateway
      network call, preventing concurrent initiation from creating multiple
      live authorities.
- [x] Reuses a recent redirected authority; a stale `initiating` claim may be
      retried after `PAYMENT_INITIATING_STALE_SECONDS` (default 120s).
- [x] Callback checks order, authority, payment amount and gateway status.
      Amount mismatch never calls the gateway and never marks an order paid.
- [x] Duplicate callbacks are idempotent; a paid order is never downgraded.
- [x] Inconclusive verification stays `verifying`; cron reconciliation
      re-verifies a stale attempt exactly once and does not create a new
      authority.
- [x] Definitive verification failure cancels the order, marks the payment
      `failed` and releases the coupon. A user cancel marks it `canceled`.
- [x] Payment/order/payment-reference writes are durable before fulfilment.
      Fulfilment failure cannot turn a captured payment into a failure.
- [x] Zero-total orders re-check lines, coupon reservation and payment amount,
      then use the normal paid-order fulfilment path without a gateway.
- [x] Staff order transitions are explicit; unpaid orders cannot be marked paid;
      paid orders cannot be canceled or returned to pending; manual completion
      requires `stock_consumed_at`.
- [x] Manual cancellation releases coupon/payment and is refused while a payment
      is `redirected` or `verifying` (capture race).
- [x] Orders cannot be added or deleted in Django admin.

### 2.2 Fulfilment, stock and digital codes

- [x] Added durable `Order.stock_consumed_at` and
      `Order.fulfillment_notified_at` markers.
- [x] Stock checks aggregate quantity per product/variant, so two lines for the
      same item cannot each pass and drive stock negative.
- [x] A paid order with insufficient stock stays `processing`; money is retained
      and cron retries the missing stock step.
- [x] Digital delivery is all-or-nothing per line, row-locked and idempotent.
- [x] A paid order with consumed stock but missing codes retries only delivery,
      not stock.
- [x] Used/assigned codes are immutable on single save/delete and bulk delete;
      the row is re-locked so a concurrent delivery cannot be overwritten or
      deleted.
- [x] Digital-code import rejects duplicates using casefolded comparison before
      insert, and runs in one transaction with an audit row.
- [x] Payment and completion notifications are created once; completion notice
      is retried until its marker is written.
- [x] `process_orders` now:
      - releases expired abandoned pending orders (including stale
        `initiating` and missing-payment rows, but not live redirected/verifying
        attempts);
      - reconciles stale `verifying` payments;
      - retries stock/code/loyalty/notification steps;
      - retries missing completion notifications.

### 2.3 Coupons and reporting

- [x] Coupon values/minimums have DB check constraints; percentage coupons are
      limited to 0–100; redemption amounts cannot be negative.
- [x] One redemption per coupon/user is enforced in the database.
- [x] Coupon reservation is released exactly once on failure, expiry or manual
      cancellation.
- [x] Revenue uses `paid_at`, not `created_at`.
- [x] Dashboard/analytics use explicit local-day UTC boundaries instead of
      `__date`/MySQL `CONVERT_TZ`. This fixes reports silently returning zero on
      MySQL/MariaDB without timezone tables.
- [x] `sales_today` and `orders_today` template tags use the same corrected
      periods.

### 2.4 Permissions, admin and audit

- [x] Digital-code view/export requires `store.export_digitalcode`; code
      add/change/delete requires the matching permission, and change/delete
      also require export.
- [x] `groups` and `audit` remain superuser-only.
- [x] Non-superusers cannot edit staff/superuser accounts or escalate flags.
- [x] Sensitive create/edit/delete writes fail closed: if the audit insert
      fails, the data change rolls back and the user gets an error.
- [x] Code exports are fully built before the audit insert; a failed audit
      returns no file.
- [x] `AuditLog` is append-only in the custom panel and Django admin, including
      superusers.
- [x] Django admin code screens use the same export gate; used/assigned code
      change/delete is refused.
- [x] Order status changes in Django admin are audited and wrapped in the admin
      transaction.
- [x] Order deletion is disabled in admin; payment/order-item screens remain
      read-only.
- [x] Staff-delete success pages now honour the same permission/delete checks.

### 2.5 Configuration, uploads and HTTP methods

- [x] `env_bool` accepts only explicit true/false values and rejects unknown
      strings.
- [x] HSTS seconds/include-subdomains/preload are opt-in env settings; default
      HSTS remains disabled until HTTPS is verified.
- [x] Product-image validation unwraps `ImageFieldFile`, closing the Django
      admin/form bypass. Model save and forms both validate.
- [x] Notification list is read-only on GET; marking read is POST-only.
- [x] `process_orders` avoids repeatedly selecting completed orders without a
      valid paid payment row.

### 2.6 Migrations

- [x] `0014_audit_hardening` adds fulfilment markers, payment `initiating`
      choice, coupon/redemption constraints and indexes.
- [x] The `0014` data pre-check runs **before any DDL**, because MariaDB DDL is
      not transactional. It reports negative/over-100 coupon values, negative
      redemptions and duplicate coupon/user redemptions.
- [x] `0015_backfill_fulfilment_markers` conservatively marks legacy
      paid/processing/completed orders as stock-consumed and legacy completed
      orders as notified, preventing double deduction and old notification
      bursts.
- [x] `store/tests/test_migrations.py` migrates down to `0013`, inserts legacy
      pending/paid/processing/completed rows, migrates to `0015`, and verifies
      the markers.
- [x] Production legacy `processing` orders still need manual stock/physical
      reconciliation; this is documented in `docs/DATABASE_MIGRATION.md`.

### 2.7 Tests and documentation

- [x] Added `test_fulfillment.py`, `test_zero_orders.py`, `test_order_state.py`,
      `test_permissions_extra.py`, `test_hardening.py`,
      `test_coupon_lifecycle.py`, `test_concurrency.py` and
      `test_migrations.py`.
- [x] Added regression coverage for amount mismatch, stale verification,
      reconciliation, aggregate stock, command retries, zero orders, manual
      cancellation, audit fail-closed, live-gateway cancellation, code
      immutability, notification methods, revenue periods, env parsing and image
      validation.
- [x] Updated `README.md`, `.env.example`, `docs/ARCHITECTURE.md`,
      `docs/FEATURE_AUDIT.md`, `docs/DATABASE_MIGRATION.md`,
      `docs/DEPLOYMENT_CPANEL.md`, `docs/TESTING.md` and
      `docs/SECURITY_REVIEW.md`.

## 3. Verification evidence

Environment: Windows; project virtualenv Python **3.14.0**; Django 5.2.17.
Target runtime remains Python 3.11 (not available locally).

| Check | Command | Result |
| --- | --- | --- |
| Django check | `DJANGO_ENV=test manage.py check` | `System check identified no issues (0 silenced).` |
| Migration drift | `manage.py makemigrations --check --dry-run` | `No changes detected` |
| Tests, SQLite | `DJANGO_ENV=test manage.py test` | `Ran 155 tests in 3.456s`, `OK (skipped=4)` |
| Tests, MariaDB 11.4.5 | same with `DJANGO_TEST_DB_ENGINE=django.db.backends.mysql` | `Ran 155 tests in 8.528s`, `OK` |
| Production check | production env + HSTS seconds/include/preload enabled + `check --deploy` | `System check identified no issues (0 silenced).` |
| Static files | production env + `collectstatic --noinput` | `0 copied, 136 unmodified, 376 post-processed` |
| Dependencies | `python -m pip check` | `No broken requirements found.` |
| Syntax/imports | `python -m compileall -q store config` | no output (success) |
| Migration rehearsal | `store.tests.test_migrations` on SQLite and MariaDB | passed |
| Whitespace/conflicts | `git diff --check` | no errors |

The four SQLite skips are the MariaDB/MySQL row-lock tests in
`test_concurrency.py`; they ran and passed in the MariaDB suite.

PowerShell may print `Exited with code 1` because Django writes progress to
stderr. The final `OK`/`Ran N tests` lines above are the actual test result.

### Expected deployment-check warnings

With the default `DJANGO_SECURE_HSTS_SECONDS=0`, Django reports W004 because HSTS
is deliberately opt-in. Enabling seconds without include-subdomains/preload adds
W005/W021. These are configuration warnings, not test failures. With
seconds/include/preload set, `check --deploy` is clean.

## 4. Failed work

No executed check or test remains failing after this pass.

Resolved during the pass:

- Two MariaDB revenue tests initially failed because `paid_at__date` returned
  zero on a MariaDB instance without timezone tables. Reports now use explicit
  UTC day boundaries, and all 155 tests pass on MariaDB.
- A model-import error from using `KIND_PERCENT` inside `Coupon.Meta` was fixed.
- Image validation was bypassed for `ImageFieldFile`; fixed and tested.
- Two order lines for one product could pass stock checks independently; fixed
  by aggregating required quantity.
- Manual cancellation could leave a coupon/payment reserved or race a gateway
  capture; fixed and tested.
- A concurrent code edit could overwrite a delivered code; save/delete now lock
  and re-check the row.

## 5. Blocked by access or environment

| Item | Why blocked | What is still required |
| --- | --- | --- |
| Real Python 3.11 run | only Python 3.14.0 is available locally | run the suite once in the server's 3.11 virtualenv |
| Production database migration | no production DB/SSH/cPanel access | rehearse on a copy, back up, then run `migrate` |
| cPanel/Passenger deployment | no server access | follow `docs/DEPLOYMENT_CPANEL.md` |
| Real ZarinPal payment | no merchant credentials | one low-value live initiation/callback test |
| Real SMTP delivery | no mailbox credentials | send/verify a real notification email |
| MySQL timezone tables | host-controlled | ask host to load them; app reports no longer depend on them |
| Production load/penetration test | no staging/production environment | schedule before launch |

## 6. Not run

- No deployment to cPanel/CloudLinux/LiteSpeed/Passenger.
- No migration on the production database.
- No real payment or refund with ZarinPal.
- No real email/SMS delivery.
- No production load, failover, backup-restore or penetration test.
- No automated browser/E2E suite in CI (manual browser smoke checks were done
  earlier; they are not visual regression tests).
- No production cron schedule was installed or monitored.

## 7. Residual risks / operational notes

1. Legacy `processing` orders may have stock that was never deducted. Migration
   `0015` conservatively marks them consumed to prevent double deduction; staff
   must reconcile physical stock and adjust manually.
2. Django admin date filters can appear empty when MySQL timezone tables are not
   loaded. Revenue/dashboard reports are fixed, but admin date filtering still
   depends on the database timezone tables.
3. `AuditLog` is append-only in application/admin code, but a database-level
   superuser can still alter tables. Restrict DB/phpMyAdmin access and ship audit
   logs off-box if retention matters.
4. Login throttling uses per-process locmem cache. Multiple Passenger processes
   or a restart weaken it; use proxy/WAF rate limiting if available.
5. The payment gateway and email paths are still mocked in tests. A real
   low-value payment and a real email must be checked before launch.
6. Staff cancellation is blocked for live gateway attempts; support staff need a
   documented process for checking the gateway before any exceptional action.
7. Python 3.11 compatibility is expected but not proven locally.

## 8. Git and release state

- Branch: `rebuild/clean-architecture`
- HEAD: `57c84bc87ee8521762d1fd760480b22ca6a0dda3`
- `origin/rebuild/clean-architecture` points at the same commit.
- The audit hardening changes, migrations `0014`/`0015`, new services and new
  tests are **uncommitted working-tree changes**.
- Nothing was committed, pushed, merged or deployed in this pass.
- No production data, live payment, cPanel setting or server configuration was
  modified.

**Permission is required before committing, pushing, merging or deploying these
changes.**
