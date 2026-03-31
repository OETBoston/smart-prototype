from collections.abc import Generator
from uuid import UUID

import pandas as pd
from db_utilities import SmartCurbDB
from dotenv import load_dotenv
from pandas.testing import assert_frame_equal
from pytest import fixture

TEST_DB = "tests"
TEST_SCHEMA = "test_data"

load_dotenv()


@fixture
def read_db() -> Generator[SmartCurbDB]:
    """Return a connection to the test database and schema, for the
    purposes of reading data only.

    Tests should not write to this database."""

    with SmartCurbDB(dbname=TEST_DB, schema=TEST_SCHEMA) as db:
        yield db


def test_read_table(read_db) -> None:
    df = read_db.get_data("test_read")
    assert_frame_equal(expected_read(), df)


def test_read_filtered(read_db) -> None:
    df = read_db.get_data("test_read", filter="integer_field > 100")
    complete_ex = expected_read()
    ex = complete_ex.loc[complete_ex["integer_field"] > 100].reset_index(drop=True)

    assert_frame_equal(ex, df)


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
