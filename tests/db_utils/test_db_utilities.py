import json
from collections.abc import Generator
from typing import Any, Tuple, TypeAlias, cast, overload
from uuid import UUID, uuid4

import geopandas as gpd
import pandas as pd
import pytest
from curb_utils.db_utils import InvalidInputError, SmartCurbDB
from dotenv import load_dotenv
from geopandas.testing import assert_geodataframe_equal
from pandas.testing import assert_frame_equal
from pytest import fixture
from shapely.geometry import Point
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

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
        yield db, tmp_table
        db.connection.execute(text(f"DROP TABLE IF EXISTS {TEST_SCHEMA}.{tmp_table}"))


@fixture
def write_table_closed() -> Generator[str]:
    """Create a temporary copy of test_write with a random suffix,
    closes the connection and yeilds the table name.

    Attempts to re-open the connection delete the table on completion.
    """
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
    yield tmp_table

    with SmartCurbDB(dbname=TEST_DB, schema=TEST_SCHEMA) as db:
        assert db.connection is not None
        db.connection.execute(text(f"DROP TABLE IF EXISTS {TEST_SCHEMA}.{tmp_table}"))


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
        yield db, tmp_table
        db.connection.execute(text(f"DROP TABLE IF EXISTS {TEST_SCHEMA}.{tmp_table}"))


@fixture
def write_geo_table_closed() -> Generator[str]:
    """Create a temporary copy of test_write with_geo a random suffix,
    closes the connection and yeilds the table name.

    Attempts to re-open the connection delete the table on completion.
    """
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
    yield tmp_table

    with SmartCurbDB(dbname=TEST_DB, schema=TEST_SCHEMA) as db:
        assert db.connection is not None
        db.connection.execute(text(f"DROP TABLE IF EXISTS {TEST_SCHEMA}.{tmp_table}"))


@fixture
def write_delete_table() -> Generator[WriteTable]:
    """Create a temporary copy of test_delete with a random suffix,
    yield the db connection and table name, then drop the table."""
    suffix = uuid4().hex[:8]
    tmp_table = f"test_delete_{suffix}"

    with SmartCurbDB(dbname=TEST_DB, schema=TEST_SCHEMA) as db:
        assert db.connection is not None
        db.connection.execute(
            text(
                f"CREATE TABLE {TEST_SCHEMA}.{tmp_table} "
                f"(LIKE {TEST_SCHEMA}.test_delete INCLUDING ALL); "
                f"INSERT INTO {TEST_SCHEMA}.{tmp_table} "
                f"SELECT * FROM {TEST_SCHEMA}.test_delete;"
            )
        )
        yield db, tmp_table
        db.connection.execute(text(f"DROP TABLE IF EXISTS {TEST_SCHEMA}.{tmp_table}"))


# ── Convenience Functions ─────────────────────────────────────────────────────


@overload
def qsort(df: gpd.GeoDataFrame) -> gpd.GeoDataFrame: ...


@overload
def qsort(df: pd.DataFrame) -> pd.DataFrame: ...


def qsort(df: pd.DataFrame | gpd.GeoDataFrame) -> pd.DataFrame | gpd.GeoDataFrame:
    """Quickly sort and reset the index of a dataframe. Addresses potential
    for the pg database to return data in an undefined order.

    Retains the correct df or gdf type.

    """
    return df.sort_values("id").reset_index(drop=True)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_read_table(read_db: SmartCurbDB) -> None:
    df = qsort(read_db.get_data("test_read"))
    assert_frame_equal(expected_read(), df)


def test_read_table_dne(read_db: SmartCurbDB) -> None:
    with pytest.raises(ValueError):
        read_db.get_data("test_dne")


def test_read_db_dne() -> None:
    with pytest.raises(OperationalError):
        with SmartCurbDB(dbname="THIS_DB_DNE", schema=TEST_SCHEMA) as _:
            pass


def test_read_filtered(read_db: SmartCurbDB) -> None:
    df = qsort(read_db.get_data("test_read", filter="integer_field > 100"))
    complete_ex = expected_read()
    ex = complete_ex.loc[complete_ex["integer_field"] > 100].reset_index(drop=True)

    assert_frame_equal(ex, df)


