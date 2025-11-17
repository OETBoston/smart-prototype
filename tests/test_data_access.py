from utilities.data_utilities.accessor import DataAccessor, DataClient, QuerySpec
from typing import Any

# --- New Mock Implementation ---

class MockDataClient:
    """
    A mock that implements the DataClient protocol (execute_query and raw_sql).
    It returns the received QuerySpec object for verification.
    """
    def execute_query(self, query_spec: QuerySpec) -> Any:
        # The mock returns the received QuerySpec object
        return {"result": "success", "received_spec": query_spec}

    def raw_sql(self, sql_query: str) -> Any:
        # Implementation for raw_sql is not needed for this test
        pass

# --- Test ---

def test_fetch_users_constructs_correct_query_spec():
    """
    Tests that DataAccessor correctly creates and passes the QuerySpec 
    object, including all its parameters, to the client.
    """
    # ARRANGE
    expected_limit = 20
    mock_client = MockDataClient()
    # The accessor is initialized with the mock client
    accessor = DataAccessor(client=mock_client)
    
    # ACT
    result = accessor.fetch_users(limit=expected_limit)
    
    # ASSERT
    # 1. Check if a QuerySpec object was received
    assert "received_spec" in result
    received_spec = result["received_spec"]
    assert isinstance(received_spec, QuerySpec)
    assert result["result"] == "success"
    
    # 2. Verify the contents of the received QuerySpec object
    assert received_spec.table == "users"
    assert received_spec.limit == expected_limit
    assert received_spec.columns == ["user_id", "email", "status"]
    assert received_spec.filters == [("status", "=", "active")]