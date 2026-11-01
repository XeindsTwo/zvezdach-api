import io
import re
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError


IMAGE_QUALITY = 85
MAX_UPLOAD_SIZE = 2 * 1024 * 1024
MAX_GIF_UPLOAD_SIZE = 5 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1920
ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP", "AVIF", "GIF"}
ALLOWED_IMAGE_FORMATS_LABEL = "PNG, JPG, JPEG, WebP, AVIF или GIF"


def safe_image_stem(filename: str) -> str:
    stem = Path(filename).stem.lower()
    stem = re.sub(r"[^a-z0-9_-]+", "-", stem).strip("-")
    return stem[:80] or "image"


def validate_image_upload(uploaded) -> None:
    try:
        uploaded.seek(0)
        filename = str(getattr(uploaded, "name", "")).lower()
        declared_gif = filename.endswith(".gif")
        declared_limit = MAX_GIF_UPLOAD_SIZE if declared_gif else MAX_UPLOAD_SIZE
        if getattr(uploaded, "size", 0) > declared_limit:
            raise ValidationError("GIF должен весить не больше 5 МБ" if declared_gif else "Изображение должно весить не больше 2 МБ")
        with Image.open(uploaded) as source:
            image_format = str(source.format or "").upper()
            source.verify()
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError(f"Разрешены только форматы: {ALLOWED_IMAGE_FORMATS_LABEL}")
        size_limit = MAX_GIF_UPLOAD_SIZE if image_format == "GIF" else MAX_UPLOAD_SIZE
        if getattr(uploaded, "size", 0) > size_limit:
            raise ValidationError(f"GIF должен весить не больше 5 МБ" if image_format == "GIF" else "Изображение должно весить не больше 2 МБ")
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValidationError("Файл не является корректным изображением") from error
    finally:
        try:
            uploaded.seek(0)
        except (AttributeError, OSError):
            pass


def optimize_image(uploaded) -> tuple[ContentFile, ContentFile | None]:
    validate_image_upload(uploaded)

    try:
        uploaded.seek(0)
        with Image.open(uploaded) as source:
            image_format = str(source.format or "").upper()
            if image_format == "GIF":
                uploaded.seek(0)
                return ContentFile(uploaded.read(), name=f"{safe_image_stem(getattr(uploaded, 'name', 'image'))}.gif"), None
            image = ImageOps.exif_transpose(source)
            image.seek(0)
            image.load()
            if max(image.size) > MAX_IMAGE_DIMENSION:
                scale = MAX_IMAGE_DIMENSION / max(image.size)
                image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")

            webp_buffer = io.BytesIO()
            image.save(webp_buffer, format="WEBP", quality=IMAGE_QUALITY, method=6, exact=True)

            avif_buffer = io.BytesIO()
            image.save(avif_buffer, format="AVIF", quality=IMAGE_QUALITY, speed=6)
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValidationError("Файл не является корректным изображением") from error
    finally:
        try:
            uploaded.seek(0)
        except (AttributeError, OSError):
            pass

    stem = safe_image_stem(getattr(uploaded, "name", "image"))
    return (
        ContentFile(webp_buffer.getvalue(), name=f"{stem}.webp"),
        ContentFile(avif_buffer.getvalue(), name=f"{stem}.avif"),
    )
