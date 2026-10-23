# Database Migration Guide

## 1. What changes in migration `0013`

Source: `store/migrations/0013_auditlog_alter_digitalcode_options_and_more.py`
(depends on `0012_alter_digitalcode_code`).

| Change | Tables/columns | Risk |
| --- | --- | --- |
| Money columns become `DECIMAL(14,0)` | `store_product.price`, `store_productvariant.price`, `store_order.total_amount`, `store_orderitem.unit_price`, `store_orderitem.total_price`, `store_payment.amount`, `store_coupon.value`, `store_coupon.min_order_amount`, `store_couponredemption.amount` | Low: existing integers convert exactly; no rounding |
| Check constraints | non-negative money, `orderitem.quantity >= 1`, `review.rating BETWEEN 1 AND 5` | Migration fails if legacy rows violate a rule |
| `AuditLog` table + indexes | `store_auditlog` | New table only |
| `DigitalCode` model option | adds `export_digitalcode` permission | No column change; permission row created by Django |
| `Discount.percent` validators | model-level 0–100 | No column type change |

The conversion is exact because every money value is a whole Toman amount and
the target field has `decimal_places=0`. No data is rewritten or dropped.

Local verification already performed: an empty MariaDB 11.4.5 database was
migrated to `0012`, integer rows were inserted, then migrated to `0013`. Values
were preserved and `SHOW COLUMNS` reported `decimal(14,0)`. This does **not**
replace a backup and a rehearsal on a copy of the production database.

## 1A. What changes in migrations `0014` and `0015`

Source: `store/migrations/0014_audit_hardening.py` and
`store/migrations/0015_backfill_fulfilment_markers.py`.

| Migration | Change | Risk |
| --- | --- | --- |
| `0014` | Adds nullable `order.stock_consumed_at` and `order.fulfillment_notified_at` | Low; no rewrite |
| `0014` | Adds `initiating` to `Payment.status` choices | No column type change |
| `0014` | Adds Coupon non-negative/percentage check constraints | Fails if legacy data violates them |
| `0014` | Adds unique `(coupon, user)` redemption and non-negative redemption amount | Fails if duplicate or negative redemptions exist |
| `0015` | Backfills fulfilment markers on legacy paid/processing/completed orders | Data-only; conservative, see below |

The data pre-check in `0014` intentionally runs **before any DDL**. MariaDB DDL
is not transactional; if a later constraint failed after adding columns, the
migration could be left half-applied. Run these read-only queries on a copy of
production first:

```sql
SELECT id, code, kind, value, min_order_amount
FROM store_coupon
WHERE value < 0 OR min_order_amount < 0
   OR (kind = 'percent' AND value > 100);

SELECT id, coupon_id, order_id, user_id, amount
FROM store_couponredemption
WHERE amount < 0;

SELECT coupon_id, user_id, COUNT(*) AS uses
FROM store_couponredemption
GROUP BY coupon_id, user_id
HAVING COUNT(*) > 1;
```

If duplicates exist, take a backup and decide manually which redemption to keep
(usually the one belonging to a paid/completed order). Then recompute the cached
counter, do not simply delete rows:

```sql
SELECT coupon_id, COUNT(*) FROM store_couponredemption GROUP BY coupon_id;
-- After reviewed cleanup:
UPDATE store_coupon c
SET used_count = (
  SELECT COUNT(*) FROM store_couponredemption r WHERE r.coupon_id = c.id
);
```

`0015` cannot know whether a legacy `processing` order had already deducted
stock: the old schema had no marker. To avoid deducting stock twice, it marks
every legacy `paid`, `processing` and `completed` order as having consumed stock
(using `paid_at`, falling back to `created_at`). It also marks completed orders
as already notified so the migration does not send a burst of old notifications.

**Manual reconciliation is required for legacy `processing` orders that were
waiting for stock.** If stock was never deducted, the marker suppresses a future
deduction and the physical stock count is overstated. Staff must review those
orders, compare them with inventory, and adjust stock manually. Document the
adjustment and keep the order/audit history. Do not reset `stock_consumed_at` on
an order unless the stock deduction is verified.

Automated rehearsal: `store/tests/test_migrations.py` migrates down to `0013`,
inserts paid/pending/processing/completed legacy orders, migrates to `0015`, and
asserts the markers. It passes on SQLite and MariaDB 11.4.5 locally.

