from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Giftbaaz custom visual system:
# glossy 2.5D / 3D-inspired, dark, premium, purple/cyan/gold.
# These are original vector assets, not Apple-owned emoji assets.

LOGO_SVG = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 620 150"><defs><linearGradient id="p" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#b76cff"/><stop offset=".5" stop-color="#6d4aff"/><stop offset="1" stop-color="#22d3ee"/></linearGradient></defs><g transform="translate(14 14)"><rect width="118" height="118" rx="30" fill="#10182a"/><rect x="12" y="24" width="94" height="88" rx="22" fill="url(#p)"/><path d="M59 25v87M18 51h82" stroke="#fff" stroke-width="8" stroke-linecap="round" opacity=".92"/><path d="M38 29c-7-20 8-27 20-5 12-22 27-15 20 5" fill="none" stroke="#fff" stroke-width="8" stroke-linecap="round"/><text x="59" y="92" text-anchor="middle" font-family="Arial,sans-serif" font-size="48" font-weight="900" fill="#fff">G</text></g><text x="156" y="92" font-family="Arial,sans-serif" font-size="66" font-weight="900" fill="#fff">Giftbaaz</text><text x="160" y="122" font-family="Arial,sans-serif" font-size="17" fill="#9aa4bb">Digital Gifts • Game Cards • More</text></svg>"""

MARK_SVG = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><defs><linearGradient id="p" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#b76cff"/><stop offset=".5" stop-color="#6d4aff"/><stop offset="1" stop-color="#22d3ee"/></linearGradient></defs><rect x="6" y="14" width="116" height="108" rx="30" fill="url(#p)"/><path d="M64 15v106M14 46h100" stroke="#fff" stroke-width="8" stroke-linecap="round" opacity=".92"/><path d="M42 20c-8-20 8-25 22-5 14-20 30-15 22 5" fill="none" stroke="#fff" stroke-width="8" stroke-linecap="round"/><text x="64" y="99" text-anchor="middle" font-family="Arial,sans-serif" font-size="57" font-weight="900" fill="#fff">G</text></svg>"""

HERO_SVG = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 700"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#050713"/><stop offset=".55" stop-color="#111334"/><stop offset="1" stop-color="#240b40"/></linearGradient><linearGradient id="gift" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#cf7dff"/><stop offset=".45" stop-color="#6d4aff"/><stop offset="1" stop-color="#27d7f2"/></linearGradient><linearGradient id="cyan" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#62efff"/><stop offset="1" stop-color="#4d73ff"/></linearGradient></defs><rect width="1200" height="700" rx="42" fill="url(#bg)"/><circle cx="850" cy="250" r="210" fill="#6d4aff" opacity=".15"/><circle cx="930" cy="470" r="170" fill="#22d3ee" opacity=".11"/><g opacity=".9"><rect x="755" y="105" width="150" height="230" rx="25" fill="url(#cyan)" transform="rotate(12 830 220)"/><rect x="965" y="150" width="145" height="210" rx="24" fill="#1f2937" stroke="#79a7ff" stroke-width="3" transform="rotate(22 1035 255)"/><rect x="680" y="375" width="145" height="205" rx="24" fill="#14213b" stroke="#b76cff" stroke-width="3" transform="rotate(-18 750 478)"/></g><g transform="translate(465 215)"><ellipse cx="145" cy="330" rx="190" ry="45" fill="#6d4aff" opacity=".22"/><rect x="20" y="90" width="250" height="210" rx="45" fill="url(#gift)"/><path d="M145 90v210M45 142h200" stroke="#fff" stroke-width="15" stroke-linecap="round" opacity=".88"/><path d="M92 91c-28-65 27-82 53-17 27-65 82-48 53 17" fill="none" stroke="#fff" stroke-width="15" stroke-linecap="round"/><text x="145" y="255" text-anchor="middle" font-family="Arial,sans-serif" font-size="110" font-weight="900" fill="#fff">G</text></g><g transform="translate(420 425)"><path d="M10 30c25-35 75-35 100 0l20 42c8 17-8 36-27 31l-35-9-35 9c-19 5-35-14-27-31z" fill="#121827" stroke="#90b9ff" stroke-width="5"/><circle cx="88" cy="55" r="8" fill="#22d3ee"/><circle cx="108" cy="75" r="8" fill="#b76cff"/><path d="M43 50h26M56 37v26" stroke="#c4b5fd" stroke-width="7" stroke-linecap="round"/></g><g fill="#fff"><circle cx="315" cy="155" r="6"/><circle cx="380" cy="120" r="4"/><circle cx="1020" cy="470" r="5"/><circle cx="1115" cy="395" r="4"/></g></svg>"""

