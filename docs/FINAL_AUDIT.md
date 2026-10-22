# Final Audit

Date: 2026-10-22
Branch: `rebuild/clean-architecture`
Baseline: `f22ffcc` (`main` checkout before the rebuild)
Repository: `https://github.com/HesanBiyari/OnlineShop`

## 1. Summary

The storefront has been rebuilt into a package-based Django 5.2 architecture
without changing the app label, table names or public URL surface. Money,
payments, digital delivery, coupons and staff permissions were hardened and
covered by automated tests. Documentation for architecture, features, database
migration, cPanel deployment, testing and security is included.

The code is **not deployed**, **not merged**, and **not pushed**. Production
database migration and a real payment were not executed because this environment
has no server, production database, cPanel, or gateway credentials.

## 2. Completed

### 2.1 Code and architecture

- [x] Split monolithic modules into `store/models/`, `services/`, `selectors/`,
      `forms/`, `views/` and `tests/`; kept Django app label `store`.
- [x] Split settings into `config/settings/{base,dev,prod,test}.py` with a
      selector that keeps `config.settings` as the Passenger entry point.
- [x] Added `config/env.py` (no `python-dotenv` dependency).
- [x] PyMySQL compatibility shim in `config/__init__.py`.
- [x] Preserved existing URL names/paths, templates, Persian RTL UI and
      dark purple/cyan visual identity.
- [x] Replaced generic staff `modelform_factory` forms with explicit,
      allow-listed forms.
- [x] Added custom 403/404/500 templates and a sitemap.
- [x] Removed stale backup/duplicate modules and the one-off
      `install_giftweb_final.py` repair script.
- [x] Cleaned `requirements.txt` (removed unused `gunicorn`/`psycopg`).
- [x] Updated `README.md`, `.env.example`, `DEPLOYMENT.md`, `CRON.md`, and added
      the `docs/` set.

### 2.2 Security and correctness

- [x] `DecimalField` money columns and database check constraints.
- [x] Server-side price/stock calculation; session stores IDs/quantities only.
- [x] Payment initiation is POST + CSRF; gateway calls run outside transactions.
- [x] Callback verifies order, issued authority and server-side amount; replay is
      idempotent; paid orders are never downgraded.
- [x] Digital delivery is row-locked, all-or-nothing per line and idempotent.
- [x] Coupon reservation is locked, one-per-user, and released once on failure.
- [x] Invalid/reused coupons reject checkout instead of silently charging full.
- [x] Code list/export gated by `store.export_digitalcode` in the staff panel and
      Django admin; imports/exports audited.
- [x] Staff privilege escalation paths closed; sensitive resources read-only.
- [x] Login throttling, safe `next`, POST logout, ownership filters.
- [x] Upload validation (size, dimensions, format, Pillow verification).
- [x] Production settings fail fast on missing secret/hosts/CSRF/SQLite.

### 2.3 Verification evidence

| Check | Result |
| --- | --- |
| `DJANGO_ENV=test python manage.py test store` (SQLite) | `Ran 82 tests ... OK` |
| Same suite on MariaDB 11.4.5 | `Ran 82 tests ... OK` |
| `python manage.py check` | no issues |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py check --deploy` (production env) | no issues |
| `python manage.py collectstatic --noinput` | succeeded |
| `python -m pip check` | no broken requirements |
| `python -m compileall -q config store` | OK |
| Migration test `0012 -> 0013` | integer rows preserved; columns `decimal(14,0)` |
| Browser smoke checks | home/shop/product/login/staff pages rendered, no failed requests |

Test distribution: auth 10, cart 9, checkout 7, digital 5, pages 4, payments 18,
security 11, staff 18.

### 2.4 Documentation delivered

- `README.md`
- `.env.example`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_AUDIT.md`
- `docs/DATABASE_MIGRATION.md`
- `docs/DEPLOYMENT_CPANEL.md`
- `docs/TESTING.md`
- `docs/SECURITY_REVIEW.md`
- `docs/FINAL_AUDIT.md`
- `DEPLOYMENT.md` / `CRON.md` reduced to pointers (no stale duplicate guidance)

