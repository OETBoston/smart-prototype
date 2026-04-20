import os
import uuid
from datetime import datetime, timezone

import dotenv
import pytest
from curb_utils.data_utils.accessor import BigQueryClient, QuerySpec
from curb_utils.data_utils.queries_and_contracts import (
    TEST_TABLE_NAME,
    SimpleEntityModel,
)

dotenv.load_dotenv(".env", override=True)


# Read test-related vars from .env (or fall back)
TEST_PROJECT_ID = os.environ.get("TEST_GCP_PROJECT_ID")
TEST_DATASET_ID = os.environ.get("TEST_BQ_DATASET_ID")
TEST_TABLE_ID = os.environ.get("TEST_BQ_TABLE_ID")


@pytest.mark.integration
class TestBigQueryClientEnvConfig:
    def test_01_client_initializes(self):
        """Ensure BigQueryClient.initialize() works w/ env-based config."""
        client_wrapper = BigQueryClient.initialize()
        assert client_wrapper.client is not None

    def test_02_info_schema_query(self):
        """Simple INFORMATION_SCHEMA query using configured project/dataset."""
        client_wrapper = BigQueryClient.initialize()

        sql = f"""
        SELECT table_name
        FROM `{TEST_PROJECT_ID}.{TEST_DATASET_ID}.INFORMATION_SCHEMA.TABLES`
        LIMIT 1
        """

        results = client_wrapper.raw_sql(sql)
        assert isinstance(results, list)

    def test_03_limit_3_results(self):
        """Test query returning exactly 3 rows."""
        client_wrapper = BigQueryClient.initialize()

        table_fqn = f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}.{TEST_TABLE_ID}"
        sql = f"SELECT * FROM `{table_fqn}` LIMIT 3"

        results = client_wrapper.raw_sql(sql)
        assert isinstance(results, list)
        assert len(results) == 3

    def test_04_streaming_insert_and_verify(self):
        """Streaming insert → immediate SELECT verification."""
        client_wrapper = BigQueryClient.initialize()

        base_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        rows = [
            SimpleEntityModel(
                id=f"{base_id}-1",
                type="test_insert",
                time=now,
                location="POINT(-100 40)",
            ),
            SimpleEntityModel(
                id=f"{base_id}-2", type="test_insert", time=now, location="POINT(2 48)"
            ),
        ]

        table_fqn = f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}.{TEST_TABLE_NAME}"

        insert_spec = QuerySpec(operation="INSERT", table=table_fqn, payload=rows)

        # Insert
        affected = client_wrapper.execute_query(insert_spec)
        assert affected == len(rows)

        # Verify via immediate SELECT
        ids = ",".join([f"'{r.id}'" for r in rows])
        select_sql = f"SELECT id FROM `{table_fqn}` WHERE id IN ({ids})"

        retrieved = client_wrapper.raw_sql(select_sql)
        assert len(retrieved) == len(rows)
