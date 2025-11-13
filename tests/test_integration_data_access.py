import pytest
import os
from unittest.mock import patch, MagicMock
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

# --- Import from your project files ---
from utilities.data.accessor import BigQueryClient, BigQueryProfile, DataAccessor, QuerySpec
from utilities.data.queries_and_contracts import (
    TestEntityModel, 
    TestEntityFilter, 
    TEST_TABLE_NAME, 
    BaseEntity 
)


# --- 1. CONFIG VARIABLES ---
TEST_PROJECT_ID = os.environ.get("TEST_GCP_PROJECT_ID", "default-test-project") 
TEST_DATASET_ID = os.environ.get("TEST_BQ_DATASET_ID", "default-dataset-id")
TEST_CREDS_PATH = "/path/to/your/ci-service-account.json" 
TEST_TABLE_FQN = f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}.{TEST_TABLE_NAME}"


# --- 2. WORKING CLIENT FIXTURE ---
@pytest.fixture(scope="module")
def setup_profile_env():
    """Uses the working profile/patch setup for client initialization."""
    test_creds_path = os.environ.get("REAL_CREDS_PATH", TEST_CREDS_PATH)
    os.environ['ACTIVE_PROFILE'] = 'ci_test' 
    expanded_test_creds_path = os.path.expanduser(test_creds_path)

    MOCK_PROFILE_INSTANCE = BigQueryProfile(credentials_path=expanded_test_creds_path)
    
    with patch(f'utilities.data.accessor.AppSettings') as MockAppSettings:
        
        mock_settings = MagicMock(
            active_profile='ci_test',
            bigquery_profiles={'ci_test': MOCK_PROFILE_INSTANCE} 
        )
        MockAppSettings.return_value = mock_settings
        yield 

    os.environ.pop('ACTIVE_PROFILE', None)


# --- 3. REVISED TEST SUITE ---
@pytest.mark.integration
@pytest.mark.usefixtures("setup_profile_env")
class TestDataAccessorOperations:

    @pytest.fixture(scope="class")
    def bigquery_client_wrapper(self) -> BigQueryClient:
        """Provides the initialized BigQueryClient wrapper."""
        return BigQueryClient.initialize()

    @pytest.fixture(scope="class")
    def data_accessor(self, bigquery_client_wrapper: BigQueryClient) -> DataAccessor:
        """
        Provides an initialized DataAccessor instance using the connected BigQueryClient.
        """
        table_prefix_map = {
            TestEntityModel: f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}"
        }
        
        # Pass the connected client instance directly to DataAccessor
        return DataAccessor(client=bigquery_client_wrapper, table_prefix_map=table_prefix_map)

    # --- REMOVED: setup_and_cleanup_write_table fixture ---

    # --- ACCEPTANCE TESTS (SUCCESS PATHS) ---

    def test_01_insert_valid_data_via_put(self, data_accessor: DataAccessor):
        """
        Tests inserting valid data using DataAccessor.put and verifies insertion 
        using unique IDs to avoid dependency on cleanup.
        """
        
        # ARRANGE 1: Use a unique ID to ensure we only check the inserted rows
        unique_id_base = str(uuid.uuid4())
        insert_time = datetime.now(timezone.utc).isoformat()
        
        valid_data: List[TestEntityModel] = [
            TestEntityModel(id=f"{unique_id_base}-1", type="Sign", time=insert_time, location="POINT(1 1)"),
            TestEntityModel(id=f"{unique_id_base}-2", type="Pole", time=insert_time, location="POINT(2 2)"),
        ]
        
        # ACT 1: Use the accessor's put method
        inserted_count = data_accessor.put(valid_data)

        # ASSERT 1: Verify the expected number of rows were reported as inserted
        assert inserted_count == len(valid_data)
        
        # ARRANGE 2 & ACT 2: Check the actual row count in BigQuery for the specific IDs
        id_list = [f"'{row.id}'" for row in valid_data]
        count_sql = f"SELECT count(*) as total FROM `{TEST_TABLE_FQN}` WHERE id IN ({', '.join(id_list)})"
        
        # Use get_raw_sql to verify database state (returns List[Dict])
        count_result = data_accessor.get_raw_sql(count_sql) 
        actual_count = count_result[0]['total']

        # ASSERT 2: Verify the count matches the inserted amount
        assert actual_count == len(valid_data)
        
        print(f"\n✅ Success: DataAccessor.put inserted and verified {actual_count} rows via unique ID.")
        
    def test_02_filter_data_via_model_get(self, data_accessor: DataAccessor):
        """
        Tests retrieving a filtered subset of data using DataAccessor.get with a TestEntityFilter model.
        (Made independent by inserting data within the test).
        """
        
        # ARRANGE 1: Insert independent test data
        unique_id_base = str(uuid.uuid4())
        # Define the specific ID we will be targeting with the filter
        target_id = f"{unique_id_base}-B" 
        insert_time = datetime.now(timezone.utc)
        
        TEST_ROWS = [
            TestEntityModel(id=f"{unique_id_base}-A", type="Sign", time=insert_time, location="POINT(1 1)"),
            TestEntityModel(id=target_id, type="Pole", time=insert_time, location="POINT(2 2)"), # Target
            TestEntityModel(id=f"{unique_id_base}-C", type="Light", time=insert_time, location="POINT(3 3)"),
        ]
        data_accessor.put(TEST_ROWS) # Insert the data

        # ARRANGE 2: Define the filter model (we want only the 'Pole' asset)
        # Filter using the full ID, as 'id_prefix' is not a field on TestEntityFilter.
        filter_criteria = TestEntityFilter(
            # Use the full ID to uniquely identify the target row.
            id=target_id,             # <-- FIXED: Use the 'id' field
            type="Pole",
            # REMOVED: id_prefix=unique_id_base 
        )
        
        # ACT: Use the model-based get method
        retrieved_data: List[TestEntityModel] = data_accessor.get(
            entity_model=TestEntityModel, 
            filter=filter_criteria
        ) 
        
        # ASSERT 1: Exactly one record was returned
        assert len(retrieved_data) == 1
        
        # ASSERT 2: The retrieved object matches the filter criteria
        assert retrieved_data[0].id == target_id
        assert retrieved_data[0].type == "Pole"
        
        print(f"\n✅ Success: Filtered GET retrieved 1 valid TestEntityModel using filter model.")

    def test_06_get_with_no_results(self, data_accessor: DataAccessor):
        """
        Tests retrieving data with a filter that returns no records. Should return an empty list.
        """
        
        # ARRANGE: Create a filter criteria that is guaranteed not to match existing data
        unique_id = str(uuid.uuid4())
        filter_criteria = TestEntityFilter(id=f"Z999999-{unique_id}", type=None) 
        
        # ACT: Use the model-based get method
        retrieved_data: List[TestEntityModel] = data_accessor.get(
            entity_model=TestEntityModel, 
            filter=filter_criteria
        ) 
        
        # ASSERT: An empty list should be returned
        assert isinstance(retrieved_data, list)
        assert len(retrieved_data) == 0
        
        print(f"\n✅ Success: GET correctly returned an empty list for a non-matching filter.")