AUTH_SVG = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 620"><defs><linearGradient id="p" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#bd79ff"/><stop offset=".55" stop-color="#6d4aff"/><stop offset="1" stop-color="#22d3ee"/></linearGradient></defs><rect width="900" height="620" rx="48" fill="#07101f"/><circle cx="250" cy="220" r="150" fill="#6d4aff" opacity=".12"/><circle cx="690" cy="370" r="150" fill="#22d3ee" opacity=".08"/><rect x="140" y="165" width="280" height="210" rx="28" fill="#111b31" stroke="#765cff" stroke-width="3"/><rect x="185" y="210" width="175" height="15" rx="8" fill="#6d7aa0"/><rect x="185" y="248" width="130" height="15" rx="8" fill="#4b5875"/><rect x="185" y="292" width="150" height="42" rx="21" fill="url(#p)"/><circle cx="280" cy="114" r="42" fill="url(#p)"/><path d="M216 464c18-80 70-120 122-120s104 40 122 120" fill="url(#p)"/><rect x="535" y="140" width="210" height="270" rx="30" fill="#111b31" stroke="#2cdff7" stroke-width="3"/><rect x="575" y="195" width="130" height="95" rx="18" fill="url(#p)" opacity=".85"/><path d="m610 245 22 22 43-52" fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/><rect x="575" y="320" width="110" height="16" rx="8" fill="#6d7aa0"/><rect x="575" y="352" width="80" height="13" rx="7" fill="#4b5875"/></svg>"""

UI_SVG = r"""<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="p" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#c58aff"/><stop offset=".55" stop-color="#6d4aff"/><stop offset="1" stop-color="#35d9ff"/></linearGradient><linearGradient id="c" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#74f4ff"/><stop offset="1" stop-color="#5d7dff"/></linearGradient><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ffd66d"/><stop offset="1" stop-color="#ff8a3d"/></linearGradient></defs>
<symbol id="home" viewBox="0 0 48 48"><path fill="url(#p)" d="M7 22 24 8l17 14v18a4 4 0 0 1-4 4H11a4 4 0 0 1-4-4z"/><path fill="#fff" d="M18 44V28h12v16z"/></symbol>
<symbol id="search" viewBox="0 0 48 48"><circle cx="21" cy="21" r="13" fill="none" stroke="url(#c)" stroke-width="7"/><path d="m31 31 11 11" stroke="#fff" stroke-width="7" stroke-linecap="round"/></symbol>
<symbol id="user" viewBox="0 0 48 48"><circle cx="24" cy="16" r="10" fill="url(#p)"/><path d="M8 44c2-11 10-17 16-17s14 6 16 17z" fill="url(#p)"/></symbol>
<symbol id="cart" viewBox="0 0 48 48"><path d="M6 8h6l4 22h22l5-15H17" fill="none" stroke="url(#c)" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="19" cy="39" r="4" fill="#fff"/><circle cx="35" cy="39" r="4" fill="#fff"/></symbol>
<symbol id="gift" viewBox="0 0 48 48"><path d="M7 19h34v23H7z" fill="url(#p)"/><path d="M24 19v23M7 25h34" stroke="#fff" stroke-width="4"/><path d="M16 19C5 7 14 2 24 19 34 2 43 7 32 19" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round"/></symbol>
<symbol id="bolt" viewBox="0 0 48 48"><path d="M28 4 10 27h13l-3 17 18-24H25z" fill="url(#g)"/></symbol>
<symbol id="lock" viewBox="0 0 48 48"><rect x="9" y="21" width="30" height="22" rx="5" fill="url(#p)"/><path d="M15 21v-6a9 9 0 0 1 18 0v6" fill="none" stroke="#fff" stroke-width="5"/><circle cx="24" cy="32" r="3" fill="#fff"/></symbol>
<symbol id="support" viewBox="0 0 48 48"><circle cx="24" cy="24" r="18" fill="url(#c)"/><circle cx="17" cy="24" r="5" fill="#fff"/><circle cx="31" cy="24" r="5" fill="#fff"/><path d="M17 24h14" stroke="#fff" stroke-width="3"/></symbol>
<symbol id="star" viewBox="0 0 48 48"><path d="m24 4 6 12 14 2-10 10 2 14-12-6-12 6 2-14L4 18l14-2z" fill="url(#g)"/></symbol>
<symbol id="sparkle" viewBox="0 0 48 48"><path d="m24 3 4 17 17 4-17 4-4 17-4-17-17-4 17-4z" fill="url(#p)"/></symbol>
<symbol id="heart" viewBox="0 0 48 48"><path d="M24 42S6 31 6 17C6 7 18 3 24 12 30 3 42 7 42 17c0 14-18 25-18 25z" fill="#ff5f8f"/></symbol>
<symbol id="bell" viewBox="0 0 48 48"><path d="M10 35h28l-4-6V20a10 10 0 0 0-20 0v9z" fill="url(#p)"/><circle cx="24" cy="40" r="4" fill="#fff"/></symbol>
<symbol id="share" viewBox="0 0 48 48"><circle cx="12" cy="24" r="6" fill="url(#c)"/><circle cx="35" cy="12" r="6" fill="url(#p)"/><circle cx="35" cy="36" r="6" fill="url(#p)"/><path d="m17 22 12-7M17 26l12 7" stroke="#fff" stroke-width="4"/></symbol>
<symbol id="success" viewBox="0 0 48 48"><circle cx="24" cy="24" r="20" fill="#35d399"/><path d="m14 24 7 7 14-15" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="error" viewBox="0 0 48 48"><circle cx="24" cy="24" r="20" fill="#fb7185"/><path d="m16 16 16 16m0-16L16 32" stroke="#fff" stroke-width="5" stroke-linecap="round"/></symbol>
<symbol id="empty-cart" viewBox="0 0 80 80"><path d="M8 12h10l7 40h37l8-28H24" fill="none" stroke="url(#c)" stroke-width="7" stroke-linecap="round"/><circle cx="31" cy="66" r="5" fill="#fff"/><circle cx="57" cy="66" r="5" fill="#fff"/><path d="m48 15 4 9 10 1-8 6 2 10-8-5-9 5 2-10-8-6 10-1z" fill="url(#p)"/></symbol>
<symbol id="empty-search" viewBox="0 0 80 80"><circle cx="31" cy="31" r="19" fill="none" stroke="url(#c)" stroke-width="7"/><path d="m45 45 16 16" stroke="#fff" stroke-width="7" stroke-linecap="round"/><path d="m25 25 12 12m0-12L25 37" stroke="#fb7185" stroke-width="4" stroke-linecap="round"/></symbol>
<symbol id="empty-orders" viewBox="0 0 80 80"><rect x="17" y="13" width="46" height="55" rx="9" fill="url(#p)"/><path d="M27 28h26M27 40h18M27 52h20" stroke="#fff" stroke-width="5" stroke-linecap="round"/><circle cx="55" cy="59" r="12" fill="#1a2235" stroke="#22d3ee" stroke-width="3"/></symbol>
<symbol id="empty-wishlist" viewBox="0 0 80 80"><rect x="15" y="24" width="50" height="40" rx="10" fill="url(#p)"/><path d="M40 64V23M15 37h50" stroke="#fff" stroke-width="4"/><path d="M40 36c-10-17-22-6-8 5 4 3 8 6 8 6s4-3 8-6c14-11 2-22-8-5z" fill="#ff5f8f"/></symbol>
<symbol id="code" viewBox="0 0 48 48"><rect x="8" y="6" width="32" height="36" rx="6" fill="url(#p)"/><path d="M15 17h18M15 25h12M15 33h15" stroke="#fff" stroke-width="3" stroke-linecap="round"/></symbol>
<symbol id="game" viewBox="0 0 48 48"><path d="M8 29c1-13 7-18 16-18s15 5 16 18c1 10-7 12-11 5H19c-4 7-12 5-11-5z" fill="url(#p)"/><path d="M13 25h10M18 20v10" stroke="#fff" stroke-width="4" stroke-linecap="round"/><circle cx="33" cy="23" r="2.5" fill="#fff"/><circle cx="38" cy="27" r="2.5" fill="#fff"/></symbol>
<symbol id="laptop" viewBox="0 0 48 48"><rect x="10" y="8" width="28" height="22" rx="4" fill="url(#c)"/><path d="M6 34h36l-4 6H10z" fill="url(#p)"/></symbol>
<symbol id="phone" viewBox="0 0 48 48"><rect x="14" y="5" width="20" height="38" rx="6" fill="url(#p)"/><rect x="18" y="10" width="12" height="25" rx="3" fill="#0b1220"/><circle cx="24" cy="39" r="2" fill="#fff"/></symbol>
<symbol id="play" viewBox="0 0 48 48"><rect x="6" y="6" width="36" height="36" rx="10" fill="url(#c)"/><path d="m20 15 14 9-14 9z" fill="#fff"/></symbol>
<symbol id="grid" viewBox="0 0 48 48"><rect x="6" y="6" width="16" height="16" rx="4" fill="url(#p)"/><rect x="26" y="6" width="16" height="16" rx="4" fill="url(#c)"/><rect x="6" y="26" width="16" height="16" rx="4" fill="url(#c)"/><rect x="26" y="26" width="16" height="16" rx="4" fill="url(#p)"/></symbol>
</svg>"""

STYLE_APPEND = r"""
/* Giftbaaz Visual Identity Pack */
.ui-icon{width:20px;height:20px;display:inline-block;vertical-align:middle;flex:0 0 auto}
.ui-icon--sm{width:16px;height:16px}.ui-icon--md{width:24px;height:24px}.ui-icon--lg{width:58px;height:58px}.ui-icon--xl{width:82px;height:82px}
.brand-mark-image{width:40px;height:40px;display:block}.footer-brand .brand-mark-image{width:38px;height:38px}
.hero-art{width:100%;height:100%;object-fit:contain;display:block;filter:drop-shadow(0 25px 55px rgba(108,74,255,.25))}
.auth-art{width:min(100%,400px);display:block;margin:0 auto 22px;opacity:.96;filter:drop-shadow(0 25px 55px rgba(108,74,255,.18));max-height:280px;object-fit:contain}
.category-icon{padding:8px}.category-icon .ui-icon{width:30px;height:30px}
.trust-grid b,.floating-stat b{display:grid;place-items:center}.step i{padding:7px}
.empty-state>div .ui-icon{width:74px;height:74px}
.payment-result .result-art{width:86px;height:86px;margin:0 auto 16px;display:grid;place-items:center}
.mini-trust span,.hero-proof span{display:inline-flex;align-items:center;gap:6px}
.bestseller-badge{display:inline-flex;align-items:center;gap:4px}
.mobile-bottom-nav a{gap:3px}
@media(max-width:600px){.hero-art{height:100%}.auth-art{max-width:290px;max-height:210px}}
"""

ACCOUNT_HTML = r"""{% load static %}
{% extends "base.html" %}
{% block title %}حساب من | Giftbaaz{% endblock %}
{% block content %}
<section class="page-hero"><div class="container">
  <div class="page-visual"><svg class="ui-icon ui-icon--lg"><use href="{% static 'assets/giftbaaz-ui.svg' %}#user"></use></svg></div>
  <span class="eyebrow">حساب کاربری</span>
  <h1>سلام {{ user.username }}</h1>
  <p>سفارش‌ها و فعالیت‌های خریدت را از اینجا مدیریت کن.</p>
