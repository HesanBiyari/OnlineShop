# Security Review

## 1. Scope and method

Reviewed: Django settings, URL map, authentication, cart/checkout, payment
initiation and callback, digital delivery, coupon handling, staff panel, Django
admin fallback, templates, upload handling, export/import, audit trail, and the
production/deployment configuration.

Methods: source review, threat modeling, targeted tests (`store/tests/`),
framework checks (`manage.py check`, `check --deploy`), dependency check
(`pip check`), and manual browser checks. No external penetration test, SAST
tool, or production access was available.

## 2. Assets

| Asset | Why it matters |
| --- | --- |
| Digital codes and PINs | directly redeemable value; disclosure = financial loss |
| Payment authority/reference and order totals | fraud, replay, wrong-amount charging |
| Customer PII (name, mobile, email, orders) | privacy and support/social-engineering risk |
| Staff accounts and permissions | full catalog/order/code control |
| Audit log | accountability for sensitive actions |
| Database and backups | contain all of the above |
| ZarinPal merchant ID / SMTP credentials | financial and reputational impact |

## 3. Trust boundaries

1. **Browser -> Django**: untrusted input (prices, quantities, IDs, coupon
   codes, callback query parameters, uploaded files, redirect targets).
2. **Django -> ZarinPal**: network responses are untrusted; only the server
   decides amounts and verifies authorities.
3. **Django -> MariaDB**: trusted, but row-level races still matter.
4. **Staff -> panel**: authenticated but not fully trusted; least privilege.
5. **cPanel/Passenger -> app**: environment, proxy headers, filesystem
   permissions, static/media serving.
6. **Operator -> backups/logs**: secrets and personal data leave the app.

## 4. Controls in place

### Authentication

- Passwords use Django's default hashers; validators enforce length, common
  password, numeric-only and similarity checks.
- Signup requires a normalized Iranian mobile number and a unique email.
- Login accepts mobile numbers and existing plain usernames (for
  `createsuperuser`/legacy staff); new signups still require a mobile.
- Failed logins are throttled per IP+identifier (`AUTH_MAX_ATTEMPTS=5`,
  `AUTH_LOCKOUT_SECONDS=900`), and lockout is audited.
- Logout is POST-only; `next` redirects are validated with
  `url_has_allowed_host_and_scheme`.
- Session and CSRF cookies are `HttpOnly`/`SameSite=Lax`, and `Secure` in
  production.

### Authorization

- Customer order/payment views filter by `request.user`; a non-owner gets 404.
- Staff panel requires `is_staff`.
- Digital code list/export requires `store.export_digitalcode`; code
  add/change/delete require the matching model permission.
- `groups` and `audit` are superuser-only.
- Non-superusers cannot edit staff/superuser accounts or grant privileges.
- Django admin code screens require export permission for view/change/module
  access and model permissions for add/delete.
- Payments and order items are read-only in the panel; order money/ownership is
  not editable; paid status cannot be set manually.
- `robots.txt` disallows staff/account/payment paths (defence in depth, not
  access control).

### CSRF and HTTP methods

- Django CSRF middleware is enabled globally.
- Cart mutations, wishlist/review/coupon/referral actions, payment initiation,
  staff delete, and logouts are POST-only and carry `{% csrf_token %}`.
- The payment callback is GET because the gateway redirects the browser; it is
  safe only with a matching issued authority and is idempotent.

### Money and inventory integrity

- All amounts use `DecimalField(max_digits=14, decimal_places=0)` (whole Toman).
- The session cart stores identifiers/quantities only; prices, discounts and
  stock are recalculated on every read.
- Checkout locks product/variant rows, revalidates the coupon and recomputes the
  total; the browser cannot submit a price.
- Database check constraints reject negative money, non-positive quantities and
  invalid ratings.
- Coupons are reserved under a row lock, limited to one redemption per user, and
  released exactly once on a failed/canceled payment.
- Invalid/expired/reused coupons reject the order instead of charging the
  undiscounted total.

