# Feature Audit

This document maps the pre-rebuild storefront to the rebuilt implementation. It
records what was preserved, what was hardened, what was added as engineering
infrastructure, and what could not be verified in this environment.

The comparison baseline is `HEAD` before the rebuild (`f22ffcc`). URL names and
public paths were kept where possible. The Django app label and database table
names are unchanged.

## 1. Public storefront

| Feature | Previous behavior | Rebuilt status | Implementation / notes |
| --- | --- | --- | --- |
| Home page | hero, categories, bestsellers, trust/steps/FAQ | Preserved | `views/catalog.py:home`, `templates/home.html` |
| Product listing | search, category filter, sorting, pagination | Preserved | `views/catalog.py:shop`, selectors with prefetching |
| Product detail | gallery, variants, discount price, stock, related products | Preserved | `views/catalog.py:product_detail`; server-side variant validation |
| Recently viewed | session/user history | Preserved | `services/promotions.record_recent_view` |
| Bestseller flag/priority | staff-controlled ordering | Preserved | model fields and ordering |
| Session cart | add/update/remove/clear | Preserved and hardened | prices/stock always recomputed; malformed keys ignored |
| Checkout | contact form, coupon, order creation | Preserved and hardened | row locks, coupon re-validation, server totals |
| Coupon apply/remove | session coupon | Preserved and hardened | locked reservation, one redemption per user, release on failure/expiry/manual cancel |
| ZarinPal payment | initiation and callback | Preserved and hardened | POST + CSRF, `initiating` claim, authority/amount checks, `verifying` reconciliation, idempotent callback |
| Zero-total order | unspecified | Hardened | same paid-order fulfilment path after server-side revalidation; no gateway |
| Order history/detail | authenticated owner view | Preserved | selectors filter by user |
| Digital delivery | assign codes to paid orders | Preserved and hardened | row locks, all-or-nothing per line, durable retry, delivered codes immutable |
| Signup/login/logout | mobile-based auth | Preserved and hardened | Iranian mobile normalization, lockout, safe `next`, POST logout |
| Account page | profile and recent orders | Preserved | `views/account.py` |
| Wishlist | toggle/list | Preserved | `views/engagement.py` |
| Reviews | submit/display approved reviews | Preserved | rating constraint 1–5, approval workflow |
| Notifications | in-app list | Preserved and hardened | payment/completion notices; GET is read-only, POST marks read |
| Referral | code/profile/apply | Preserved | unique codes, self-referral rejected |
| Loyalty | points/ledger | Preserved | awarded once per paid order |
| Static pages | about/contact/faq/guide/terms/privacy | Preserved | `views/pages.py` |
| `robots.txt` | served by app | Preserved | domain from `SITE_DOMAIN` |
| Legal/error pages | basic templates | Preserved and extended | custom 403/404/500 templates |
| Sitemap | not present | Added (technical) | `/sitemap.xml` for products/categories |
| RTL Persian UI | dark purple/cyan visual identity | Preserved | same CSS variables, Tahoma, responsive/motion rules |
| Mobile navigation | bottom nav | Preserved | `templates/base.html` |

## 2. Staff panel

| Feature | Previous behavior | Rebuilt status | Notes |
| --- | --- | --- | --- |
| Dashboard | sales/orders/chart/low stock | Preserved | `views/staff.py:dashboard` |
| Product/category/variant/image/discount CRUD | generic model forms | Preserved and hardened | explicit allow-listed forms |
| Order management | list and view | Preserved and hardened | only `status` editable; paid status cannot be set manually; cancellation releases coupon/payment and is refused during a live gateway attempt |
| Payments | read-only list | Preserved | no add/change/delete |
| Coupons | CRUD | Preserved and hardened | validated value/date fields; DB constraints and redemption uniqueness |
| Reviews | approve/edit | Preserved | explicit fields |
| Users | manage accounts | Preserved and hardened | privilege fields superuser-only; staff cannot edit staff |
| Groups/permissions | superuser-only | Preserved | custom `GroupStaffForm` |
| Digital codes | list/import/export | Preserved and hardened | export gate for view/change, add for import, row-locked immutability, size/row limits, audit |
| Audit log | not present | Added (security) | `AuditLog`, `/dashboard/audit/` superuser-only, append-only, fail-closed sensitive writes |
| Analytics | revenue snapshot | Preserved and hardened | `/admin-tools/analytics/`; revenue uses `paid_at`, local-day UTC bounds |
| Django admin | `/django-admin/` fallback | Preserved and hardened | code screens require export permission |
| Staff logout | session logout | Preserved | POST-only |