</div></section>
<section class="section"><div class="container">
  <div class="account-top"><a class="btn btn-primary" href="{% url 'shop' %}">ادامه خرید ←</a><a class="btn btn-secondary" href="{% url 'orders' %}">همه سفارش‌ها</a></div>
  <div class="advanced-account-grid">
    <a class="glass advanced-link" href="{% url 'wishlist' %}"><svg class="ui-icon"><use href="{% static 'assets/giftbaaz-ui.svg' %}#heart"></use></svg><strong>علاقه‌مندی‌ها</strong><span>محصولات ذخیره‌شده</span></a>
    <a class="glass advanced-link" href="{% url 'loyalty' %}"><svg class="ui-icon"><use href="{% static 'assets/giftbaaz-ui.svg' %}#star"></use></svg><strong>وفاداری</strong><span>امتیاز خرید</span></a>
    <a class="glass advanced-link" href="{% url 'notifications' %}"><svg class="ui-icon"><use href="{% static 'assets/giftbaaz-ui.svg' %}#bell"></use></svg><strong>اعلان‌ها</strong><span>رویدادهای حساب</span></a>
    <a class="glass advanced-link" href="{% url 'referral' %}"><svg class="ui-icon"><use href="{% static 'assets/giftbaaz-ui.svg' %}#share"></use></svg><strong>معرفی دوستان</strong><span>کد اختصاصی</span></a>
  </div>
  <div class="section-head"><div><span class="eyebrow">تاریخچه</span><h2>آخرین سفارش‌ها</h2></div></div>
  <div class="orders-list">{% for order in orders %}
    <a class="order-card glass" href="{% url 'order_detail' order.id %}"><div><span class="order-id">#{{ order.id }}</span><small>{{ order.created_at|date:"Y/m/d H:i" }}</small></div><span class="status-pill">{{ order.get_status_display }}</span><strong>{{ order.total_amount|floatformat:0 }} تومان</strong><span>←</span></a>
  {% empty %}
    <div class="empty-state"><div><svg class="ui-icon ui-icon--lg"><use href="{% static 'assets/giftbaaz-ui.svg' %}#empty-orders"></use></svg></div><h2>هنوز سفارشی نداری</h2><p>اولین خریدت را از فروشگاه شروع کن.</p><a class="btn btn-primary" href="{% url 'shop' %}">مشاهده فروشگاه</a></div>
  {% endfor %}</div>
