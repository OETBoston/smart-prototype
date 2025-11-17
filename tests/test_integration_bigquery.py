import pytest
import os
from unittest.mock import patch, MagicMock
import uuid
from datetime import datetime, timezone
from utilities.data_utilities.accessor import BigQueryClient, BigQueryProfile, QuerySpec
from utilities.data_utilities.queries_and_contracts import (
    SimpleEntityModel, 
    SimpleEntityFilter, 
    TEST_TABLE_NAME, 
    BaseEntity
)
import time


# Set a known dataset in the project linked to your service account credentials file
TEST_PROJECT_ID = os.environ.get("TEST_GCP_PROJECT_ID", "default-test-project") 
TEST_DATASET_ID = os.environ.get("TEST_BQ_DATASET_ID", "default-dataset-id")
TEST_TABLE_ID = os.environ.get("TEST_BQ_TABLE_ID", "default-table-id")
TEST_CREDS_PATH = "/path/to/your/ci-service-account.json"

@pytest.fixture(scope="module")
def setup_profile_env():
    
    test_creds_path = os.environ.get("REAL_CREDS_PATH", TEST_CREDS_PATH)
    os.environ['ACTIVE_PROFILE'] = 'ci_test' 
    expanded_test_creds_path = os.path.expanduser(test_creds_path)

    # --- 1. DEFINE THE PROFILE WITH DATASET ---
    MOCK_PROFILE_INSTANCE = BigQueryProfile(credentials_path=expanded_test_creds_path)
    
    # --- 2. Patch Pydantic to return the profile data when run. ---
    with patch(f'utilities.data_utilities.accessor.AppSettings') as MockAppSettings:
        
        mock_profile_dict = {'ci_test': MOCK_PROFILE_INSTANCE}

        mock_settings = MagicMock(
            active_profile='ci_test',
            bigquery_profiles=mock_profile_dict 
        )
        MockAppSettings.return_value = mock_settings
        
        # The tests run here, while the patch is active
        yield # <-- MOVE YIELD HERE

    # --- 3. Clean up the environment variable after the tests finish ---
    os.environ.pop('ACTIVE_PROFILE', None)
    
    
@pytest.mark.integration
@pytest.mark.usefixtures("setup_profile_env")
class TestBigQueryClientEnvConfig:

    def test_03_init_uses_env_and_profile(self):
        """
        Integration test to ensure BigQueryClient.initialize uses the
        ACTIVE_PROFILE and successfully connects using the specified path.
        """
        
        # ACT 1: Initialize the client (it should use the injected profile)
        client_wrapper = BigQueryClient.initialize()

        # ASSERT 1: Check the internal state of the wrapper
        assert client_wrapper.project_id == TEST_PROJECT_ID
        # You could also assert the underlying client has the default_dataset set
        # assert client_wrapper.client.default_dataset == TEST_DATASET_ID
        
        # ARRANGE: SQL to query BigQuery's information schema.
        # Use a non-fully-qualified table name to test the default_dataset setting.
        sql_query = f"""
        SELECT 
            table_name
        FROM 
            `{TEST_DATASET_ID}`.INFORMATION_SCHEMA.TABLES
        LIMIT 1
        """

        # ACT 2: Execute the query
        results = client_wrapper.raw_sql(sql_query)

        # ASSERT 2: Check for successful query execution (0-N tables)
        assert isinstance(results, list)
        assert len(results) >= 0 
        
        print(f"\n✅ Success: Initialized via ENV/Profile and connected to {TEST_PROJECT_ID}/{TEST_DATASET_ID}.")

    def test_04_select_limit_3_results(self):
        """
        Integration test to select 3 rows from a public table and verify the count.
        """
        
        # ARRANGE 1: Initialize the client
        client_wrapper = BigQueryClient.initialize()

        # ARRANGE 2: SQL to query a well-known public dataset table and limit the results to 3
        LOCAL_TABLE = f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}.{TEST_TABLE_ID}"
        sql_query = f"""
        SELECT 
            *
        FROM 
            `{LOCAL_TABLE}`
        LIMIT 3
        """

        # ACT: Execute the query
        results = client_wrapper.raw_sql(sql_query)

        # ASSERT: Check for successful query execution and that exactly 3 results were returned
        assert isinstance(results, list)
        assert len(results) == 3
        print(f"\n✅ Success: Fetched exactly 3 results from {TEST_TABLE_ID}.")

    def test_05_streaming_insert(self):
            """
            Integration test to insert rows using the streaming API and verify immediate 
            availability via SELECT, skipping cleanup.
            """
            # ARRANGE 1: Initialize the client
            client_wrapper = BigQueryClient.initialize()
            
            # ARRANGE 2: Define unique rows to insert based on SimpleEntityModel schema
            unique_id_base = str(uuid.uuid4())
            insert_time = datetime.now(timezone.utc)

            # Define the GEOGRAPHY data as WKT string
            US_LOCATION_WKT = "POINT(-100 40)" 
            EU_LOCATION_WKT = "POINT(2 48)" 

            ROWS_TO_INSERT = [
                SimpleEntityModel(
                    id=f"{unique_id_base}-1",
                    type="test_insert",
                    time=insert_time,
                    location=US_LOCATION_WKT 
                ),
                SimpleEntityModel(
                    id=f"{unique_id_base}-2",
                    type="test_insert",
                    time=insert_time,
                    location=EU_LOCATION_WKT
                ),
            ]

            test_insert_table = TEST_TABLE_NAME
            TABLE_FQN = f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}.{test_insert_table}"
            
            # ARRANGE 3: Create the QuerySpec object
            insert_spec = QuerySpec(
                operation='INSERT',
                table=TABLE_FQN,
                payload=ROWS_TO_INSERT 
            )

            # ACT 1: Execute the insert operation
            affected_rows = client_wrapper.execute_query(insert_spec)

            # ASSERT 1: Verify the correct number of rows were reported as inserted
            assert affected_rows == len(ROWS_TO_INSERT)
            print(f"\n✅ Success: Reported {affected_rows} rows inserted into {test_insert_table}.")
            
            # --- NEW VERIFICATION STEP ---
            
            # ARRANGE 4: Build SELECT query to retrieve the inserted rows by ID
            id_list = [f"'{row.id}'" for row in ROWS_TO_INSERT]
            select_sql = f"SELECT id FROM `{TABLE_FQN}` WHERE id IN ({', '.join(id_list)})"
            
            # ACT 2: Execute the SELECT query
            # We expect this to work immediately because SELECT queries include streaming buffer data.
            retrieved_rows = client_wrapper.raw_sql(select_sql)
            
            # ASSERT 2: Verify all inserted rows were retrieved immediately
            assert len(retrieved_rows) == len(ROWS_TO_INSERT)
            print(f"✅ Verification: Successfully retrieved {len(retrieved_rows)} rows immediately after streaming.")

            # --- OLD CLEANUP REMOVED ---
            # NOTE: Cleanup is skipped as requested. Data will persist.