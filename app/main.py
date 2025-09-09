from __future__ import annotations

import logging
from os import environ
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .database import get_session, session_scope
from .models import Image, Tag
from .schemas import ImageOut
from .thumbs import ensure_thumbnail, original_file_path, thumb_file_path, IMAGES_ROOT

logger = logging.getLogger("wpserve")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

app = FastAPI(title="Wallpaper Server")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


BASE_PATH = Path(environ.get("WPSERVE_BASE_PATH", ""))


@app.on_event("startup")
def startup_scan():
    """On startup: ensure thumbnails exist and prune DB records for missing files."""
    removed = 0
    generated = 0
    # Use explicit context manager for startup tasks instead of dependency generator
    with session_scope() as session:  # type: ignore
        # .unique() required because Image.tags relationship uses joined eager loading
        images: List[Image] = session.execute(select(Image)).unique().scalars().all()
        for img in images:
            original = BASE_PATH / Path("." + img.file_path)
            if not original.is_file():
                logger.warning("DB entry without file -> deleting: %s", original)
                session.delete(img)
                removed += 1
                continue
            thumb_before = thumb_file_path(Path("." + img.file_path))
            if not thumb_before.is_file():
                if ensure_thumbnail(original, thumb_before):
                    generated += 1
    logger.info(
        "Startup scan complete. Removed=%d Generated thumbs=%d", removed, generated
    )


# ---------- HTML Routes ----------


@app.get("/")
def index(request: Request, session: Session = Depends(get_session)):
    # Exclude tags that have no images
    tags = (
        session.execute(select(Tag).where(Tag.images.any()).order_by(Tag.name))
        .scalars()
        .all()
    )
    total_images = session.execute(select(func.count(Image.id))).scalar_one()
    return templates.TemplateResponse(
        "index.html", {"request": request, "tags": tags, "total_images": total_images}
    )


@app.get("/tag/{tag_id}")
def tag_page(tag_id: int, request: Request, session: Session = Depends(get_session)):
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, "Tag not found")
    # images relationship may be lazy load; ensure ordering by id
    images = sorted(tag.images, key=lambda i: i.id)
    return templates.TemplateResponse(
        "tag.html", {"request": request, "tag": tag, "images": images}
    )


@app.get("/image/{image_id}")
def image_page(
    image_id: int, request: Request, session: Session = Depends(get_session)
):
    image = session.get(Image, image_id)
    if not image:
        raise HTTPException(404, "Image not found")
    image.file_path = str(Path("." + image.file_path))
    return templates.TemplateResponse(
        "image.html", {"request": request, "image": image}
    )


# ---------- API Routes ----------


@app.get("/api/images", response_model=list[ImageOut])
def api_images(session: Session = Depends(get_session)):
    images = session.execute(select(Image).order_by(Image.id)).unique().scalars().all()
    return images


@app.get("/api/thumb/{image_id}")
def api_thumb(image_id: int, session: Session = Depends(get_session)):
    image = session.get(Image, image_id)
    if not image:
        raise HTTPException(404, "Image not found")
    original = BASE_PATH / Path("." + image.file_path)
    thumb = thumb_file_path(Path("." + image.file_path))
    thumb = ensure_thumbnail(original, thumb)
    if not thumb or not thumb.is_file():
        raise HTTPException(500, "Failed to create thumbnail")
    return FileResponse(thumb, media_type="image/jpeg")


@app.get("/api/raw/{image_id}")
def api_raw(image_id: int, session: Session = Depends(get_session)):
    image = session.get(Image, image_id)
    if not image:
        raise HTTPException(404, "Image not found")
    original = original_file_path(image.file_path, image.file_name)
    if not original.is_file():
        raise HTTPException(404, "File missing on disk")
    # Guess media type from extension
    ext = original.suffix.lower()
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")
    return FileResponse(original, media_type=media_type)


@app.get("/healthz")
def health():  # simple health endpoint
    return {"ok": True}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
