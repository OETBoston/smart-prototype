import json
from collections.abc import Generator
from typing import Any, TypeAlias, cast
from uuid import UUID, uuid4

import geopandas as gpd
import pandas as pd
import pytest
from db_utilities import InvalidInputError, SmartCurbDB
from dotenv import load_dotenv
from geopandas.testing import assert_geodataframe_equal
from pandas.testing import assert_frame_equal
from pytest import fixture
from shapely.geometry import Point
from sqlalchemy import text

# ── Setup ─___─────────────────────────────────────────────────────────────────
TEST_DB = "tests"
TEST_SCHEMA = "test_data"

load_dotenv()

WriteTable: TypeAlias = tuple[SmartCurbDB, str]

# ── Fixtures ──────────────────────────────────────────────────────────────────


@fixture
def read_db() -> Generator[SmartCurbDB]:
    """Return a connection to the test database and schema, for the
    purposes of reading data only.

    Tests should not write to this database."""

    with SmartCurbDB(dbname=TEST_DB, schema=TEST_SCHEMA) as db:
        yield db


@fixture
def write_table() -> Generator[WriteTable]:
    """Create a temporary copy of test_write with a random suffix,
    yield the db connection and table name, then drop the table."""
    suffix = uuid4().hex[:8]
    tmp_table = f"test_write_{suffix}"

    with SmartCurbDB(dbname=TEST_DB, schema=TEST_SCHEMA) as db:
        assert db.connection is not None
        db.connection.execute(
            text(
                f"CREATE TABLE {TEST_SCHEMA}.{tmp_table} "
                f"(LIKE {TEST_SCHEMA}.test_write INCLUDING ALL)"
            )
        )
        db.connection.commit()
        yield db, tmp_table
        db.connection.execute(text(f"DROP TABLE IF EXISTS {TEST_SCHEMA}.{tmp_table}"))
        db.connection.commit()


@fixture
def write_geo_table() -> Generator[WriteTable]:
    """Create a temporary copy of test_write_geo with a random suffix,
    yield the db connection and table name, then drop the table."""
    suffix = uuid4().hex[:8]
    tmp_table = f"test_write_geo_{suffix}"

    with SmartCurbDB(dbname=TEST_DB, schema=TEST_SCHEMA) as db:
        assert db.connection is not None
        db.connection.execute(
            text(
                f"CREATE TABLE {TEST_SCHEMA}.{tmp_table} "
                f"(LIKE {TEST_SCHEMA}.test_write_geo INCLUDING ALL)"
            )
        )
        db.connection.commit()
        yield db, tmp_table
        db.connection.execute(text(f"DROP TABLE IF EXISTS {TEST_SCHEMA}.{tmp_table}"))
        db.connection.commit()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_read_table(read_db) -> None:
    df = read_db.get_data("test_read")
    assert_frame_equal(expected_read(), df)


def test_read_filtered(read_db) -> None:
    df = read_db.get_data("test_read", filter="integer_field > 100")
    complete_ex = expected_read()
    ex = complete_ex.loc[complete_ex["integer_field"] > 100].reset_index(drop=True)

    assert_frame_equal(ex, df)


def test_read_geo_table(read_db) -> None:
    gdf = read_db.get_data("test_read_geo", geom_col="geometry")
    assert_geodataframe_equal(expected_read_geo(), gdf)


def test_append_data(write_table: WriteTable) -> None:
    db, table_name = write_table
    data = expected_read()

    # Convert the jsonb field to a string
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)

    db.append_data(table_name, write_data)
    result = db.get_data(table_name)
    assert_frame_equal(data, result)


def test_append_data_json_as_dict(write_table: WriteTable) -> None:
    """Tests incorrect insertion of dict instead of a json string to a jsonb
    field
    """
    db, table_name = write_table
    data = expected_read()

    with pytest.raises(InvalidInputError):
        db.append_data(table_name, data)


def test_append_data_int_as_string(write_table: WriteTable) -> None:
    db, table_name = write_table
    data = expected_read()

    # Convert the jsonb field to a string
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)

    # Convert int to a string for failure
    write_data["integer_field"] = "Not an integer"

    with pytest.raises(InvalidInputError):
        db.append_data(table_name, write_data)


def test_append_geo_data(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    data = expected_read_geo()

    # Convert the jsonb field to a string
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)

    db.append_data(table_name, write_data)
    result = db.get_data(table_name, geom_col="geometry")
    assert_frame_equal(data, result)


def test_append_geo_data_json_as_dict(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    data = expected_read_geo()

    with pytest.raises(InvalidInputError):
        db.append_data(table_name, data)


def test_append_geo_data_int_as_string(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    data = expected_read_geo()

    # Convert the jsonb field to a string
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)

    # Convert int to a string for failure
    write_data["integer_field"] = "Not an integer"

    with pytest.raises(InvalidInputError):
        db.append_data(table_name, write_data)


def test_update_value_string(write_table: WriteTable) -> None:
    db, table_name = write_table
    data = expected_read()

    # Convert the jsonb field to a string
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)
    db.append_data(table_name, write_data)

    # Update a field - both in the database and the expected data
    update_uuid = "550e8400-e29b-41d4-a716-446655440003"
    db.modify_record(
        table_name,
        filter=f"id = '{update_uuid}'",
        column="string_field",
        value="Updated This!",
    )
    data.loc[data["id"] == UUID(update_uuid), "string_field"] = "Updated This!"

    # Read and confirm
    result = db.get_data(table_name).sort_values(by="id").reset_index(drop=True)
    assert_frame_equal(data, result)