Staff resource keys kept: `products`, `categories`, `variants`, `images`,
`discounts`, `codes`, `orders`, `order-items`, `payments`, `coupons`,
`coupon-redemptions`, `reviews`, `referrals`, `loyalty`,
`loyalty-transactions`, `notifications`, `recently-viewed`, `wishlist`,
`users`, `groups`, `audit`.

## 3. Business rules verified by tests

| Rule | Test coverage |
| --- | --- |
| Cart ignores tampered prices and clamps to stock | `test_cart.py` |
| Checkout recomputes totals and locks stock | `test_checkout.py` |
| Invalid/expired/reused coupon rejects the order | `test_checkout.py` |
| Coupon is released exactly once on failed payment/expiry/manual cancel | `test_payments.py`, `test_coupon_lifecycle.py`, `test_order_state.py` |
| Callback requires matching authority and amount | `test_payments.py` |
| Duplicate callback does not double-charge stock/codes | `test_payments.py`, `test_digital.py` |
| Inconclusive verification is reconciled once | `test_payments.py` |
| Insufficient stock after payment keeps order processing and cron retries | `test_payments.py`, `test_fulfillment.py` |
| Zero-total order uses revalidated paid fulfilment | `test_zero_orders.py` |
| Digital delivery is all-or-nothing per line, idempotent and immutable after delivery | `test_digital.py`, `test_permissions_extra.py` |
| Manual completion requires consumed stock; paid orders cannot be faked/canceled | `test_order_state.py` |
| Sensitive audit failure rolls back the data change | `test_permissions_extra.py` |
| Non-owner cannot view orders/payments | `test_security.py` |
| Staff code screens/exports require permission | `test_staff.py`, `test_security.py` |
| Exports/imports write audit rows | `test_staff.py` |
| Login lockout after repeated failures | `test_auth.py` |
| State-changing endpoints reject GET/CSRF-less posts | `test_security.py` |

## 4. Removed items (not product features)

| Item | Reason |
| --- | --- |
| `install_giftweb_final.py` | one-off repair script; replaced by normal Django commands |
| `*.backup_*`, `*.bak_*`, `*.visualbak_*`, `*.motionbak_*` files | duplicate/stale copies of source and templates |
| monolithic `store/views.py`, `store/models.py`, `store/forms.py` | split into packages without changing app label/table names |
| `store/payment_flows.py`, `store/payment_gateway.py` | superseded by `services/payments.py` and `services/gateway.py` |
| `store/advanced_*` modules | merged into domain packages |
| `gunicorn`, `psycopg` requirements | unused on Passenger/MariaDB target |

No public URL, template, or staff workflow was intentionally removed.

## 5. Added engineering infrastructure

- Automated test suite: 155 tests across cart, checkout, payments, durable
  fulfilment, concurrency, migrations, auth, staff permissions, security and
  page smoke tests.
- Database check constraints for money, quantities, ratings, coupon values and
  redemption uniqueness; fulfilment markers for legacy orders.
- `AuditLog` for sensitive actions, append-only and fail-closed for sensitive
  writes.
- Custom error pages (403/404/500).
- Sitemap and canonical/meta tags.
- Split settings (`base`/`dev`/`prod`/`test`) with production fail-fast checks.
- Documentation under `docs/`.

These are supporting changes, not new customer-facing features.

## 6. Not verified in this environment

| Area | Why | What remains |
| --- | --- | --- |
| Real ZarinPal payment | no merchant credentials | sandbox/mocked flow only; run one low-value live payment before launch |
| Real SMTP delivery | no mailbox credentials | console/locmem in tests |
| Production cPanel deployment | no server/SSH access | follow `docs/DEPLOYMENT_CPANEL.md` |
| Production database migration | no production DB access | follow `docs/DATABASE_MIGRATION.md` on a backup |
| Python 3.11 runtime | only Python 3.14 available locally | run the suite once in the server's 3.11 virtualenv |
| Load/penetration testing | out of scope/access | schedule before high-traffic launch |

## 7. Visual regression checks performed

Browser checks were run against a seeded local database (development settings):

- home, shop, product detail;
- login and signup;
- staff dashboard, product list, product add/edit form;
- code import/analytics screens.

All rendered without failed network requests. Staff list table headers were
translated to Persian and table wrapping was fixed after these checks.
