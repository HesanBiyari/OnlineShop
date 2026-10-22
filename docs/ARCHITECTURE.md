# Architecture

## 1. Scope and constraints

Giftbaaz is a Django 5.2 storefront for digital products and gift cards. The
deployment target is shared hosting with cPanel, CloudLinux, LiteSpeed and
Passenger WSGI. The architecture therefore depends on:

- Python 3.11, Django 5.2.x, MariaDB/MySQL (InnoDB), PyMySQL;
- a single Passenger process group managed by the hosting panel;
- local-memory caching, in-app notifications and a cron-driven retry command;
- no Redis, Celery, RabbitMQ, Docker, Gunicorn or root-level services.

The Django app label remains `store`, and the existing table names and
migration history are preserved.

## 2. Directory layout

```
config/
  __init__.py            PyMySQL -> MySQLdb compatibility shim
  env.py                 dependency-free .env reader and typed env helpers
  settings/__init__.py   environment selector (production by default)
  settings/base.py       shared settings
  settings/dev.py        DEBUG, plain static storage, console email
  settings/prod.py       fail-fast secret/hosts/CSRF/DB checks, WhiteNoise
  settings/test.py       in-memory SQLite, locmem email/cache
  urls.py                root URL map, sitemap, error handlers
  wsgi.py, asgi.py       framework entry points
passenger_wsgi.py        cPanel/Passenger entry point
store/
  models/                domain models (catalog, orders, payments, digital,
                         promotions, engagement, audit)
  services/              business logic and side effects
  selectors/             read-side query helpers
  forms/                 auth/customer forms and explicit staff forms
  views/                 public, account, payment, staff and page views
  management/commands/   process_orders
  tests/                 automated suite
templates/               storefront, staff panel, admin tools, error pages
static/                  brand styling and JavaScript
docs/                    engineering documentation
```

## 3. Layer rules

| Layer | Responsibility | Must not |
| --- | --- | --- |
| `models` | schema, invariants expressed as properties/constraints | perform network I/O |
| `selectors` | read-only querysets with ownership filters | mutate data |
| `services` | pricing, cart resolution, checkout, payments, digital delivery, coupons, audit | trust browser prices or hold locks during network calls |
| `forms` | input validation and explicit field allow-lists | accept model-wide field maps from users |
| `views` | HTTP orchestration, permissions, messages, redirects | duplicate money/stock rules |
| `templates` | presentation | compute authoritative prices |

## 4. Request flows

### 4.1 Catalog and cart

```
GET /shop/ -> selectors.catalog -> Product/ProductVariant -> template
POST /cart/add/<pk>/ -> services.cart.add_to_cart
    -> validate active variant and stock
    -> session["cart"] = {"<product_id>:<variant_id>": quantity}
GET /cart/ -> services.cart.get_cart_items
    -> reload products/variants/discounts
    -> clamp quantities to current stock
    -> recompute Decimal line totals
```

The session never stores prices. A stale or tampered session can only change
which identifiers/quantities are requested; the server recomputes everything.

### 4.2 Checkout

```
POST /checkout/ (authenticated, CSRF)
  -> services.checkout.create_order_from_cart
     BEGIN
       lock product rows (SELECT ... FOR UPDATE)
       re-resolve cart, prices and stock
       lock and re-validate coupon (if any)
       create Order + OrderItem rows + CouponRedemption + Payment
     COMMIT
  -> redirect /payment/<order_id>/
```

If a coupon expired, was already redeemed by the user, or no longer yields a
positive discount, checkout raises `CouponNoLongerValidError` and the order is
not created. The customer is never silently charged the undiscounted total.

### 4.3 Payment initiation

```
POST /payment/<order_id>/ (owner only, CSRF)
  -> services.payments.start_payment
     BEGIN: lock order + payment, reject non-pending orders
     COMMIT
     network: gateway.create_payment(...)   # outside any transaction
     BEGIN: lock again, store authority/status
     COMMIT
  -> 302 to gateway
```

A valid redirected authority is reused for a configurable window
(`PAYMENT_REDIRECT_REUSE_SECONDS`, default 1800s). Stale `created` attempts are
re-issued. A paid order is never downgraded.

### 4.4 Gateway callback

