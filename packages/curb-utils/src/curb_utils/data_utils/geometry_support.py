# utilities/data/geometry_support.py
from __future__ import annotations

import json
from collections.abc import Mapping

from shapely import wkt
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from .type_blueprint import PydanticTypeBlueprint


class Geometry(PydanticTypeBlueprint):
    __default_error__ = (
        "Unrecognized geometry format, please check geometry pydantic type"
    )


@Geometry.register
def recognize_shapely_object(value):
    if isinstance(value, BaseGeometry):
        return str(value)


@Geometry.register
def recognize_any_wkt_string(value):
    if isinstance(value, str):
        try:
            wkt.loads(value)
            return value  # preserve original string
        except Exception:
            return None


@Geometry.register
def recognize_geojson_mapping(value):
    from collections.abc import Mapping

    if isinstance(value, Mapping):
        try:
            return shape(dict(value)).wkt
        except Exception:
            return None


@Geometry.register
def recognize_geojson_string(value):
    if isinstance(value, str):
        try:
            obj = json.loads(value)
        except Exception:
            return None

        if isinstance(obj, Mapping) and "type" in obj and "coordinates" in obj:
            try:
                return shape(dict(obj)).wkt
            except Exception:
                return None
