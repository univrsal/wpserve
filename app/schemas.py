from __future__ import annotations
from typing import List
from pydantic import BaseModel


class TagBase(BaseModel):
    name: str


class TagRead(TagBase):
    id: int

    class Config:
        orm_mode = True


class ImageBase(BaseModel):
    filename: str
    width: int
    height: int
    file_size: int


class ImageRead(ImageBase):
    id: int
    tags: List[TagRead] = []

    class Config:
        orm_mode = True
