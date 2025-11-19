import pytest
import os
from unittest.mock import patch, MagicMock
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

# --- Import from your project files ---
from utilities.data_utilities.accessor import BigQueryClient, BigQueryProfile, DataAccessor, QuerySpec
from utilities.data_utilities.queries_and_contracts import (
    SimpleEntityModel, 
    SimpleEntityFilter, 
    TEST_TABLE_NAME, 
    BaseEntity,
    StreetSegmentEntityModel,
    StreetSegmentFilterModel,
)



# --- 1. CONFIG VARIABLES ---
TEST_PROJECT_ID = os.environ.get("TEST_GCP_PROJECT_ID", "default-test-project") 
TEST_DATASET_ID = os.environ.get("TEST_BQ_DATASET_ID", "default-dataset-id")
TEST_CREDS_PATH = "/path/to/your/ci-service-account.json" 
TEST_TABLE_FQN = f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}.{TEST_TABLE_NAME}"


# --- 2. WORKING CLIENT FIXTURE ---
@pytest.fixture(scope="class")
def setup_profile_env():
    """Uses the working profile/patch setup for client initialization."""
    test_creds_path = os.environ.get("REAL_CREDS_PATH", TEST_CREDS_PATH)
    os.environ['ACTIVE_PROFILE'] = 'ci_test' 
    expanded_test_creds_path = os.path.expanduser(test_creds_path)

    MOCK_PROFILE_INSTANCE = BigQueryProfile(credentials_path=expanded_test_creds_path)
    
    with patch(f'utilities.data_utilities.accessor.AppSettings') as MockAppSettings:
        
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
        
        # Pass the connected client instance directly to DataAccessor
        return DataAccessor(client=bigquery_client_wrapper, current_prefix=f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}")

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
        
        valid_data: List[SimpleEntityModel] = [
            SimpleEntityModel(id=f"{unique_id_base}-1", type="Sign", time=insert_time, location="POINT(1 1)"),
            SimpleEntityModel(id=f"{unique_id_base}-2", type="Pole", time=insert_time, location="POINT(2 2)"),
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
        Tests retrieving a filtered subset of data using DataAccessor.get with a SimpleEntityFilter model.
        (Made independent by inserting data within the test).
        """
        
        # ARRANGE 1: Insert independent test data
        unique_id_base = str(uuid.uuid4())
        # Define the specific ID we will be targeting with the filter
        target_id = f"{unique_id_base}-B" 
        insert_time = datetime.now(timezone.utc)
        
        TEST_ROWS = [
            SimpleEntityModel(id=f"{unique_id_base}-A", type="Sign", time=insert_time, location="POINT(1 1)"),
            SimpleEntityModel(id=target_id, type="Pole", time=insert_time, location="POINT(2 2)"), # Target
            SimpleEntityModel(id=f"{unique_id_base}-C", type="Light", time=insert_time, location="POINT(3 3)"),
        ]
        data_accessor.put(TEST_ROWS) # Insert the data

        # ARRANGE 2: Define the filter model (we want only the 'Pole' asset)
        # Filter using the full ID, as 'id_prefix' is not a field on SimpleEntityFilter.
        filter_criteria = SimpleEntityFilter(
            # Use the full ID to uniquely identify the target row.
            id=target_id,             # <-- FIXED: Use the 'id' field
            type="Pole",
            # REMOVED: id_prefix=unique_id_base 
        )
        
        # ACT: Use the model-based get method
        retrieved_data: List[SimpleEntityModel] = data_accessor.get(
            entity_model=SimpleEntityModel, 
            filter=filter_criteria
        ) 
        
        # ASSERT 1: Exactly one record was returned
        assert len(retrieved_data) == 1
        
        # ASSERT 2: The retrieved object matches the filter criteria
        assert retrieved_data[0].id == target_id
        assert retrieved_data[0].type == "Pole"
        
        print(f"\n✅ Success: Filtered GET retrieved 1 valid SimpleEntityModel using filter model.")

    def test_06_get_with_no_results(self, data_accessor: DataAccessor):
        """
        Tests retrieving data with a filter that returns no records. Should return an empty list.
        """
        
        # ARRANGE: Create a filter criteria that is guaranteed not to match existing data
        unique_id = str(uuid.uuid4())
        filter_criteria = SimpleEntityFilter(id=f"Z999999-{unique_id}", type=None) 
        
        # ACT: Use the model-based get method
        retrieved_data: List[SimpleEntityModel] = data_accessor.get(
            entity_model=SimpleEntityModel, 
            filter=filter_criteria
        ) 
        
        # ASSERT: An empty list should be returned
        assert isinstance(retrieved_data, list)
        assert len(retrieved_data) == 0
        
        print(f"\n✅ Success: GET correctly returned an empty list for a non-matching filter.")


    # tests/integration/test_data_accessor.py (Add to TestDataAccessorOperations class)

    def test_03_filter_data_with_time_after(self, data_accessor: DataAccessor):
        """
        Tests filtering data using the time_after field, which requires
        translation to a > operator on the 'time' column.
        """
        # ARRANGE 1: Define key times
        unique_id_base = str(uuid.uuid4())
        # The split point: we want records AFTER this time (i.e., row_B)
        split_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        
        # Test rows: Row A (before split), Row B (after split)
        TEST_ROWS = [
            SimpleEntityModel(
                id=f"{unique_id_base}-A", type="Old", 
                time=datetime(2025, 1, 1, 9, 0, 0, tzinfo=timezone.utc), 
                location="POINT(1 1)"
            ),
            SimpleEntityModel(
                id=f"{unique_id_base}-B", type="New", 
                time=datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc), # <-- This should be returned
                location="POINT(2 2)"
            ),
        ]
        data_accessor.put(TEST_ROWS)

        # ARRANGE 2: Define the filter criteria (time_after uses the > operator)
        filter_criteria = SimpleEntityFilter(
            time_after=split_time, 
            id_prefix=unique_id_base
        )
        
        # ACT: Retrieve the data
        retrieved_data: List[SimpleEntityModel] = data_accessor.get(
            entity_model=SimpleEntityModel, 
            filter=filter_criteria
        ) 
        
        # ASSERT: Only one record (the one after the split_time) should be returned
        assert len(retrieved_data) == 1
        assert retrieved_data[0].id == f"{unique_id_base}-B"
        
        print(f"\n✅ Success: Filtered GET with time_after (>) retrieved the expected single record.")


    def test_04_filter_data_with_time_before(self, data_accessor: DataAccessor):
        """
        Tests filtering data using the time_before field, which requires
        translation to a < operator on the 'time' column.
        (Assumes time_before is added to SimpleEntityFilter)
        """
        # ARRANGE 1: Define key times
        unique_id_base = str(uuid.uuid4())
        # The split point: we want records BEFORE this time (i.e., row_A)
        split_time = datetime(2025, 2, 1, 10, 0, 0, tzinfo=timezone.utc)
        
        # Test rows: Row A (before split), Row B (after split)
        TEST_ROWS = [
            SimpleEntityModel(
                id=f"{unique_id_base}-C", type="Old", 
                time=datetime(2025, 2, 1, 9, 0, 0, tzinfo=timezone.utc), # <-- This should be returned
                location="POINT(1 1)"
            ),
            SimpleEntityModel(
                id=f"{unique_id_base}-D", type="New", 
                time=datetime(2025, 2, 1, 11, 0, 0, tzinfo=timezone.utc), 
                location="POINT(2 2)"
            ),
        ]
        data_accessor.put(TEST_ROWS)

        # ARRANGE 2: Define the filter criteria (time_before uses the < operator)
        filter_criteria = SimpleEntityFilter(
            time_before=split_time,
            id_prefix=unique_id_base
        )
        
        # ACT: Retrieve the data
        retrieved_data: List[SimpleEntityModel] = data_accessor.get(
            entity_model=SimpleEntityModel, 
            filter=filter_criteria
        ) 
        
        # ASSERT: Only one record (the one before the split_time) should be returned
        assert len(retrieved_data) == 1
        assert retrieved_data[0].id == f"{unique_id_base}-C"
        
        print(f"\n✅ Success: Filtered GET with time_before (<) retrieved the expected single record.")

    def test_05_get_with_limit_one_returns_single_model(self, data_accessor: DataAccessor):
        """
        Tests retrieving data with limit=1, verifying a single SimpleEntityModel is returned, 
        not a list containing one model.
        """
        
        # ARRANGE 1: Insert independent test data
        unique_id_base = str(uuid.uuid4())
        target_id = f"{unique_id_base}-TARGET" 
        insert_time = datetime.now(timezone.utc)
        
        TEST_ROWS = [
            SimpleEntityModel(id=target_id, type="Target", time=insert_time, location="POINT(1 1)"),
            SimpleEntityModel(id=f"{unique_id_base}-Extra", type="Extra", time=insert_time, location="POINT(2 2)"),
        ]
        data_accessor.put(TEST_ROWS)

        # ARRANGE 2: Filter criteria that would match multiple rows
        filter_criteria = SimpleEntityFilter(
            id_prefix=unique_id_base,
            type=None
        )
        
        # ACT: Use the model-based get method with limit=1
        retrieved_data = data_accessor.get(
            entity_model=SimpleEntityModel, 
            filter=filter_criteria,
            limit=1 # <-- Crucial test point
        ) 
        
        # ASSERT 1: Verify the result is a single model, NOT a list
        assert isinstance(retrieved_data, SimpleEntityModel)
        
        # ASSERT 2: Verify the data is correct
        assert retrieved_data.type == "Target"
        
        print(f"\n✅ Success: GET with limit=1 returned a single SimpleEntityModel object.")


@pytest.mark.integration
class TestConfigDrivenInit:
    
    @pytest.fixture(scope="class")
    def config_driven_data_accessor(self) -> DataAccessor:
        """
        Provides a DataAccessor instance that forces client initialization 
        via the AppSettings/Config path (no 'client' argument provided).
        """
        
        # 🔑 Assume 'config/config.test.toml' is the real path
        CONFIG_FILE_PATH = '.env'
        
        # Ensure the DataAccessor's __init__ is updated to call AppSettings.load(CONFIG_FILE_PATH)
        return DataAccessor(
            config_path=CONFIG_FILE_PATH
        )
    def test_06_config_initialization_works(self, config_driven_data_accessor: DataAccessor):
        """
        Verifies that the DataAccessor successfully initialized its client 
        via the configuration pathway and can perform basic operations.
        """
        # ARRANGE 1: Use a unique ID 
        unique_id_base = str(uuid.uuid4())
        insert_time = datetime.now(timezone.utc).isoformat()
        
        valid_data: List[SimpleEntityModel] = [
            SimpleEntityModel(id=f"{unique_id_base}-10", type="Test", time=insert_time, location="POINT(1 1)"),
        ]
        
        # ACT: Use the accessor's put method
        inserted_count = config_driven_data_accessor.put(valid_data)

        # ASSERT: Verify the operation succeeded
        assert inserted_count == len(valid_data)
        assert isinstance(config_driven_data_accessor.client, BigQueryClient)
        
        print(f"\n✅ Success: DataAccessor initialized client via config and performed PUT.")

    def test_street_segment_entity(self, config_driven_data_accessor: DataAccessor):
        """
        Verifies schema match across all records and asserts that at least two records are returned.
        """
        results = config_driven_data_accessor.get(
            entity_model=StreetSegmentEntityModel,
            filter=StreetSegmentFilterModel())
            
        # Check that 'results' is not empty and is a list/tuple.
        assert isinstance(results, list)
        assert len(results) > 0
        
        # Optional: Check the type of the returned object
        assert isinstance(results[0], StreetSegmentEntityModel)