```
GET /payment/<order_id>/callback/?Authority=...&Status=...
  -> services.payments.process_callback
     - order must exist
     - already paid -> return "already_paid" (idempotent success)
     - payment must exist and authority must match
     - canceled order -> reject
     - Status != OK -> mark canceled, release coupon once
     - lock payment, mark "verifying"
     - network: gateway.verify_payment(amount=order.total_amount, authority)
     - lock again; if already paid -> success
     - failure -> mark failed, release coupon
     - success:
         * lock stock rows; if insufficient -> order stays "processing"
         * decrement stock
         * mark order paid with payment reference
         * deliver digital codes (all-or-nothing per line)
         * award loyalty points / notification once (savepoint)
         * status completed if all lines delivered, else processing
```

Repeated callbacks cannot deduct stock twice or deliver codes twice, because
the finalization path re-checks `order.is_paid` under a row lock and the
digital delivery function is already idempotent.

### 4.5 Digital delivery

`services.digital.deliver_digital_codes(order)`:

1. locks candidate `DigitalCode` rows with `select_for_update()`;
2. counts already assigned codes per line;
3. if enough unused codes exist, assigns exactly the needed quantity;
4. if not enough exist, assigns none for that line and returns `False`.

`process_orders` can be run repeatedly from cron. It re-attempts delivery for
`paid`/`processing` orders and moves fully delivered orders to `completed`.

## 5. Data model summary

| Model | Purpose | Key constraints |
| --- | --- | --- |
| `Category`, `Product`, `ProductVariant` | catalog | unique category slug, unique SKU, non-negative prices |
| `ProductImage` | gallery | first image becomes main; one main image enforced in `save()` |
| `Discount` | per-product percent discount | percent 0–100, start ≤ end |
| `Order`, `OrderItem` | immutable commercial snapshot | non-negative totals, quantity ≥ 1 |
| `Payment` | one gateway attempt per order | one-to-one order, unique non-null authority |
| `DigitalCode` | saleable secret inventory | consistent used/unused state, export permission |
| `Coupon`, `CouponRedemption` | discounts and one-per-user redemption | unique code, one redemption per order |
| `Referral`, `LoyaltyAccount`, `LoyaltyTransaction` | growth features | one profile/account per user |
| `Review`, `Wishlist`, `Notification`, `RecentlyViewed` | engagement | rating 1–5 |
| `AuditLog` | append-only sensitive-action trail | actor nullable on user deletion |

Money fields use `DecimalField(max_digits=14, decimal_places=0)`, representing
whole Toman. There are no floats in pricing paths. Check constraints are
declared in the models and created by migration `0013`.

## 6. Configuration

`config.settings` is a selector:

- `DJANGO_ENV=development|dev|local` -> `dev.py`
- `DJANGO_ENV=test|testing` -> `test.py`
- anything else (including unset) -> `prod.py`
- `manage.py test` automatically selects `test.py` when `DJANGO_ENV` is unset.

`prod.py` fails fast when `DJANGO_SECRET_KEY` is missing or shorter than 50
characters, when allowed hosts/CSRF origins are empty, or when SQLite is
selected. `base.py` reads all secrets from the environment; `.env` is a
developer convenience only and is git-ignored.

Production static files use `CompressedManifestStaticFilesStorage`, served by
WhiteNoise. User uploads stay on the filesystem under `DJANGO_MEDIA_ROOT` and
must be served by the web server, never executed.

## 7. Permissions and sensitive data

- Public catalog, cart, checkout and account views require no special role.
- Order, payment, download and account views filter by `request.user`.
- Staff panel access requires `is_staff`.
- `codes` screens require `store.export_digitalcode` (or superuser).
- Code creation/editing/deletion use the corresponding model permissions.
- `groups` and `audit` are superuser-only.
- Sensitive resources (`codes`, `orders`, `payments`, `coupons`, `users`) are
  audited on change; order status transitions and code imports/exports always
  write an `AuditLog` row.
- Django admin is a technical fallback at `/django-admin/`; its code screens
  apply the same export-permission gate.

## 8. Failure handling

- Gateway creation or verification network errors are logged and surfaced as
  safe Persian messages; `verifying` attempts remain retryable.
- A payment that succeeds while stock is insufficient is kept as `processing`
  for manual fulfilment; money is never silently discarded.
- Loyalty/notification failures are isolated in a savepoint and cannot roll
  back a confirmed payment.
- Digital delivery shortage leaves the order `processing`; `process_orders`
  retries later.
- Protected foreign keys prevent deleting products/orders that financial rows
  depend on; the staff panel shows a Persian error instead of crashing.

## 9. Deliberate non-goals

- No background worker/queue: cron plus idempotent commands cover retries.
- No multi-gateway abstraction beyond the current ZarinPal client.
- No SPA/front-end build pipeline: server-rendered templates and small vanilla
  scripts preserve the existing visual identity.