### Historical migration `0007` note

Migration `0007` was amended in this rebuild to remove two conditional
(`UniqueConstraint(condition=...)`) constraints:

- `unique_non_empty_payment_ref` on `store_order.payment_ref`;
- `one_main_image_per_product` on `store_productimage.product`.

Django's MySQL/MariaDB backend reports `supports_partial_indexes = False` and
silently skips such constraints, so the original migration state no longer
matched the models (and a fresh install could create the constraints on SQLite
while MariaDB ignored them). Removing them from `0007` keeps migration state in
sync and lets `makemigrations --check` pass without an extra migration.

Implications for an existing database:

- If `store.0007` is already recorded in `django_migrations`, it will not run
  again; this edit does not modify existing data or indexes.
- If an earlier SQLite/PostgreSQL deployment did create those indexes, inspect
  and drop only the two named indexes if they conflict with current behavior.
  MariaDB deployments should not have them.
- The rules are enforced in application code: `Payment` is one-to-one with
  `Order`, and `ProductImage.save()` assigns a single main image under a row
  lock.

Do not "fix" this by adding a new conditional `UniqueConstraint`; it will not
be enforced on the target database.

## 2. Prerequisites

- Django 5.2 supports MariaDB 10.6+ / MySQL 8.0.11+. Confirm the server version:
  ```sql
  SELECT VERSION();
  ```
- InnoDB tables (Django default).
- Database/table charset `utf8mb4` and collation `utf8mb4_unicode_ci`. Persian
  text inserts fail with error 1366 when this is wrong.
- Enough disk space for a full backup and the altered tables.
- A maintenance window; `ALTER TABLE` on large tables can take time and locks.

Check charset:

```sql
SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = DATABASE();

SHOW CREATE TABLE store_product;
SHOW CREATE TABLE store_orderitem;
```

If the database is not `utf8mb4`, fix it before migrating. On cPanel the safest
route is to create the database with the correct charset in the panel, or run
(per table, during maintenance):

```sql
ALTER DATABASE `DB_NAME`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE store_product
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- repeat for every store_* and auth_* table
```

## 3. Pre-flight checks (read-only)

Run these on the production database **before** migrating. Every query should
return `0`.

```sql
-- Negative money values (would violate new constraints)
SELECT COUNT(*) FROM store_product          WHERE price < 0;
SELECT COUNT(*) FROM store_productvariant   WHERE price < 0;
SELECT COUNT(*) FROM store_order            WHERE total_amount < 0;
SELECT COUNT(*) FROM store_orderitem        WHERE unit_price < 0 OR total_price < 0;
SELECT COUNT(*) FROM store_payment          WHERE amount < 0;
SELECT COUNT(*) FROM store_coupon           WHERE value < 0 OR min_order_amount < 0;
SELECT COUNT(*) FROM store_couponredemption WHERE amount < 0;

-- Invalid quantities / ratings
SELECT COUNT(*) FROM store_orderitem WHERE quantity < 1;
SELECT COUNT(*) FROM store_review    WHERE rating < 1 OR rating > 5;

-- Discount percent (model validation; DB check already exists)
SELECT COUNT(*) FROM store_discount WHERE percent < 0 OR percent > 100;
```

Record baseline counts and sums for post-migration comparison:

```sql
SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS total
FROM store_order;

SELECT COUNT(*) AS items, COALESCE(SUM(total_price), 0) AS total
FROM store_orderitem;

SELECT COUNT(*) AS codes FROM store_digitalcode;

SELECT COUNT(*) AS products, COALESCE(SUM(price), 0) AS total
FROM store_product;
```

If any pre-flight query is non-zero, fix the rows first (or document an approved
exception and adjust the migration). Do not delete financial rows to make a
constraint pass.

## 4. Backup

### Option A: mysqldump (preferred)

```bash
mysqldump \
  --single-transaction --quick --routines --triggers \
  --default-character-set=utf8mb4 \
  -h localhost -u DB_USER -p DB_NAME \
  > /home/CPANEL_USER/backups/giftbaaz-before-0015-$(date +%F-%H%M).sql
```

Verify the dump is non-empty and contains `CREATE TABLE`/`INSERT` statements.
Store it outside the application root.

### Option B: cPanel phpMyAdmin

Select the database -> Export -> Custom -> SQL -> save the file locally and on
the server. Include structure and data.

