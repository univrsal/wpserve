from __future__ import annotations

from pathlib import Path
from typing import Iterable

from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.database import Base, engine, get_db
from app.models.image import Image, Tag
from app.routers import images as images_router

import os
from PIL import Image as PILImage

app = FastAPI(title="Image Browser")

# Ensure DB tables
Base.metadata.create_all(bind=engine)

# Mount static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
TEMPLATES_DIR = Path("templates")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.include_router(images_router.router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    tags = db.query(Tag).order_by(Tag.name).all()
    total_images = db.query(Image).count()
    return templates.TemplateResponse(
        "index.html", {"request": request, "tags": tags, "total_images": total_images}
    )


@app.get("/tag/{tag_id}", response_class=HTMLResponse)
async def tag_page(tag_id: int, request: Request, db: Session = Depends(get_db)):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        return HTMLResponse("Tag not found", status_code=404)
    return templates.TemplateResponse(
        "tag.html", {"request": request, "tag": tag, "images": tag.images}
    )


@app.get("/image/{image_id}", response_class=HTMLResponse)
async def image_page(image_id: int, request: Request, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        return HTMLResponse("Image not found", status_code=404)
    return templates.TemplateResponse(
        "image.html", {"request": request, "image": image}
    )


# Utility: initial scan (optional) - invoked at startup if env var set
SCAN_DIR = Path(os.getenv("IMAGE_SCAN_DIR", "static/images"))


def scan_images(db: Session, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            continue
        existing = db.query(Image).filter(Image.filename == path.name).first()
        if existing:
            continue
        try:
            with PILImage.open(path) as im:
                width, height = im.size
        except Exception:
            continue
        file_size = path.stat().st_size
        img = Image(filename=path.name, width=width, height=height, file_size=file_size)
        db.add(img)
    db.commit()


@app.on_event("startup")
async def startup_event():
    if os.getenv("AUTO_SCAN", "1") == "1":
        db = next(get_db())
        try:
            scan_images(db, SCAN_DIR)
        finally:
            db.close()
