from typing import List

from pydantic import BaseModel

from .sign import Sign


class Image(BaseModel):
    signs: List[Sign]