Also back up uploaded media and the current code state (git commit/tag).

## 5. Migration procedure

```bash
# 1. Activate the application's virtualenv
source /home/CPANEL_USER/virtualenv/APP_ROOT/3.11/bin/activate
cd /home/CPANEL_USER/APP_ROOT

# 2. Confirm code and pending migrations
git rev-parse --short HEAD
python manage.py showmigrations store
python manage.py migrate --plan

# 3. Apply (maintenance window)
python manage.py migrate

# 4. Verify Django's view of history
python manage.py showmigrations store
```

`python manage.py migrate` applies all pending migrations, including Django's
own `auth`/`admin`/`sessions` migrations if this is a fresh database. On an
existing production database it should add `store.0014` and `store.0015` (and
`store.0013` first if that migration has not yet been applied).

If the host cannot run long requests, run the command over SSH or cPanel
Terminal; do not trigger migrations from a web request.

## 6. Post-migration verification

```sql
SHOW COLUMNS FROM store_product        LIKE 'price';
SHOW COLUMNS FROM store_order          LIKE 'total_amount';
SHOW COLUMNS FROM store_payment        LIKE 'amount';
-- Expect: decimal(14,0)

SHOW COLUMNS FROM store_order LIKE 'stock_consumed_at';
SHOW COLUMNS FROM store_order LIKE 'fulfillment_notified_at';
-- Expect: datetime(6), NULL allowed

SELECT COUNT(*) FROM store_auditlog;

SELECT status,
       COUNT(*) AS orders,
       SUM(stock_consumed_at IS NULL) AS without_stock_marker,
       SUM(fulfillment_notified_at IS NULL) AS without_delivery_notice
FROM store_order
GROUP BY status;

SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS total
FROM store_order;
```

For legacy `processing` rows, compare against the stock reconciliation notes in
section 1A before trusting the marker.

Compare the counts/sums with the pre-flight baseline. Then:

```bash
python manage.py check --deploy
python manage.py collectstatic --noinput
python manage.py process_orders
```

Smoke-test: home, shop, product, add to cart, checkout with a coupon, payment
initiation (sandbox or a low-value real payment), order history, staff dashboard,
code list/export (with a permitted account), and a repeated callback.

Restart the Passenger application after deploying new code or environment
variables.

## 7. Rollback

**Preferred:** restore the backup taken in section 4.

```bash
mysql -h localhost -u DB_USER -p DB_NAME \
  < /home/CPANEL_USER/backups/giftbaaz-before-0015-YYYY-MM-DD-HHMM.sql
```

**Django reverse migration** (`python manage.py migrate store 0013`) can undo
`0014`/`0015` because the field additions have a reverse, but it is not
recommended for production:

- MySQL/MariaDB DDL commits implicitly, so a partially failed migration cannot
  be rolled back atomically.
- Reversing `0014` drops the fulfilment markers and the new coupon constraints.
- Reversing to `0012` would additionally drop `store_auditlog` and its history.
- If any code has already written decimal values (all whole Toman), the reverse
  to integer is lossless, but this should still be rehearsed on a copy.

If a migration fails halfway, do **not** re-run it blindly. Capture the error,
inspect `SHOW CREATE TABLE` for the affected tables, restore the backup, fix the
cause, and retry during a new maintenance window.

## 8. Fresh-install path

For a brand-new database:

```sql
CREATE DATABASE giftbaaz
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'giftbaaz'@'localhost' IDENTIFIED BY '...';
GRANT ALL PRIVILEGES ON giftbaaz.* TO 'giftbaaz'@'localhost';
FLUSH PRIVILEGES;
```

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

A fresh install runs `0001` through `0015` directly; the data-conversion and
legacy-backfill concerns above only apply to an existing database.

## 9. Notes for reviewers

- Migrations `0013` and `0014` were generated by Django 5.2.17 and
  `makemigrations --check --dry-run` reports no pending model changes.
- The suite passes on both SQLite and MariaDB 11.4.5, including an automated
  `0013 -> 0015` migration rehearsal with legacy paid/pending/processing/
  completed rows.
- Production execution and timing on the real data volume remain unverified
  because server/database access was not available.
- The `0014` precheck intentionally runs before DDL. MariaDB DDL is not
  transactional; if data must be cleaned, do it on a backup and re-run the
  migration from a known state.
