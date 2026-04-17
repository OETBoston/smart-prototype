import json

import pytest
from data_utils.geometry_support import Geometry
from pydantic import BaseModel
from shapely import wkt as wkt_module
from shapely.geometry import LineString, Point, shape


class TestModel(BaseModel):
    geom: Geometry | None = None
    model_config = {"validate_assignment": True}


def wkt_equal(a: str, b: str) -> bool:
    """
    Compares two WKT strings by parsing them into Shapely geometries.
    Ensures they represent the same geometry, even if formatting changes.
    """
    return wkt_module.loads(a).equals(wkt_module.loads(b))


# -------------------------------------------------------
# SHAPELY OBJECTS
# -------------------------------------------------------


def test_shapely_geometry_to_wkt_exact_match():
    geom = LineString([(0, 0), (1, 1)])
    m = TestModel(geom=geom)
    expected = geom.wkt
    assert isinstance(m.geom, str)
    assert wkt_equal(m.geom, expected)


def test_assignment_validation_shapely_exact_match():
    geom = Point(5, 5)
    expected = geom.wkt
    m = TestModel()
    m.geom = geom
    assert isinstance(m.geom, str)
    assert wkt_equal(m.geom, expected)


# -------------------------------------------------------
# WKT STRINGS
# -------------------------------------------------------


def test_valid_wkt_passes_through_exactly():
    wkt_str = "POINT (1 2)"
    m = TestModel(geom=wkt_str)
    assert m.geom == wkt_str


def test_assignment_validation_wkt_exact_preservation():
    wkt_str = "POINT (3 4)"
    m = TestModel()
    m.geom = wkt_str
    assert m.geom == wkt_str


# -------------------------------------------------------
# GEOJSON DICT
# -------------------------------------------------------


def test_geojson_dict_to_wkt_exact_match():
    geojson = {"type": "Point", "coordinates": [1, 2]}
    expected = shape(geojson).wkt
    m = TestModel(geom=geojson)
    assert isinstance(m.geom, str)
    assert wkt_equal(m.geom, expected)


def test_coordinate_list_to_wkt_exact_match():
    geojson = {"type": "LineString", "coordinates": [[0, 0], [2, 2]]}
    expected = shape(geojson).wkt
    m = TestModel(geom=geojson)
    assert isinstance(m.geom, str)
    assert wkt_equal(m.geom, expected)


# -------------------------------------------------------
# GEOJSON STRING
# -------------------------------------------------------


def test_geojson_string_to_wkt_exact_match():
    geojson = '{"type": "Point", "coordinates": [10, 20]}'
    expected = shape(json.loads(geojson)).wkt
    m = TestModel(geom=geojson)
    assert isinstance(m.geom, str)
    assert wkt_equal(m.geom, expected)


def test_geojson_string_linestring():
    geojson = '{"type": "LineString", "coordinates": [[0,0],[3,3]]}'
    expected = shape(json.loads(geojson)).wkt
    m = TestModel(geom=geojson)
    assert isinstance(m.geom, str)
    assert wkt_equal(m.geom, expected)


# -------------------------------------------------------
# FAILURES: INVALID WKT, INVALID GEOJSON, RANDOM JUNK
# -------------------------------------------------------


def test_invalid_wkt_raises():
    bad_wkt = "NOT_A_REAL_GEOMETRY"
    with pytest.raises(ValueError) as exc:
        TestModel(geom=bad_wkt)
    assert "Unrecognized geometry format" in str(exc.value)


def test_invalid_geojson_string_raises():
    bad_geojson = '{"type": "Point", "coords": [1,2]}'  # invalid geometry
    with pytest.raises(ValueError) as exc:
        TestModel(geom=bad_geojson)
    assert "Unrecognized geometry format" in str(exc.value)


def test_invalid_geojson_non_json_string_raises():
    bad_geojson = "{this is not json}"
    with pytest.raises(ValueError) as exc:
        TestModel(geom=bad_geojson)
    assert "Unrecognized geometry format" in str(exc.value)


def test_arbitrary_value_raises():
    with pytest.raises(ValueError) as exc:
        TestModel(geom=42)
    assert "Unrecognized geometry format" in str(exc.value)


def test_unrecognized_list_raises():
    with pytest.raises(ValueError) as exc:
        TestModel(geom=[1, 2, "lol"])
    assert "Unrecognized geometry format" in str(exc.value)


# -------------------------------------------------------
# NONE HANDLING
# -------------------------------------------------------


def test_none_is_preserved():
    m = TestModel(geom=None)
    assert m.geom is None