### Payments

- Initiation is POST + CSRF and owner-only; non-pending orders cannot be paid.
- Gateway network calls happen outside database transactions.
- The callback requires the order, a payment row, and an exact authority match.
- Verification uses the server-side order total, not a client value.
- `order.is_paid` is rechecked under a row lock; duplicate callbacks cannot
  deduct stock or deliver codes twice.
- A paid order is never downgraded.
- Network/verify uncertainty leaves a retryable `verifying` state; coupons are
  not released on an inconclusive result.
- A successful payment with insufficient stock is kept `processing` for manual
  fulfilment.

### Digital delivery and exports

- Delivery locks unused code rows and assigns exactly the ordered quantity.
- Delivery is all-or-nothing per line; a shortage consumes nothing for that
  line and leaves the order `processing`.
- Repeated delivery calls assign nothing new.
- Codes/PINs are shown only on the owner's order detail after assignment.
- CSV export requires explicit permission, sets `Cache-Control: no-store`, and
  writes an audit row. Imports validate size/rows/product/variant/duplicates and
  write an audit row.
- CSVs are UTF-8 with BOM for Excel compatibility.

### Uploads

- Product images are limited by size and dimensions and verified with Pillow.
- Only JPEG/PNG/WEBP/GIF are accepted; MIME type is checked when provided.
- All uploads are validated before any file is saved.
- Media must be served by the web server with script execution disabled (see
  deployment guide).

### Auditing and logging

- `AuditLog` records code exports/imports, staff object changes, order status
  changes and login lockouts, with actor, target, IP (direct peer only) and
  JSON-safe details.
- Logging never includes request bodies, passwords, card data or full codes.
- `X-Forwarded-For` is deliberately ignored for audit IPs because shared
  hosting may not sanitize it.

### Configuration and transport

- Production fails fast without a 50+ character secret, allowed hosts, CSRF
  origins, and a non-SQLite database.
- `DEBUG=False`, `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`,
  same-origin referrer/opener policies.
- HTTPS redirect, secure cookies, HSTS (configurable; default 0 until enabled),
  and `SECURE_PROXY_SSL_HEADER` for Passenger/LiteSpeed.
- Static files use a hashed manifest; WhiteNoise does not serve user uploads.
- No raw SQL, `extra()`, `RawSQL`, `mark_safe`, `|safe`, `eval`, `exec`,
  `subprocess`, or `csrf_exempt` in application code.

## 5. Findings fixed during the rebuild

| # | Finding | Resolution | Evidence |
| --- | --- | --- | --- |
| 1 | Payment initiation was reachable by GET, enabling CSRF-ish payment spam | POST + CSRF, owner check, never-cache response | `test_payments.py`, `test_security.py` |
| 2 | Callback could be replayed to deduct stock/deliver codes twice | Locked, idempotent finalization; `already_paid` outcome | `test_payments.py`, `test_digital.py` |
| 3 | Client-supplied totals could influence charging | Server-side Decimal recalculation and locked checkout | `test_cart.py`, `test_checkout.py` |
| 4 | Invalid coupon silently charged full price | Checkout rejects with an explicit error | `test_checkout.py` |
| 5 | Generic staff forms exposed order totals, payment rows and privilege flags | Explicit per-resource forms; read-only sensitive resources | `test_staff.py` |
| 6 | Any staff member could list/export digital codes | `export_digitalcode` gate in panel and Django admin | `test_staff.py`, `test_security.py` |
| 7 | Code exports/imports were not attributable | `AuditLog` rows for both paths | `test_staff.py` |
| 8 | Race conditions in checkout/delivery | `select_for_update()` and all-or-nothing assignment | `test_checkout.py`, `test_digital.py` |
| 9 | Malformed cart keys could break cart count/render | Strict key parsing and safe integer conversion | `test_cart.py` |
| 10 | Login had no brute-force protection; `next` could be open | Cache lockout + validated redirects | `test_auth.py` |
| 11 | Money stored as integers/floats without DB constraints | `DecimalField` + check constraints (migration 0013) | migration test, `test_checkout.py` |
| 12 | Staff could edit their own/admin accounts and privileges | Superuser-only privilege fields; staff-account protection | `test_staff.py` |

