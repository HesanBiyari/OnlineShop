# Giftbaaz | گیفت‌باز

فروشگاه اینترنتی محصولات دیجیتال و گیفت‌کارت، ساخته‌شده با **Django 5.2**، **MariaDB/MySQL** و رابط کاربری فارسی راست‌به‌چپ.

- دامنه تولید: `https://giftbazz.ir`
- مخزن: `https://github.com/HesanBiyari/OnlineShop`
- شاخه بازسازی: `rebuild/clean-architecture`
- میزبان هدف: cPanel / CloudLinux / LiteSpeed / Passenger WSGI

## معماری کوتاه

```
config/                 تنظیمات، URL ریشه، WSGI/ASGI و Passenger
store/models/           مدل‌ها بر اساس دامنه (کاتالوگ، سفارش، پرداخت، ...)
store/services/         منطق کسب‌وکار: سبد، قیمت، پرداخت، تحویل کد، کوپن
store/selectors/        کوئری‌های خواندنی
store/forms/            فرم‌های احراز هویت و پنل کارکنان
store/views/            نماهای عمومی و پنل کارکنان
store/tests/            تست‌های خودکار (۸۲ تست)
templates/              قالب‌های عمومی، پنل کارکنان و صفحه‌های خطا
static/                 دارایی‌های ظاهری (هویت تیره بنفش/فیروزه‌ای)
docs/                   مستندات معماری، مهاجرت، استقرار، امنیت و آزمون
```

برچسب اپ Django همان `store` است و نام جدول‌ها و تاریخچه مهاجرت تغییر نکرده‌اند. نسخه‌های قدیمی فایل‌های تکراری/بکاپ حذف شده‌اند و هیچ قابلیت عمومی حذف نشده است.

## اجرای محلی

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

برای اجرای محلی، محیط را صریحاً روی توسعه تنظیم کنید (پیش‌فرض پروژه production است):

```bash
# Linux/macOS
export DJANGO_ENV=development

# Windows PowerShell
$env:DJANGO_ENV="development"

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

سپس:

- فروشگاه: `http://127.0.0.1:8000/`
- پنل کارکنان: `http://127.0.0.1:8000/dashboard/`
- پنل فنی جنگو: `http://127.0.0.1:8000/django-admin/`
- ورود: `/login/` (شماره موبایل یا نام کاربری حساب‌های قدیمی/مدیر)

`/admin/` به داشبورد سفارشی هدایت می‌شود. درگاه پرداخت پیش‌فرض ZarinPal است و در محیط توسعه به‌صورت sandbox اجرا می‌شود.

## تنظیمات محیطی

همه مقادیر حساس از environment خوانده می‌شوند. فایل نمونه: [`.env.example`](.env.example)

حداقل تنظیمات تولید:

```bash
DJANGO_ENV=production
DJANGO_SECRET_KEY=<حداقل ۵۰ کاراکتر تصادفی>
DJANGO_ALLOWED_HOSTS=giftbazz.ir,www.giftbazz.ir
DJANGO_CSRF_TRUSTED_ORIGINS=https://giftbazz.ir,https://www.giftbazz.ir
DJANGO_DB_ENGINE=django.db.backends.mysql
DJANGO_DB_NAME=...
DJANGO_DB_USER=...
DJANGO_DB_PASSWORD=...
ZARINPAL_MERCHANT_ID=...
ZARINPAL_SANDBOX=false
```

تولید بدون secret معتبر، بدون `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` یا با SQLite بالا نمی‌آید. پایگاه داده باید با `utf8mb4` و `utf8mb4_unicode_ci` ساخته شود.

## آزمون و بررسی

```bash
# تنظیمات تست (SQLite در حافظه)
DJANGO_ENV=test python manage.py test store

# بررسی‌های پایه
DJANGO_ENV=test python manage.py check
DJANGO_ENV=test python manage.py makemigrations --check --dry-run
python -m pip check
python -m compileall -q config store

# تولید
DJANGO_ENV=production python manage.py check --deploy
DJANGO_ENV=production python manage.py collectstatic --noinput
```

اجرای تست روی MariaDB واقعی (همان موتور تولید) در [`docs/TESTING.md`](docs/TESTING.md) توضیح داده شده است.

## استقرار

راهنمای گام‌به‌گام cPanel/Passenger، ساخت پایگاه داده، متغیرهای محیطی، فایل‌های استاتیک/مدیا، cron و بازگردانی:

- [`docs/DEPLOYMENT_CPANEL.md`](docs/DEPLOYMENT_CPANEL.md)
- [`docs/DATABASE_MIGRATION.md`](docs/DATABASE_MIGRATION.md)

خلاصه: نصب وابستگی‌ها در virtualenv، تنظیم متغیرها، `migrate`، `collectstatic`، بررسی `check --deploy`، راه‌اندازی مجدد اپ Passenger و اجرای چک‌لیست دود.

## مستندات

| سند | موضوع |
| --- | --- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | لایه‌ها، جریان درخواست، قواعد پول و همزمانی |
| [`docs/FEATURE_AUDIT.md`](docs/FEATURE_AUDIT.md) | فهرست قابلیت‌های حفظ‌شده و وضعیت آن‌ها |
| [`docs/DATABASE_MIGRATION.md`](docs/DATABASE_MIGRATION.md) | مهاجرت ایمن `0012 → 0013` روی MariaDB |
| [`docs/DEPLOYMENT_CPANEL.md`](docs/DEPLOYMENT_CPANEL.md) | استقرار cPanel/Passenger |
| [`docs/TESTING.md`](docs/TESTING.md) | تست‌های خودکار، نتایج و محدودیت‌ها |
| [`docs/SECURITY_REVIEW.md`](docs/SECURITY_REVIEW.md) | مدل تهدید، کنترل‌ها و ریسک‌های باقی‌مانده |
| [`docs/FINAL_AUDIT.md`](docs/FINAL_AUDIT.md) | گزارش نهایی: انجام‌شده/ناموفق/مسدود/اجرا‌نشده |

## نکات امنیتی مهم

- قیمت‌ها و موجودی همیشه سمت سرور و با `Decimal` محاسبه می‌شوند؛ سشن فقط شناسه و تعداد را نگه می‌دارد.
- شروع پرداخت `POST` + CSRF است؛ بازگشت درگاه authority، مبلغ و سفارش را بررسی می‌کند و تکراری‌پذیر است.
- تحویل کد دیجیتال به‌صورت «همه یا هیچ» برای هر خط سفارش و تحت قفل ردیف انجام می‌شود.
- کدها و PINها فقط برای کاربر مجاز دیده می‌شوند؛ خروجی/ورودی CSV نیازمند مجوز و ثبت در `AuditLog` است.
- رسیدگی به سفارش‌های پرداخت‌شده اما تحویل‌نشده با cron:

```bash
python manage.py process_orders
```

## وضعیت

کد، تست‌ها و مستندات روی شاخه `rebuild/clean-architecture` آماده‌اند. استقرار واقعی روی cPanel، مهاجرت پایگاه داده تولید و پرداخت واقعی درگاه **انجام نشده‌اند**، چون دسترسی به سرور/پایگاه داده تولید و اطلاعات واقعی درگاه در این محیط وجود ندارد. جزئیات در [`docs/FINAL_AUDIT.md`](docs/FINAL_AUDIT.md).
