from typing import Any, ClassVar, Optional

from curb_utils.data_utils.accessor import DataAccessor, QuerySpec
from pydantic import BaseModel, Field


# Assuming data_utils.queries_and_contracts is where BaseEntity lives
# from data_utils.queries_and_contracts import BaseEntity
# Since BaseEntity definition is missing, defining a simple mock here for completeness
class BaseEntity(BaseModel):
    @classmethod
    def get_table_name_cls(cls):
        # Accesses the ClassVar defined below
        return getattr(cls, "_TABLE_NAME", cls.__name__.lower())


from google.cloud.bigquery import SchemaField

# --- New Mock Implementation ---


class MockDataClient:
    """
    A mock that implements the DataClient protocol (execute_query and raw_sql).
    It stores the last QuerySpec it received for assertion purposes.
    """

    def __init__(self):
        # Store the received spec here
        self.last_query_spec: Optional[QuerySpec] = None

    def execute_query(self, query_spec: QuerySpec) -> Any:
        # 1. Store the received spec for assertion
        self.last_query_spec = query_spec
        # 2. Return the format expected by DataAccessor.get (a list of data dictionaries)
        # We return an empty list since we are testing the query construction, not data flow.
        return []

    def raw_sql(self, sql_query: str) -> Any:
        # Implementation for raw_sql is not needed for this test scenario
        return []


# Assuming you define TEST_PROJECT_ID and TEST_DATASET_ID somewhere, or use placeholders.
TEST_PROJECT_ID = "mock_project"
TEST_DATASET_ID = "mock_dataset"

# --- Test ---


def test_fetch_generic_data_constructs_correct_spec():
    """
    Tests the DataAccessor.get method correctly translates Pydantic models
    into a fully qualified QuerySpec.
    """

    # --- ARRANGE ---

    # 1. Define a simple test model and filter
    class UserTestModel(BaseEntity):
        _TABLE_NAME: ClassVar[str] = "users_table"
        _ENTITY_SCHEMA: ClassVar[list[SchemaField]] = [
            SchemaField("user_id", "STRING"),
            SchemaField("status", "STRING"),
        ]
        user_id: str
        status: str

    class UserTestFilter(BaseEntity):
        status: Optional[str] = Field(None, description="Filter by status.")

    expected_limit = 20
    mock_client = MockDataClient()

    # 1. Instantiate DataAccessor with the required map
    accessor = DataAccessor(
        client=mock_client, current_prefix=f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}"
    )

    # 2. Instantiate the filter
    input_filter = UserTestFilter(status="active")

    # Determine the expected FQN (project.dataset.table)
    expected_fqn = f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}.{UserTestModel._TABLE_NAME}"

    # --- ACT ---
    result = accessor.get(
        entity_model=UserTestModel, filter=input_filter, limit=expected_limit
    )

    # --- ASSERT ---
    # 1. Check the return value (should be an empty list since the mock returned an empty list)
    assert result == []

    # 2. Check the spec that was captured by the mock client
    received_spec = mock_client.last_query_spec
    assert received_spec is not None

    # Assert against the full qualified table name (FQN)
    assert received_spec.table == expected_fqn
    assert received_spec.columns == ["user_id", "status"]
    assert received_spec.limit == expected_limit

    # Verify the filter was translated correctly
    # Note: AccessorSelectQueryBuilder maps 'status' -> ('status', '=', 'active')
    assert received_spec.filters == [("status", "=", "active")]