## 3. Failed

No final verification command failed.

Defects found and fixed during the rebuild (for the record):

| Defect | Fix |
| --- | --- |
| `order_detail` selector returned a single object and crashed with `pk=` | selector returns a queryset; view uses `get_object_or_404` |
| Malformed cart keys broke cart count/render | strict parsing and safe integer conversion |
| Invalid coupon was dropped silently at checkout | explicit rejection with a Persian message |
| Staff table headers/cells were clipped or English | Persian labels and CSS wrapping |
| Removed `django.contrib.sitemaps` caused sitemap failure | app re-added, sitemap verified |
| Django admin exposed code screens to staff without export permission | permission gates added |
| `config/wsgi.py` docstring referenced Django 6.1 | corrected to 5.2 |

## 4. Blocked by access (not failures of the code)

| Item | Blocker | Consequence |
| --- | --- | --- |
| Real cPanel/Passenger deployment | no server/SSH/cPanel access | deployment guide written but not executed |
| Production database migration `0012 -> 0013` | no production DB access | local MariaDB rehearsal only; backup/rehearsal still required |
| Real ZarinPal payment/verify | no merchant credentials | payment logic tested with a fake gateway only |
| Real email delivery | no SMTP credentials | console/locmem email only |
| Python 3.11 runtime verification | only Python 3.14 available locally | suite passes on 3.14; run once on the server 3.11 venv |
| cPanel environment variables, cron, media permissions | no panel access | operator must apply the documented steps |
| HTTPS/HSTS/DNS/certificate validation | no production domain control | cannot verify transport end-to-end |

## 5. Not run

- Load, stress or concurrency testing at production traffic levels.
- External penetration test, SAST/DAST scanning.
- Real low-value payment and real callback replay against ZarinPal.
- Real SMTP send/open/bounce test.
- Production migration timing/lock measurement on the real data volume.
- Visual regression automation (checks were manual browser smoke tests).
- Post-deployment monitoring/alerting setup.

## 6. Git and release state

- Work is on `rebuild/clean-architecture`; `main` was not modified.
- The rebuild is committed on this branch (`Rebuild store architecture,
  payments, tests and docs`; see `git log`). The working tree was clean after
  the commit.
- No push, merge, tag or release was performed.
- No destructive Git operation (`reset --hard`, `clean -fd`, force push) was used.
- Generated/local artifacts (`.venv/`, `staticfiles/`, `db.sqlite3`, `.env`,
  media, caches) were excluded from the commit.

## 7. Required steps before launch

1. Review and commit the changes on `rebuild/clean-architecture`.
2. Run the suite in the server's Python 3.11 virtualenv.
3. Follow `docs/DATABASE_MIGRATION.md`: backup, pre-flight queries, rehearse on a
   copy, migrate during a maintenance window, verify counts/sums.
4. Follow `docs/DEPLOYMENT_CPANEL.md`: create the app, set env vars, install
   requirements, migrate, collectstatic, restart Passenger.
5. Configure cron for `process_orders` and verify its log.
6. Configure media serving with script execution disabled.
7. Execute the smoke checklist, including a real low-value ZarinPal payment and
   a repeated callback.
8. Enable HSTS after HTTPS verification; restrict `/django-admin/`.
9. Create least-privilege staff groups; verify code export permission and audit
   rows.
10. Set up backups and monitoring.

## 8. Sign-off

| Area | Status |
| --- | --- |
| Clean architecture | Complete |
| Feature preservation | Complete (audited) |
| Money/payment/digital correctness | Implemented and tested locally |
| Security hardening | Implemented; residual risks documented |
| Automated tests | 82 passing on SQLite + MariaDB |
| Documentation | Complete |
| Production deployment | **Not performed — blocked by access** |
| Production data migration | **Not performed — blocked by access** |
| Real payment/email | **Not performed — blocked by credentials** |

The rebuild is ready for review and a supervised staging/production rollout. It
is not a claim of a completed live deployment.
