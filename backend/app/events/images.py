"""Image storage helpers for the events domain."""

import uuid
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.events.schemas import EventImageUrls

VARIANT_WIDTHS = (400, 800, 1200)
EVENTS_MEDIA_SUBDIR = "events"
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}
UNSUPPORTED_IMAGE_DETAIL = (
    "Formato de imagen no soportado. Usa JPEG, PNG o WebP"
)


def events_media_dir() -> Path:
    return Path(settings.media_root) / EVENTS_MEDIA_SUBDIR


def delete_event_image_files(image_key: str) -> None:
    directory = events_media_dir()
    for width in VARIANT_WIDTHS:
        (directory / f"{image_key}_{width}w.webp").unlink(missing_ok=True)


async def read_and_validate_image(upload: UploadFile) -> bytes:
    raw = await upload.read(settings.max_event_image_bytes + 1)
    if len(raw) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo de imagen está vacío",
        )
    if len(raw) > settings.max_event_image_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="La imagen no debe superar los 5 MB",
        )
    return raw


def decode_and_clean_image(raw: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in SUPPORTED_FORMATS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=UNSUPPORTED_IMAGE_DETAIL,
                )
            image.load()
            transposed = ImageOps.exif_transpose(image)
            has_alpha = transposed.mode in ("RGBA", "LA") or (
                transposed.mode == "P"
                and "transparency" in transposed.info
            )
            mode = "RGBA" if has_alpha else "RGB"
            clean = Image.new(mode, transposed.size)
            clean.paste(transposed.convert(mode))
            return clean
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=UNSUPPORTED_IMAGE_DETAIL,
        ) from exc


def store_event_image_variants(clean: Image.Image) -> str:
    image_key = uuid.uuid4().hex
    directory = events_media_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for target_width in VARIANT_WIDTHS:
        if clean.width > target_width:
            target_height = max(
                1, round(clean.height * target_width / clean.width)
            )
            variant = clean.resize(
                (target_width, target_height),
                Image.Resampling.LANCZOS,
            )
        else:
            variant = clean.copy()
        variant.save(
            directory / f"{image_key}_{target_width}w.webp",
            format="WEBP",
            quality=80,
            method=4,
        )
    return image_key


def build_image_urls(image_key: str | None) -> EventImageUrls | None:
    if not image_key:
        return None
    return EventImageUrls(
        w400=f"/api/media/events/{image_key}_400w.webp",
        w800=f"/api/media/events/{image_key}_800w.webp",
        w1200=f"/api/media/events/{image_key}_1200w.webp",
    )
