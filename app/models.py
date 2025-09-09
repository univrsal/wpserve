from __future__ import annotations

from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, Table
from sqlalchemy.orm import relationship, Mapped, mapped_column

from .database import Base


image_tag_table = Table(
    "image_tag",
    Base.metadata,
    Column("image_id", ForeignKey("image.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


class Image(Base):
    __tablename__ = "image"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(TIMESTAMP, nullable=False)
    updated_at: Mapped[str] = mapped_column(TIMESTAMP, nullable=False)
    # last_used exists but not required for current pages

    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary=image_tag_table, back_populates="images", lazy="joined"
    )


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[str] = mapped_column(TIMESTAMP, nullable=False)

    images: Mapped[list[Image]] = relationship(
        Image, secondary=image_tag_table, back_populates="tags", lazy="selectin"
    )
