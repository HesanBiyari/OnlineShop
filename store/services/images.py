"""Image upload validation and product gallery persistence."""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from PIL import Image, UnidentifiedImageError

from store.models import Product, ProductImage

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


def validate_image_upload(uploaded) -> str | None:
    """Return a user-facing error, or ``None`` when the file is acceptable."""

    if uploaded is None:
        return "تصویری انتخاب نشده است."

    max_bytes = int(getattr(settings, "PRODUCT_IMAGE_MAX_BYTES", 5 * 1024 * 1024))
    if getattr(uploaded, "size", 0) > max_bytes:
        return "حجم تصویر بیش از حد مجاز است."

    content_type = str(getattr(uploaded, "content_type", "") or "")
    if content_type and not content_type.startswith("image/"):
        return "فایل انتخاب‌شده تصویر نیست."

    max_dimension = int(
        getattr(settings, "PRODUCT_IMAGE_MAX_DIMENSION", 4000)
    )
    try:
        uploaded.seek(0)
        with Image.open(uploaded) as image:
            image.verify()
        uploaded.seek(0)
        with Image.open(uploaded) as image:
            width, height = image.size
            image_format = image.format
    except (UnidentifiedImageError, OSError, ValueError):
        return "تصویر معتبر نیست."
    finally:
        try:
            uploaded.seek(0)
        except (AttributeError, OSError):
            pass

    if image_format not in ALLOWED_FORMATS:
        return "فرمت تصویر پشتیبانی نمی‌شود."
    if width <= 0 or height <= 0 or width > max_dimension or height > max_dimension:
        return "ابعاد تصویر بیش از حد مجاز است."
    return None


def save_product_images(
    product: Product,
    uploads: list,
    *,
    alt_text: str = "",
    make_main: bool = False,
) -> list[str]:
    """Validate every upload before saving any of them."""

    if not uploads:
        return []

    errors = []
    for uploaded in uploads:
        error = validate_image_upload(uploaded)
        if error:
            errors.append(f"{getattr(uploaded, 'name', 'تصویر')}: {error}")
    if errors:
        return errors

    alt_text = (alt_text or "").strip()[:200]
    with transaction.atomic():
        if make_main:
            ProductImage.objects.filter(product=product, is_main=True).update(
                is_main=False
            )
        for index, uploaded in enumerate(uploads):
            ProductImage.objects.create(
                product=product,
                image=uploaded,
                alt_text=(
                    alt_text
                    or getattr(uploaded, "name", "").rsplit(".", 1)[0][:200]
                ),
                is_main=(index == 0 and make_main),
            )
    return []