def test_update_value_json(write_table: WriteTable) -> None:
    db, table_name = write_table
    data = expected_read()

    # Convert the jsonb field to a string
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)
    db.append_data(table_name, write_data)

    # Update a field - both in the database and the expected data
    update_uuid = "550e8400-e29b-41d4-a716-446655440003"
    new_value = {"This is new": 12345}
    db.modify_record(
        table_name,
        filter=f"id = '{update_uuid}'",
        column="jsonb_field",
        value=json.dumps(new_value),
    )
    data.at[2, "jsonb_field"] = cast(Any, new_value)

    # Read and confirm
    result = db.get_data(table_name).sort_values(by="id").reset_index(drop=True)
    assert_frame_equal(data, result)


def test_update_value_int_as_string(write_table: WriteTable) -> None:
    db, table_name = write_table
    data = expected_read()

    # Convert the jsonb field to a string
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)
    db.append_data(table_name, write_data)

    # Update a field - both in the database and the expected data
    update_uuid = "550e8400-e29b-41d4-a716-446655440003"

    with pytest.raises(InvalidInputError):
        db.modify_record(
            table_name,
            filter=f"id = '{update_uuid}'",
            column="integer_field",
            value="Not a String",
        )


def test_update_geo_value_string(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    data = expected_read_geo()

    # Convert the jsonb field to a string
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)
    db.append_data(table_name, write_data)

    # Update a field - both in the database and the expected data
    update_uuid = "660e8400-e29b-41d4-a716-446655440003"
    db.modify_record(
        table_name,
        filter=f"id = '{update_uuid}'",
        column="string_field",
        value="Updated This!",
    )
    data.loc[data["id"] == UUID(update_uuid), "string_field"] = "Updated This!"

    # Read and confirm
    result = (
        db.get_data(table_name, geom_col="geometry")
        .sort_values(by="id")
        .reset_index(drop=True)
    )
    assert_frame_equal(data, result)


def test_update_geo_value_json(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    data = expected_read_geo()

    # Convert the jsonb field to a string
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)
    db.append_data(table_name, write_data)

    # Update a field - both in the database and the expected data
    update_uuid = "660e8400-e29b-41d4-a716-446655440003"
    new_value = {"This is new": 12345}
    db.modify_record(
        table_name,
        filter=f"id = '{update_uuid}'",
        column="jsonb_field",
        value=json.dumps(new_value),
    )
    data.at[2, "jsonb_field"] = cast(Any, new_value)

    # Read and confirm
    result = (
        db.get_data(table_name, geom_col="geometry")
        .sort_values(by="id")
        .reset_index(drop=True)
    )
    assert_frame_equal(data, result)


def test_update_value_geo_int_as_string(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    data = expected_read()

    # Convert the jsonb field to a string
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)
    db.append_data(table_name, write_data)

    # Update a field - both in the database and the expected data
    update_uuid = "550e8400-e29b-41d4-a716-446655440003"

    with pytest.raises(InvalidInputError):
        db.modify_record(
            table_name,
            filter=f"id = '{update_uuid}'",
            column="integer_field",
            value="Not a String",
        )


# ── Expected Data ─────────────────────────────────────────────────────────────


def expected_read() -> pd.DataFrame:
    data = pd.DataFrame(
        {
            "id": [
                UUID("550e8400-e29b-41d4-a716-446655440001"),
                UUID("550e8400-e29b-41d4-a716-446655440002"),
                UUID("550e8400-e29b-41d4-a716-446655440003"),
                UUID("550e8400-e29b-41d4-a716-446655440004"),
                UUID("550e8400-e29b-41d4-a716-446655440005"),
            ],
            "integer_field": [42, 100, 255, 1, 999],
            "string_field": [
                "Sample record 1",
                "Sample record 2",
                "Sample record 3",
                "Sample record 4",
                "Sample record 5",
            ],
            "jsonb_field": [
                {"key": "value", "count": 1, "active": True},
                {"name": "test", "data": [1, 2, 3], "nested": {"field": "value"}},
                {
                    "status": "active",
                    "priority": "high",
                    "tags": ["production", "critical"],
                },
                {"empty": {}, "null_value": None},
                {"numeric": 3.14159, "boolean": False, "text": "hello world"},
            ],
        }
    )

    return data


def expected_read_geo() -> gpd.GeoDataFrame:
    data = gpd.GeoDataFrame(
        {
            "id": [
                UUID("660e8400-e29b-41d4-a716-446655440001"),
                UUID("660e8400-e29b-41d4-a716-446655440002"),
                UUID("660e8400-e29b-41d4-a716-446655440003"),
                UUID("660e8400-e29b-41d4-a716-446655440004"),
                UUID("660e8400-e29b-41d4-a716-446655440005"),
            ],
            "integer_field": [10, 20, 30, 40, 50],
            "string_field": [
                "City Hall",
                "Rivers Edge",
                "MIT",
                "US History",
                "Parking Clerk",
            ],
            "jsonb_field": [
                {"location": "Boston"},
                {"location": "Medford"},
                {"location": "Cambridge"},
                {"location": "Boston"},
                {"location": "Boston"},
            ],
            "geometry": [
                Point(-71.05796081347341, 42.36041637870849),
                Point(-71.0743071567904, 42.41042214024287),
                Point(-71.0940387442943, 42.3601268800116),
                Point(-71.05347673995645, 42.36373998244562),
                Point(-71.0575510602215, 42.360579396935556),
            ],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )

    return data
