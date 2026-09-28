from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
STYLE = ROOT / "static" / "css" / "style.css"
BASE = TEMPLATES / "base.html"
ADMIN_BASE = TEMPLATES / "admin" / "base_site.html"
BACKUP_DIR = ROOT / ".giftbaaz_scale_repair_backups"
LOG_DIR = ROOT / ".giftbaaz_scale_repair_logs"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"scale_repair_{STAMP}.log"

SCALE_MARKER = "/* Giftbaaz Final Scale Calibration v1 */"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def ensure_project() -> None:
    if not (ROOT / "manage.py").exists():
        fail(f"Run this script from the project root. manage.py not found at {ROOT}")
    if not (ROOT / "config" / "settings.py").exists():
        fail("config/settings.py was not found")
    if not BASE.exists() or not STYLE.exists():
        fail("Required templates/static files are missing")


def backup(path: Path) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / path.name
    if dest.exists():
        dest = BACKUP_DIR / f"{path.stem}_{STAMP}{path.suffix}"
    shutil.copy2(path, dest)


def write_log(line: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def run(cmd: list[str], label: str) -> None:
    text = "$ " + " ".join(cmd)
    print(f"  {label} ...", end=" ", flush=True)
    write_log("\n" + text)
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    combined = (proc.stdout or "") + (proc.stderr or "")
    write_log(combined)
    if proc.returncode != 0:
        print("FAIL")
        tail = combined.splitlines()[-40:]
        if tail:
            print("\n".join("    " + line for line in tail))
        fail(f"{label} failed with exit code {proc.returncode}. Full log: {LOG_FILE}")
    print("PASS")


def dedupe_base_links() -> None:
    text = BASE.read_text(encoding="utf-8")
    original = text

    favicon_pat = re.compile(
        r"\n\s*<link rel=\"icon\" href=\"\{% static 'assets/branding/giftbaaz-mark\.svg' %\}\" type=\"image/svg\+xml\">"
    )
    apple_pat = re.compile(
        r"\n\s*<link rel=\"apple-touch-icon\" href=\"\{% static 'assets/branding/giftbaaz-mark\.svg' %\}\">"
    )

    text, n1 = favicon_pat.subn("", text)
    text, n2 = apple_pat.subn("", text)

    head_anchor = '  <link rel="stylesheet" href="{% static \'css/style.css\' %}">'
    if head_anchor in text:
        inject = (
            "  <link rel=\"icon\" href=\"{% static 'assets/branding/giftbaaz-mark.svg' %}\" type=\"image/svg+xml\">\n"
            "  <link rel=\"apple-touch-icon\" href=\"{% static 'assets/branding/giftbaaz-mark.svg' %}\">\n"
        )
        text = text.replace(head_anchor, inject + head_anchor, 1)

    # Make the mobile account/entry icon consistent with the rest of the icon system.
    old_mobile = (
        '{% if user.is_authenticated %}<a href="{% url \'account\' %}">◉<span>حساب</span></a>'
        '{% else %}<a href="{% url \'login\' %}">◉<span>ورود</span></a>{% endif %}'
    )
    new_mobile = (
        '{% if user.is_authenticated %}<a href="{% url \'account\' %}"><svg class="ui-icon"><use href="{% static \'assets/giftbaaz-ui.svg\' %}#user"></use></svg><span>حساب</span></a>'
        '{% else %}<a href="{% url \'login\' %}"><svg class="ui-icon"><use href="{% static \'assets/giftbaaz-ui.svg\' %}#user"></use></svg><span>ورود</span></a>{% endif %}'
    )
    text = text.replace(old_mobile, new_mobile, 1)

    if text != original:
        BASE.write_text(text, encoding="utf-8")
        print(f"  base.html cleanup: {n1} duplicate favicon(s), {n2} duplicate apple-icon(s) removed")


def dedupe_admin_load() -> None:
    if not ADMIN_BASE.exists():
        return
    text = ADMIN_BASE.read_text(encoding="utf-8")
    text2 = text.replace("{% load static %}\n{% load static %}", "{% load static %}", 1)
    text2 = re.sub(r"\{% load static %\}\s*\{% load static %\}", "{% load static %}", text2, count=1)
    if text2 != text:
        ADMIN_BASE.write_text(text2, encoding="utf-8")
        print("  admin/base_site.html duplicate static load: cleaned")


def apply_scale_css() -> None:
    css = STYLE.read_text(encoding="utf-8")
    if SCALE_MARKER in css:
        print("  scale calibration already present: kept existing calibration")
        return

    patch = r'''

/* Giftbaaz Final Scale Calibration v1 */
/* Purpose: keep visual proportions tied to content width instead of fixed-height boxes. */

.container{width:min(1180px,calc(100% - 40px))}
.header-main{gap:20px;padding:14px 0}
.brand-mark-image{width:44px;height:44px;object-fit:contain;flex:0 0 44px}
.footer-brand .brand-mark-image{width:40px;height:40px;flex-basis:40px}
.brand-text{font-size:21px}

.hero{padding:72px 0 82px}
.hero-grid{grid-template-columns:minmax(0,1.05fr) minmax(320px,.95fr);gap:52px}
.hero h1{font-size:clamp(40px,5.2vw,68px);letter-spacing:-1.5px}
.hero-copy p{font-size:15px}
.hero-visual{height:auto;min-height:0;display:flex;align-items:center;justify-content:center}
.hero-art{width:min(100%,560px);height:auto;aspect-ratio:1200 / 700;object-fit:contain;display:block}

.section{padding:68px 0}
.section-head{margin-bottom:24px}
.section-head h2{font-size:28px}
.page-hero{padding:54px 0 28px}
.page-hero h1{font-size:42px}

.category-card{padding:18px}
.category-icon{width:40px;height:40px}
.category-card strong{font-size:13px}

.product-grid{gap:16px}
.product-media{height:auto;aspect-ratio:4 / 3;min-height:0}
.product-card-body{padding:15px}
.product-card h3{font-size:13px;min-height:40px}
.price-row strong{font-size:15px}
.card-cta{font-size:10px}

.product-detail-grid{gap:22px}
.gallery-card{padding:13px}
.product-main-media{height:auto;aspect-ratio:4 / 3;min-height:0}
.product-info-panel{padding:26px}
.product-info-panel h1{font-size:34px}
.detail-price strong{font-size:28px}
.product-thumbnails img{width:60px;height:60px}

.auth-page{min-height:0;padding:58px 0}
.auth-art{width:min(100%,350px);max-height:none;height:auto;aspect-ratio:900 / 620;object-fit:contain}
.auth-visual h1{font-size:44px}
.auth-card{padding:26px}

.page-visual{width:58px;height:58px;margin:0 0 14px;display:grid;place-items:center;border:1px solid var(--line);border-radius:16px;background:rgba(139,92,246,.08)}
.page-visual .ui-icon{width:38px;height:38px}

.advanced-account-grid{gap:10px}
.advanced-link{padding:16px}
.order-card{padding:15px}
.summary-card{padding:20px}
.checkout-card{padding:22px}

.ui-icon--lg{width:54px;height:54px}
.ui-icon--xl{width:72px;height:72px}
.empty-state{padding:58px 18px}

@media(max-width:1000px){
  .header-main{grid-template-columns:auto minmax(240px,1fr) auto}
  .hero-grid{gap:34px}
  .hero-art{max-width:520px}
  .product-media{aspect-ratio:4 / 3}
}

@media(max-width:800px){
  .hero{padding:54px 0 62px}
  .hero-grid{grid-template-columns:1fr;gap:28px}
  .hero-copy{text-align:center}
  .hero-copy p{margin-inline:auto}
  .hero-actions{justify-content:center}
  .hero-proof{justify-content:center}
  .hero-visual{order:-1}
  .hero-art{width:min(100%,520px);max-width:520px}
  .product-detail-grid{gap:16px}
  .product-main-media{aspect-ratio:4 / 3}
  .auth-page{gap:32px}
}

@media(max-width:600px){
  .container{width:min(100% - 24px,1180px)}
  .header-main{padding:11px 0;gap:12px}
  .brand-mark-image{width:36px;height:36px;flex-basis:36px}
  .footer-brand .brand-mark-image{width:34px;height:34px;flex-basis:34px}
  .brand-text{font-size:18px}
  .hero{padding:46px 0 54px}
  .hero h1{font-size:clamp(35px,10vw,46px);letter-spacing:-.8px}
  .hero-copy p{font-size:13px}
  .hero-art{width:100%;max-width:420px}
  .section{padding:48px 0}
  .section-head h2{font-size:23px}
  .page-hero{padding:40px 0 22px}
  .page-hero h1{font-size:32px}
  .category-card{padding:15px}
  .category-icon{width:38px;height:38px}
  .category-icon .ui-icon{width:27px;height:27px}
  .product-grid{gap:10px}
  .product-media{aspect-ratio:1.15 / 1}
  .product-card-body{padding:11px}
  .product-card h3{font-size:12px;min-height:38px}
  .price-row strong{font-size:13px}
  .product-main-media{aspect-ratio:4 / 3}
  .product-info-panel{padding:21px}
  .product-info-panel h1{font-size:27px}
  .detail-price strong{font-size:25px}
  .product-thumbnails img{width:56px;height:56px}
  .auth-page{padding:42px 0}
  .auth-art{width:min(100%,290px)}
  .auth-visual h1{font-size:34px}
  .auth-card{padding:21px}
  .page-visual{width:52px;height:52px;border-radius:14px}
  .page-visual .ui-icon{width:34px;height:34px}
  .ui-icon--lg{width:48px;height:48px}
  .ui-icon--xl{width:64px;height:64px}
  .empty-state{padding:48px 14px}
}
'''
    STYLE.write_text(css.rstrip() + patch + "\n", encoding="utf-8")
    print("  final scale calibration CSS: added")


def audit_templates() -> None:
    errors: list[str] = []
    static_missing: list[str] = []
    html_files = sorted(TEMPLATES.rglob("*.html"))
    if not html_files:
        errors.append("No templates/**/*.html files found")
    for path in html_files:
        text = path.read_text(encoding="utf-8")
        tag_tokens = list(re.finditer(r"\{%\s*(.*?)\s*%\}", text, flags=re.S))
        template_tags = [m.group(1).strip() for m in tag_tokens]
        if any(t.startswith("extends ") for t in template_tags):
            first_nonempty = template_tags[0] if template_tags else ""
            if not first_nonempty.startswith("extends "):
                errors.append(f"{path.relative_to(ROOT)}: extends is not the first template tag")
        if re.search(r"\{%\s*static\b", text) and not re.search(r"\{%\s*load\s+static\s*%\}", text):
            errors.append(f"{path.relative_to(ROOT)}: static tag used without load static")
        for m in re.finditer(r"\{%\s*static\s+['\"]([^'\"]+)['\"]\s*%\}", text):
            rel = m.group(1)
            candidate = ROOT / "static" / rel
            if not candidate.exists():
                static_missing.append(f"{path.relative_to(ROOT)} -> static/{rel}")
    if static_missing:
        errors.append("Missing static source files: " + "; ".join(static_missing))
    if errors:
        for e in errors:
            print("  " + e)
        fail(f"template/static audit found {len(errors)} issue(s)")
    print(f"  template/static audit ({len(html_files)} templates) ... PASS")


def audit_css_calibration() -> None:
    css = STYLE.read_text(encoding="utf-8")
    checks = {
        "scale marker": SCALE_MARKER in css,
        "hero art aspect": "aspect-ratio:1200 / 700" in css,
        "product media aspect": "aspect-ratio:4 / 3" in css,
        "mobile product ratio": "aspect-ratio:1.15 / 1" in css,
        "auth illustration cap": "width:min(100%,350px)" in css,
        "desktop logo 44px": "width:44px;height:44px;object-fit:contain;flex:0 0 44px" in css,
        "mobile logo 36px": "width:36px;height:36px;flex-basis:36px" in css,
        "page visual size": "width:58px;height:58px" in css,
    }
    bad = [name for name, ok in checks.items() if not ok]
    if bad:
        fail("CSS calibration audit failed: " + ", ".join(bad))
    print("  CSS scale calibration audit ... PASS")


def compile_all_templates() -> None:
    code = r'''import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.template.loader import get_template
from pathlib import Path
root = Path("templates")
files = sorted(root.rglob("*.html"))
for p in files:
    name = p.relative_to(root).as_posix()
    get_template(name)
print(f"compiled {len(files)} templates")
'''
    run([sys.executable, "-c", code], "compile all templates")


def main() -> None:
    ensure_project()
    print("=" * 72)
    print("GIFTBAAZ FINAL SCALE + FRONTEND REPAIR")
    print("=" * 72)
    print(f"Project: {ROOT}")

    backup(BASE)
    backup(STYLE)
    if ADMIN_BASE.exists():
        backup(ADMIN_BASE)

    dedupe_base_links()
    dedupe_admin_load()
    apply_scale_css()

    audit_templates()
    audit_css_calibration()

    django = str(ROOT / "venv" / "Scripts" / "python.exe")
    if not Path(django).exists():
        django = sys.executable

    print("\nVERIFICATION PASS 1")
    compile_all_templates()
    run([django, "manage.py", "collectstatic", "--clear", "--noinput"], "collectstatic")
    run([django, "manage.py", "check"], "manage.py check")
    run([django, "manage.py", "makemigrations", "--check", "--dry-run"], "migrations check")
    run([django, "manage.py", "test", "--verbosity", "1"], "Django tests")

    print("\nVERIFICATION PASS 2")
    compile_all_templates()
    audit_templates()
    audit_css_calibration()
    run([django, "manage.py", "collectstatic", "--clear", "--noinput"], "collectstatic")
    run([django, "manage.py", "check"], "manage.py check")
    run([django, "manage.py", "makemigrations", "--check", "--dry-run"], "migrations check")
    run([django, "manage.py", "test", "--verbosity", "1"], "Django tests")

    print("\n" + "=" * 72)
    print("FINAL REPAIR COMPLETE - ALL TEMPLATE/STATIC/FRONTEND CHECKS PASSED TWICE")
    print("=" * 72)
    print(f"Full command log: {LOG_FILE}")
    print(f"Backups: {BACKUP_DIR}")
    print("Do not run the older visual installer scripts after this repair.")


if __name__ == "__main__":
    main()
