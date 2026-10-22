# Production deployment

The maintained, step-by-step guide is
[`docs/DEPLOYMENT_CPANEL.md`](docs/DEPLOYMENT_CPANEL.md).

Database migration (including backup, pre-flight checks and rollback) is in
[`docs/DATABASE_MIGRATION.md`](docs/DATABASE_MIGRATION.md).

Quick reference:

- App root: repository root containing `manage.py` and `passenger_wsgi.py`
- WSGI entry point: `config.wsgi:application`
- Settings: `config.settings` (defaults to production; set `DJANGO_ENV`)
- Install: `python -m pip install -r requirements.txt`
- Apply: `python manage.py migrate`
- Static: `python manage.py collectstatic --noinput`
- Verify: `python manage.py check --deploy`
- Restart: `touch tmp/restart.txt` (or cPanel's Restart button)
- Retry fulfilment: `python manage.py process_orders` (see `CRON.md`)

Do not use SQLite in production. The database must be created with
`CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`.
