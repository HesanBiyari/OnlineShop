# Production deployment

## cPanel / Passenger
Project root: OnlineShop root
WSGI: config.wsgi:application

Install:
    python -m pip install -r requirements.txt

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
