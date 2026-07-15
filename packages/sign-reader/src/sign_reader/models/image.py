from typing import Generic, List, TypeVar

from pydantic import BaseModel

from .sign import Sign, SignExtended

T = TypeVar("T")


class ImageBase(BaseModel, Generic[T]):
    signs: List[T]


class Image(ImageBase[Sign]):
    pass


class ImageExtended(ImageBase[SignExtended]):
    pass
