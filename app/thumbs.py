from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage

logger = logging.getLogger(__name__)

THUMBS_ROOT = Path("static/thumbs")
IMAGES_ROOT = Path("static/images")

MAX_THUMB_SIZE = (512, 512)


def derive_relative_path(file_path: str, file_name: str) -> Path:
    # Prefer file_path if it looks like it already includes the file name
    p = Path(file_path)
    if p.suffix:  # likely includes filename
        return p
    # fallback use file_path as directory + file_name
    return p / file_name


def original_file_path(file_path: str, file_name: str) -> Path:
    rel = derive_relative_path(file_path, file_name)
    return IMAGES_ROOT / rel


def thumb_file_path(file_path: Path) -> Path:
    return THUMBS_ROOT / file_path.with_suffix(".jpg")


def ensure_thumbnail(src: Path, dst: Path) -> Optional[Path]:
    if not src.is_file():
        logger.warning("Original image missing: %s", src)
        return None
    if dst.is_file():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with PILImage.open(src) as im:
            im.thumbnail(MAX_THUMB_SIZE)
            # Convert to RGB to ensure JPEG compatibility (avoid keeping alpha)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.save(dst, format="JPEG", quality=80)
            logger.info("Created thumbnail %s", dst)
    except Exception as e:  # pragma: no cover - best effort
        logger.exception("Failed generating thumbnail for %s: %s", src, e)
        return None
    return dst