def test_read_geo_table(read_db: SmartCurbDB) -> None:
    gdf = qsort(read_db.get_data("test_read_geo", geom_col="geometry"))
    assert_geodataframe_equal(expected_read_geo(), gdf)


def test_append_data(write_table: WriteTable) -> None:
    db, table_name = write_table
    data, write_data = expected_write()

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
    _, write_data = expected_write()

    # Convert int to a string for failure
    write_data["integer_field"] = "Not an integer"

    with pytest.raises(InvalidInputError):
        db.append_data(table_name, write_data)


def test_append_geo_data(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    data, write_data = expected_write_geo()

    db.append_data(table_name, write_data)
    result = db.get_data(table_name, geom_col="geometry")
    assert_geodataframe_equal(data, result)


def test_append_geo_data_json_as_dict(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    data = expected_read_geo()

    with pytest.raises(InvalidInputError):
        db.append_data(table_name, data)


def test_append_geo_data_int_as_string(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    _, write_data = expected_write_geo()

    # Convert int to a string for failure
    write_data["integer_field"] = "Not an integer"

    with pytest.raises(InvalidInputError):
        db.append_data(table_name, write_data)


def test_update_value_string(write_table: WriteTable) -> None:
    db, table_name = write_table
    data, write_data = expected_write()
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
    result = qsort(db.get_data(table_name))
    assert_frame_equal(data, result)


def test_update_value_json(write_table: WriteTable) -> None:
    db, table_name = write_table
    data, write_data = expected_write()

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
    result = qsort(db.get_data(table_name))
    assert_frame_equal(data, result)


def test_update_value_int_as_string(write_table: WriteTable) -> None:
    db, table_name = write_table
    _, write_data = expected_write()

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


def test_update_value_multiple_rows(write_table: WriteTable) -> None:
    db, table_name = write_table
    data, write_data = expected_write()

    db.append_data(table_name, write_data)

    # Attempt to update using a filter that returns multiple rows

    with pytest.raises(ValueError):
        db.modify_record(
            table_name,
            filter="integer_field < 100",
            column="string_field",
            value="New String",
        )


def test_update_value_zero_rows(write_table: WriteTable) -> None:
    db, table_name = write_table
    _, write_data = expected_write()

    db.append_data(table_name, write_data)

    # Attempt to update using a filter that returns multiple rows

    with pytest.raises(ValueError):
        db.modify_record(
            table_name,
            filter="integer_field < -100",
            column="string_field",
            value="New String",
        )


def test_update_value_invalid_filter(write_table: WriteTable) -> None:
    db, table_name = write_table
    data, write_data = expected_write()

    db.append_data(table_name, write_data)

    with pytest.raises(ValueError):
        db.modify_record(
            table_name,
            filter="dne < -100",
            column="string_field",
            value="New String",
        )


def test_update_geo_value_string(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    data, write_data = expected_write_geo()

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
    result = qsort(db.get_data(table_name, geom_col="geometry"))
    assert_geodataframe_equal(data, result)


def test_update_geo_value_json(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    data, write_data = expected_write_geo()

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
    result = qsort(db.get_data(table_name, geom_col="geometry"))
    assert_geodataframe_equal(data, result)


def test_update_value_geo_int_as_string(write_geo_table: WriteTable) -> None:
    db, table_name = write_geo_table
    _, write_data = expected_write()

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


def test_update_or_append_inserts_new(write_table: WriteTable) -> None:
    """All rows are new — behaves like append_data."""
    db, table_name = write_table
    data, write_data = expected_write()

    db.update_or_append(table_name, write_data, key_columns=["id"])
    result = qsort(db.get_data(table_name))
    assert_frame_equal(data, result)


def test_update_or_append_updates_existing(write_table: WriteTable) -> None:
    """All rows already exist — all are updated."""
    db, table_name = write_table
    data, write_data = expected_write()

    db.append_data(table_name, write_data)

    updated = write_data.copy()
    updated["string_field"] = "Updated"
    db.update_or_append(table_name, updated, key_columns=["id"])

    result = qsort(db.get_data(table_name))
    expected = data.copy()
    expected["string_field"] = "Updated"
    assert_frame_equal(expected, result)


def test_update_or_append_mixed(write_table: WriteTable) -> None:
    """Some rows exist (updated), some are new (inserted)."""
    db, table_name = write_table
    data, write_data = expected_write()

    # Pre-populate only the first three rows
    db.append_data(table_name, write_data.iloc[:3])

    # Upsert all five — rows 1-3 updated, rows 4-5 inserted
    updated = write_data.copy()
    updated.loc[updated.index[:3], "string_field"] = "Updated"
    db.update_or_append(table_name, updated, key_columns=["id"])

    result = qsort(db.get_data(table_name))
    expected = data.copy()
    expected.loc[expected.index[:3], "string_field"] = "Updated"
    assert_frame_equal(expected, result)


def test_update_or_append_geo(write_geo_table: WriteTable) -> None:
    """GeoDataFrame: some rows exist (updated), some are new (inserted)."""
    db, table_name = write_geo_table
    data, write_data = expected_write_geo()

    # Pre-populate only the first three rows
    db.append_data(table_name, write_data.iloc[:3])

    # Upsert all five — rows 1-3 updated, rows 4-5 inserted
    updated = write_data.copy()
    updated.loc[updated.index[:3], "string_field"] = "Updated"
    db.update_or_append(table_name, updated, key_columns=["id"])

    result = qsort(db.get_data(table_name, geom_col="geometry"))
    expected = data.copy()
    expected.loc[expected.index[:3], "string_field"] = "Updated"
    assert_geodataframe_equal(expected, result)


def test_update_or_append_key_not_in_data(write_table: WriteTable) -> None:
    db, table_name = write_table
    data = expected_read().drop(columns=["id"])
    with pytest.raises(ValueError, match="key_columns"):
        db.update_or_append(table_name, data, key_columns=["id"])


def test_update_or_append_key_not_in_table(write_table: WriteTable) -> None:
    db, table_name = write_table
    data = expected_read()
    data["nonexistent"] = "x"
    with pytest.raises(ValueError, match="key_columns"):
        db.update_or_append(table_name, data, key_columns=["nonexistent"])


def test_update_or_append_no_constraint(write_table: WriteTable) -> None:
    """key_columns that exist in both data and table but have no constraint."""
    db, table_name = write_table
    data = expected_read()
    with pytest.raises(ValueError, match="UNIQUE or PRIMARY KEY"):
        db.update_or_append(table_name, data, key_columns=["string_field"])


def test_update_or_append_only_key_columns(write_table: WriteTable) -> None:
    db, table_name = write_table
    data = expected_read()[["id"]]
    with pytest.raises(ValueError, match="no columns to update"):
        db.update_or_append(table_name, data, key_columns=["id"])


def test_update_or_append_missing_one_column(write_table: WriteTable) -> None:
    db, table_name = write_table
    data = expected_read()[["id", "integer_field"]]
    with pytest.raises(ValueError, match="does not contain all columns"):
        db.update_or_append(table_name, data, key_columns=["id"])


def test_no_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ValueError failure if the database password is not set"""

    monkeypatch.delenv("DB_PASSWORD", raising=False)

    # Attempt to create a connection without password
    with pytest.raises(ValueError):
        with SmartCurbDB(dbname=TEST_DB, schema=TEST_SCHEMA):
            pass


@pytest.mark.parametrize(
    "key_columns",
    [
        ["id"],
        ["id", "unique_field"],
    ],
)
def test_delete_records(write_delete_table: WriteTable, key_columns: list[str]) -> None:
    """Test delete with multiple column filters combined"""
    db, table_name = write_delete_table
    result = db.get_data(table_name)
    data = data_to_delete()
    db.delete(table_name, data, key_columns=key_columns)
    result = db.get_data(table_name)
    expected = expected_delete()
    assert_frame_equal(expected, result)


def test_delete_key_not_in_data(write_delete_table: WriteTable) -> None:
    """Test delete failure when key column(s) are not included in the provided data."""
    db, table_name = write_delete_table
    data = data_to_delete().drop(columns=["id"])
    with pytest.raises(ValueError, match="key_columns"):
        db.delete(table_name, data, key_columns=["id"])


def test_delete_key_not_in_table(write_delete_table: WriteTable) -> None:
    """Test delete failure when key column(s) do not exist in the database table."""
    db, table_name = write_delete_table
    data = data_to_delete()
    data["nonexistent"] = "x"
    with pytest.raises(ValueError, match="key_columns"):
        db.delete(table_name, data, key_columns=["nonexistent"])


def test_delete_no_data(write_delete_table: WriteTable) -> None:
    """Test delete failure when no data is provided."""
    db, table_name = write_delete_table
    data = pd.DataFrame(
        columns=["id", "unique_field", "integer_field", "string_field", "jsonb_field"]
    )
    with pytest.raises(ValueError, match="No data provided for deletion."):
        db.delete(table_name, data, key_columns=["id"])


def test_failed_transaction(write_table_closed: str) -> None:
    """Veify that a failed transaction is properly rolled back"""

    data, write_data = expected_write()
    with SmartCurbDB(TEST_DB, TEST_SCHEMA) as db:
        # Run a good followed by a failed transaction
        db.append_data(write_table_closed, write_data)

        # This should fail since records already exist
        with pytest.raises(InvalidInputError):
            db.append_data(write_table_closed, write_data)

    with SmartCurbDB(TEST_DB, TEST_SCHEMA) as db:
        # The dataframe shoudl be empty
        mt = db.get_data(write_table_closed)

    assert len(mt) == 0


def test_failed_geo_transaction(write_geo_table_closed: str) -> None:
    """Veify that a failed geo transaction is properly rolled back"""

    data, write_data = expected_write()
    with SmartCurbDB(TEST_DB, TEST_SCHEMA) as db:
        # Run a good followed by a failed transaction
        db.append_data(write_geo_table_closed, write_data)

        # This should fail since records already exist
        with pytest.raises(InvalidInputError):
            db.append_data(write_geo_table_closed, write_data)

    with SmartCurbDB(TEST_DB, TEST_SCHEMA) as db:
        # The dataframe shoudl be empty
        mt = db.get_data(write_geo_table_closed, geom_col="geometry")

    assert len(mt) == 0


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

    return data.sort_values("id").reset_index(drop=True)


def expected_write() -> Tuple[pd.DataFrame, pd.DataFrame]:
    data = expected_read()
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)

    return (data, write_data)


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

    return data.sort_values("id").reset_index(drop=True)


def expected_write_geo() -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    data = expected_read_geo()
    write_data = data.copy()
    write_data["jsonb_field"] = write_data["jsonb_field"].apply(json.dumps)

    return (data, write_data)


def expected_read_delete() -> pd.DataFrame:
    """Returns all records before deletion (data_to_delete + expected_delete)."""
    data1 = data_to_delete()
    data2 = expected_delete()
    combined = pd.concat([data1, data2], ignore_index=True)
    return combined.sort_values("id").reset_index(drop=True)


def expected_delete() -> pd.DataFrame:
    data = pd.DataFrame(
        {
            "id": [
                UUID("660e8400-e29b-41d4-a716-446655440004"),
                UUID("660e8400-e29b-41d4-a716-446655440005"),
            ],
            "unique_field": [
                UUID("000e0000-e29b-41d4-a000-446655440004"),
                UUID("000e0000-e29b-41d4-a000-446655440005"),
            ],
            "integer_field": [40, 50],
            "string_field": ["US History", "Parking Clerk"],
            "jsonb_field": [{"location": "Boston"}, {"location": "Boston"}],
        }
    )

    return data.sort_values("id").reset_index(drop=True)


def data_to_delete() -> pd.DataFrame:
    data = pd.DataFrame(
        {
            "id": [
                UUID("660e8400-e29b-41d4-a716-446655440001"),
                UUID("660e8400-e29b-41d4-a716-446655440002"),
                UUID("660e8400-e29b-41d4-a716-446655440003"),
            ],
            "unique_field": [
                UUID("000e0000-e29b-41d4-a000-446655440001"),
                UUID("000e0000-e29b-41d4-a000-446655440002"),
                UUID("000e0000-e29b-41d4-a000-446655440003"),
            ],
            "integer_field": [10, 20, 30],
            "string_field": ["City Hall", "Rivers Edge", "MIT"],
            "jsonb_field": [
                {"location": "Boston"},
                {"location": "Medford"},
                {"location": "Cambridge"},
            ],
        }
    )
    return data.sort_values("id").reset_index(drop=True)