</div></section>
{% endblock %}
"""

def backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        shutil.copy2(path, path.with_name(f"{path.name}.visualbak_{stamp}"))

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return
    if path.exists():
        backup(path)
    path.write_text(content, encoding="utf-8")

def replace(path: Path, old: str, new: str, required: bool = True) -> None:
    content = path.read_text(encoding="utf-8")
    if old not in content:
        if required and new not in content:
            raise RuntimeError(f"Expected UI pattern not found: {path}")
        return
    write(path, content.replace(old, new, 1))

def run_manage(*args: str) -> int:
    return subprocess.run([sys.executable, "manage.py", *args], cwd=ROOT).returncode

def main() -> None:
    if not (ROOT / "manage.py").exists():
        raise SystemExit("Run this file from the OnlineShop project root.")

    print("=" * 70)
    print("GIFTBAAZ VISUAL IDENTITY INSTALLER")
    print("=" * 70)

    # 1) Assets
    assets = {
        ROOT / "static/assets/giftbaaz-ui.svg": UI_SVG,
        ROOT / "static/assets/branding/giftbaaz-logo.svg": LOGO_SVG,
        ROOT / "static/assets/branding/giftbaaz-mark.svg": MARK_SVG,
        ROOT / "static/assets/hero/giftbaaz-hero.svg": HERO_SVG,
        ROOT / "static/assets/hero/giftbaaz-auth.svg": AUTH_SVG,
    }
    for path, content in assets.items():
        write(path, content)

    # 2) Global base template: real brand mark, favicon and unified icons.
    base = ROOT / "templates/base.html"
    static_ui = "{% static 'assets/giftbaaz-ui.svg' %}"
    static_mark = "{% static 'assets/branding/giftbaaz-mark.svg' %}"
    static_hero = "{% static 'assets/hero/giftbaaz-hero.svg' %}"
    static_auth = "{% static 'assets/hero/giftbaaz-auth.svg' %}"

    replacements = [
        ('<meta property="og:type" content="website">',
         '<meta property="og:type" content="website">\n  <link rel="icon" href="' + static_mark + '" type="image/svg+xml">\n  <link rel="apple-touch-icon" href="' + static_mark + '">'),
        ('<span>⚡ تحویل دیجیتال سریع</span>',
         '<span><svg class="ui-icon ui-icon--sm"><use href="' + static_ui + '#bolt"></use></svg>تحویل دیجیتال سریع</span>'),
        ('<span class="brand-mark">G</span>',
         '<img class="brand-mark-image" src="' + static_mark + '" alt="Giftbaaz">'),
        ('<span class="search-icon" aria-hidden="true">⌕</span>',
         '<span class="search-icon" aria-hidden="true"><svg class="ui-icon"><use href="' + static_ui + '#search"></use></svg></span>'),
        ("<a class=\"icon-action\" href=\"{% url 'account' %}\"><span>◉</span><b>حساب</b></a>",
         '<a class="icon-action" href="{% url \'account\' %}"><span><svg class="ui-icon"><use href="' + static_ui + '#user"></use></svg></span><b>حساب</b></a>'),
        ("<a class=\"icon-action\" href=\"{% url 'login' %}\"><span>◉</span><b>ورود</b></a>",
         '<a class="icon-action" href="{% url \'login\' %}"><span><svg class="ui-icon"><use href="' + static_ui + '#user"></use></svg></span><b>ورود</b></a>'),
        ('<span>🛒</span><b>سبد</b>',
         '<span><svg class="ui-icon"><use href="' + static_ui + '#cart"></use></svg></span><b>سبد</b>'),
    ]
    for old, new in replacements:
        replace(base, old, new, required=False)

    mobile_old = (
        '<a href="{% url \'home\' %}">⌂<span>خانه</span></a>'
        '<a href="{% url \'shop\' %}">⌕<span>فروشگاه</span></a>'
        '<a href="{% url \'cart\' %}">🛒<span>سبد</span></a>'
    )
    mobile_new = (
        '<a href="{% url \'home\' %}"><svg class="ui-icon"><use href="' + static_ui + '#home"></use></svg><span>خانه</span></a>'
        '<a href="{% url \'shop\' %}"><svg class="ui-icon"><use href="' + static_ui + '#search"></use></svg><span>فروشگاه</span></a>'
        '<a href="{% url \'cart\' %}"><svg class="ui-icon"><use href="' + static_ui + '#cart"></use></svg><span>سبد</span></a>'
    )
    replace(base, mobile_old, mobile_new, required=False)

    # 3) Home hero, category icons and trust icons.
    home = ROOT / "templates/home.html"
    old_hero = """<div class="hero-visual reveal" data-parallax>
      <div class="orb orb-one"></div><div class="orb orb-two"></div>
      <div class="hero-product-card"><div class="floating-icon">✦</div><span>Digital Store</span><strong>همین حالا شروع کن</strong><a href="{% url 'shop' %}">انتخاب محصول ←</a></div>
      <div class="floating-stat stat-a"><b>⚡</b><span>فرآیند سریع</span></div>
      <div class="floating-stat stat-b"><b>🔒</b><span>خرید امن</span></div>
    </div>"""
    new_hero = '<div class="hero-visual reveal" data-parallax><img class="hero-art" src="' + static_hero + '" alt="Giftbaaz digital gifts"></div>'
    replace(home, old_hero, new_hero)

    category_icons = """<span class="category-icon">
{% if "game" in category.slug or "gaming" in category.slug %}
<svg class="ui-icon ui-icon--md"><use href="{% static 'assets/giftbaaz-ui.svg' %}#game"></use></svg>
{% elif "gift" in category.slug or "card" in category.slug %}
<svg class="ui-icon ui-icon--md"><use href="{% static 'assets/giftbaaz-ui.svg' %}#gift"></use></svg>
{% elif "soft" in category.slug %}
<svg class="ui-icon ui-icon--md"><use href="{% static 'assets/giftbaaz-ui.svg' %}#laptop"></use></svg>
{% elif "mobile" in category.slug or "top" in category.slug %}
<svg class="ui-icon ui-icon--md"><use href="{% static 'assets/giftbaaz-ui.svg' %}#phone"></use></svg>
{% elif "entertain" in category.slug or "stream" in category.slug %}
<svg class="ui-icon ui-icon--md"><use href="{% static 'assets/giftbaaz-ui.svg' %}#play"></use></svg>
{% else %}
<svg class="ui-icon ui-icon--md"><use href="{% static 'assets/giftbaaz-ui.svg' %}#grid"></use></svg>
{% endif %}
</span>"""
    replace(home, '<span class="category-icon">✦</span>', category_icons, required=False)
    replace(home, '<div>★</div><h2>هنوز پرفروشی مشخص نشده</h2>', '<div><svg class="ui-icon ui-icon--lg"><use href="' + static_ui + '#star"></use></svg></div><h2>هنوز پرفروشی مشخص نشده</h2>', required=False)
    for old, key in [
        ('<div class="trust-grid"><div><b>⚡</b>', "bolt"),
        ('</div><div><b>🔒</b>', "lock"),
        ('</div><div><b>◈</b>', "code"),
        ('</div><div><b>↗</b>', "share"),
    ]:
        replace(home, old, ('<div class="trust-grid"><div><b><svg class="ui-icon ui-icon--md"><use href="' + static_ui + '#' + key + '"></use></svg></b>' if key == "bolt"
                              else '</div><div><b><svg class="ui-icon ui-icon--md"><use href="' + static_ui + '#' + key + '"></use></svg></b>'), required=False)

    # 4) Shop / cart / order empty states.
    shop = ROOT / "templates/shop.html"
    replace(shop, '<div class="empty-state"><div>⌕</div>',
            '<div class="empty-state"><div><svg class="ui-icon ui-icon--lg"><use href="' + static_ui + '#empty-search"></use></svg></div>', required=False)

    cart = ROOT / "templates/cart.html"
    replace(cart, '<span>✦</span>', '<svg class="ui-icon ui-icon--lg"><use href="' + static_ui + '#gift"></use></svg>', required=False)
    replace(cart, '<div class="empty-state"><div>🛒</div>',
            '<div class="empty-state"><div><svg class="ui-icon ui-icon--lg"><use href="' + static_ui + '#empty-cart"></use></svg></div>', required=False)

    orders = ROOT / "templates/orders.html"
    replace(orders, '<div class="empty-state"><div>◫</div>',
            '<div class="empty-state"><div><svg class="ui-icon ui-icon--lg"><use href="' + static_ui + '#empty-orders"></use></svg></div>', required=False)

    # 5) Product card/detail icons.
    card = ROOT / "templates/partials/product_card.html"
    replace(card, '<div class="product-placeholder">✦</div>',
            '<div class="product-placeholder"><svg class="ui-icon ui-icon--xl"><use href="' + static_ui + '#gift"></use></svg></div>', required=False)
    replace(card, '<span class="bestseller-badge">★ پرفروش</span>',
            '<span class="bestseller-badge"><svg class="ui-icon ui-icon--sm"><use href="' + static_ui + '#star"></use></svg>پرفروش</span>', required=False)

    product = ROOT / "templates/product_detail.html"
    replace(product, '<div class="product-placeholder">✦</div>',
            '<div class="product-placeholder"><svg class="ui-icon ui-icon--xl"><use href="' + static_ui + '#gift"></use></svg></div>', required=False)
    replace(product, '<span>🔒 خرید امن</span><span>⚡ تحویل دیجیتال</span><span>↗ قابل پیگیری</span>',
            '<span><svg class="ui-icon ui-icon--sm"><use href="' + static_ui + '#lock"></use></svg>خرید امن</span><span><svg class="ui-icon ui-icon--sm"><use href="' + static_ui + '#bolt"></use></svg>تحویل دیجیتال</span><span><svg class="ui-icon ui-icon--sm"><use href="' + static_ui + '#share"></use></svg>قابل پیگیری</span>', required=False)

    # 6) Payment result.
    payment_result = ROOT / "templates/payment_result.html"
    p = payment_result.read_text(encoding="utf-8")
    p_old = '<div class="result-icon">{% if success %}✓{% else %}×{% endif %}</div>'
    p_new = '<div class="result-art">{% if success %}<svg class="ui-icon ui-icon--xl"><use href="' + static_ui + '#success"></use></svg>{% else %}<svg class="ui-icon ui-icon--xl"><use href="' + static_ui + '#error"></use></svg>{% endif %}</div>'
    if p_old in p:
        write(payment_result, p.replace(p_old, p_new, 1))

    # 7) Login / signup illustration.
    for name in ("login.html", "signup.html"):
        path = ROOT / "templates" / name
        c = path.read_text(encoding="utf-8")
        if "assets/hero/giftbaaz-auth.svg" not in c:
            if "{% load static %}" not in c:
                c = "{% load static %}\n" + c
            c = c.replace(
                '<div class="auth-visual">',
                '<div class="auth-visual"><img class="auth-art" src="' + static_auth + '" alt="Giftbaaz account illustration">',
                1,
            )
            write(path, c)

    # 8) Repair the duplicated account template while preserving existing account URLs.
    write(ROOT / "templates/account.html", ACCOUNT_HTML)

    # 9) CSS.
    css = ROOT / "static/css/style.css"
    current = css.read_text(encoding="utf-8")
    if "/* Giftbaaz Visual Identity Pack */" not in current:
        write(css, current.rstrip() + "\n" + STYLE_APPEND + "\n")

    # 10) Verification.
    print("\n[1/3] Django check")
    if run_manage("check"):
        raise SystemExit("[FAILED] manage.py check")
    print("\n[2/3] Django tests")
    if run_manage("test"):
        raise SystemExit("[FAILED] manage.py test")
    print("\n[3/3] Collect static")
    if run_manage("collectstatic", "--noinput"):
        raise SystemExit("[FAILED] manage.py collectstatic --noinput")

    print("\n" + "=" * 70)
    print("GIFTBAAZ VISUAL INSTALLATION COMPLETE")
    print("=" * 70)
    print("Created original SVG branding, hero artwork and a unified glossy icon set.")
    print("Updated core templates, empty states, payment result and auth visuals.")
    print("Run the installer from the OnlineShop project root.")
    print("The glossy icon language is iPhone-like in feel, not Apple emoji assets.")


if __name__ == "__main__":
    main()