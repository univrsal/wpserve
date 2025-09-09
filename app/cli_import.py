from __future__ import annotations

"""CLI tool to import images & tags from an existing wallpapers.db.

Usage (after activating venv):
  python -m app.cli_import --source wallpapers.db --copy-from /mnt/wallpapers_repo --limit 50

It copies (or symlinks) image files into static/images and inserts rows
into the local image_browser.db (created via app.main) avoiding duplicates.
"""

import argparse
import shutil
from pathlib import Path
from typing import Optional
import sqlite3

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.image import Image, Tag
import uuid
from PIL import Image as PILImage

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def import_data(
    source_db: Path,
    copy_from: Path,
    mode: str = "copy",
    limit: Optional[int] = None,
    verbose: bool = True,
) -> None:
    if mode not in {"copy", "link", "skip"}:
        raise SystemExit("mode must be one of copy|link|skip")

    if not source_db.exists():
        raise SystemExit(f"Source DB not found: {source_db}")

    dest_dir = Path("static/images")
    dest_thumb_dir = Path("static/thumbs")
    ensure_dir(dest_dir)
    ensure_dir(dest_thumb_dir)

    con = sqlite3.connect(str(source_db))
    cur = con.cursor()

    # Fetch images
    q = "SELECT id, file_path, file_name, file_size, width, height FROM image ORDER BY id"
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = cur.execute(q).fetchall()

    # Preload tag mapping: image_id -> [tag_names]
    tag_rows = cur.execute(
        """
        SELECT i.id, t.name
        FROM image_tag it
        JOIN image i ON i.id = it.image_id
        JOIN tag t ON t.id = it.tag_id
        """
    ).fetchall()

    image_tags: dict[int, list[str]] = {}
    for img_id, tag_name in tag_rows:
        image_tags.setdefault(img_id, []).append(tag_name)

    session: Session = SessionLocal()
    # Preload existing tags into a cache to avoid duplicate INSERTs / unique constraint errors
    # Using plain dict without static typing due to SQLAlchemy instrumentation of attributes
    # Convert to a plain dict[str, Tag] (ignore type checkers complaining about SQLAlchemy attributes)
    tag_cache: dict[str, Tag] = {str(t.name): t for t in session.query(Tag).all()}
    imported = skipped = 0
    try:
        for img_id, file_path, file_name, file_size, width, height in rows:
            tags = image_tags.get(img_id, [])
            if "v" not in tags:
                continue
            ext = Path(file_name).suffix.lower()
            if ext not in SUPPORTED_EXT:
                if verbose:
                    print(f"Skip unsupported ext: {file_name}")
                skipped += 1
                continue
            # Avoid duplicates by filename
            if session.query(Image).filter(Image.filename == file_name).first():
                if verbose:
                    print(f"Already present: {file_name}")
                skipped += 1
                continue
            # Build source path (source DB paths appear to start with a leading slash like /4k/...) so we prefix a dot
            src_path = copy_from / Path("." + file_path)
            if not src_path.exists():
                if verbose:
                    print(f"Missing source file: {src_path}")
                skipped += 1
                continue
            ext = Path(file_name).suffix.lower()
            new_filename = f"{uuid.uuid4().hex}{ext}"
            dest_file = dest_dir / new_filename
            dest_thumb_file = dest_thumb_dir / new_filename

            if mode == "copy":
                shutil.copy2(src_path, dest_file)
            elif mode == "link":
                try:
                    if dest_file.exists():
                        dest_file.unlink()
                    dest_file.symlink_to(src_path.resolve())
                except OSError:
                    shutil.copy2(src_path, dest_file)

            # create thumbnail (maintain aspect ratio, fit within 480x270)
            if mode in {"copy", "link"}:
                try:
                    with PILImage.open(
                        dest_file if dest_file.exists() else src_path
                    ) as im:
                        im.thumbnail((480, 270))
                        if im.mode in ("RGBA", "LA"):
                            im = im.convert("RGB")
                        thumb_mode = "JPEG"
                        save_kwargs = {"quality": 80}
                        im.save(dest_thumb_file, thumb_mode, **save_kwargs)
                except Exception as e:
                    if verbose:
                        print(f"Thumbnail failed for {file_name}: {e}")

            img = Image(
                filename=new_filename,
                width=width,
                height=height,
                file_size=file_size,
            )
            session.add(img)

            # Tags (deduplicate per image to avoid attaching same tag twice)
            for tag_name in sorted(set(image_tags.get(img_id, []))):
                # Use cache first
                tag_obj = tag_cache.get(tag_name)
                if not tag_obj:
                    tag_obj = Tag(name=tag_name)
                    session.add(tag_obj)
                    # Flush so subsequent queries within this transaction can see it (and to catch uniqueness early)
                    session.flush([tag_obj])
                    tag_cache[tag_name] = tag_obj
                img.tags.append(tag_obj)

            imported += 1
            if imported % 100 == 0:  # commit in larger batches
                session.commit()
                if verbose:
                    print(f"Committed {imported} images so far...")
        session.commit()
    finally:
        session.close()
        con.close()

    print(f"Import finished: imported={imported} skipped={skipped}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Import images & tags from wallpapers.db")
    p.add_argument(
        "--source",
        type=Path,
        default=Path("wallpapers.db"),
        help="Path to source wallpapers.db",
    )
    p.add_argument(
        "--copy-from",
        dest="copy_from",
        type=Path,
        help="Base directory containing source files if file_path is relative or not directly valid.",
    )
    p.add_argument(
        "--mode",
        choices=["copy", "link", "skip"],
        default="copy",
        help="How to bring files into static/images",
    )
    p.add_argument(
        "--limit", type=int, default=None, help="Limit number of images for testing"
    )
    p.add_argument("-q", dest="quiet", action="store_true", help="Reduce output")
    return p


def main():
    args = build_arg_parser().parse_args()
    import_data(
        source_db=args.source,
        copy_from=args.copy_from,
        mode=args.mode,
        limit=args.limit,
        verbose=not args.quiet,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