## 6. Residual risks and recommendations

| Risk | Severity | Recommendation |
| --- | --- | --- |
| Login throttling uses per-process `LocMemCache`; multiple Passenger processes do not share counters and a restart clears them | Medium | Add proxy/WAF rate limiting or a shared cache if the host provides one; keep the 5-attempt limit |
| No 2FA for staff accounts | Medium | Enable 2FA at the proxy/SSO layer or restrict `/dashboard/` and `/django-admin/` by IP |
| `/django-admin/` is reachable from the internet (login required) | Medium | IP-restrict it at LiteSpeed/cPanel; staff should normally use `/dashboard/` |
| No Content-Security-Policy header | Medium | Add a tested CSP at the web server; inline styles/scripts currently make a strict policy non-trivial |
| Digital codes/PINs are stored in plaintext in the database and backups | High if DB/backup leaks | Least-privilege DB user, encrypted off-site backups, restrict phpMyAdmin access, rotate credentials |
| Media files are served directly and are not re-encoded | Low/Medium | Keep script execution disabled; consider re-encoding uploads or a separate media domain |
| CSV exports can contain spreadsheet formula prefixes (`=`, `+`, `-`, `@`) | Low | Open exports as text/import rather than double-clicking; or add a documented escaping policy if operators need Excel |
| `SECURE_PROXY_SSL_HEADER` trusts `X-Forwarded-Proto` | Low | Ensure LiteSpeed/Passenger overwrites the header; do not expose the app directly |
| HSTS is disabled until the operator enables it | Low | Enable after HTTPS verification; avoid preload until confident |
| Audit log is not immutable; a superuser can delete entries in Django admin | Medium | Restrict superuser access, ship audit rows to external storage, define retention |
| No global request rate limiting / bot protection | Medium | Add at the proxy/WAF layer; monitor 4xx/5xx and login failures |
| Dependency pins are versions, not hashes | Low | Use a private index or `--require-hashes` if the host supports it |
| Signup reveals whether a phone/email is registered | Low | Acceptable for UX; consider generic messaging if enumeration is a concern |
| No load/concurrency test at production scale | Medium | Run a staging load test before campaigns; verify row-lock behavior under real traffic |
| Real gateway/SMTP behavior unverified | High for launch | Execute a low-value live payment and a real email test before announcing |

## 7. Verification performed

- `DJANGO_ENV=test python manage.py check` -> no issues.
- Production `check --deploy` with a real-length secret, hosts, CSRF origins,
  MySQL engine and HSTS preload -> no issues.
- 82 automated tests pass on SQLite and MariaDB 11.4.5, including authorization,
  CSRF/method, replay, coupon, stock-shortage and export-permission cases.
- `pip check` -> no broken requirements.
- No raw SQL/`safe`/`csrf_exempt` usage found in application code.
- Browser smoke checks showed no failed network requests on public/staff pages.

## 8. Launch security checklist

- [ ] Restore/verify database and media backups.
- [ ] Set a unique 64+ character `DJANGO_SECRET_KEY`.
- [ ] Set `DEBUG=false`, real `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`.
- [ ] Confirm HTTPS, secure cookies, proxy header and callback URL.
- [ ] Enable HSTS after verification.
- [ ] Disable ZarinPal sandbox and use the real merchant ID.
- [ ] Create least-privilege staff groups; verify code export permission.
- [ ] Restrict or monitor `/django-admin/`.
- [ ] Disable script execution and directory listing in media.
- [ ] Protect backups and phpMyAdmin; rotate DB/SMTP credentials.
- [ ] Configure cron for `process_orders` and alert on failures.
- [ ] Run one real low-value payment and verify idempotent callback handling.
- [ ] Review `store_auditlog` after the first staff operations.
