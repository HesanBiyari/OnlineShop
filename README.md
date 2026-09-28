# Giftbaaz | گیفت باز

فروشگاه Django برای محصولات دیجیتال و گیفت‌کارت.

## اجرا

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

برای اعمال cleanup، audit، regression tests و گزارش‌گیری یک‌مرحله‌ای:

```bash
python install_giftweb_final.py
```

## تست

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test
```

پنل اصلی از `/dashboard/` در دسترس است. مسیر `/admin/` به داشبورد سفارشی می‌رود و `/django-admin/` به عنوان fallback جنگو باقی می‌ماند.

## تنظیمات تولید

کلید و تنظیمات درگاه و امنیت از environment خوانده می‌شوند؛ قبل از انتشار، `DJANGO_DEBUG=False`، `DJANGO_SECRET_KEY`، `DJANGO_ALLOWED_HOSTS`، تنظیمات CSRF/HTTPS و اطلاعات درگاه را تنظیم کنید.
