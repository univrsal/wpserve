from __future__ import annotations

from pydantic import BaseModel


class TagOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class ImageOut(BaseModel):
    id: int
    file_name: str
    file_path: str
    file_size: int
    width: int
    height: int
    format: str
    tags: list[TagOut]

    class Config:
        from_attributes = True
