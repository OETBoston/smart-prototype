import os
import uuid
from datetime import datetime, timezone

import dotenv
import pytest
from data_utilities.accessor import (
    BigQueryClient,
    DataAccessor,
)
from data_utilities.queries_and_contracts import (
    TEST_TABLE_NAME,
    BaseEntity,
    CurbLineEntityModel,
    CurbLineFilterModel,
    RawSignAssetEntityModel,
    RawSignAssetEntityModelWithAttachments,
    RawSignAssetFilterModel,
    RoadInventoryEntityModel,
    RoadInventoryFilterModel,
    SimpleEntityModel,
    StreetSegmentEntityModel,
    StreetSegmentFilterModel,
)

dotenv.load_dotenv(".env", override=True)

# Pull test vars from .env
TEST_PROJECT_ID = os.environ.get("TEST_GCP_PROJECT_ID")
TEST_DATASET_ID = os.environ.get("TEST_BQ_DATASET_ID")
TEST_TABLE_FQN = f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}.{TEST_TABLE_NAME}"


@pytest.fixture(scope="class")
def data_accessor():
    """Standard integration accessor — real config, real credentials."""
    return DataAccessor()


@pytest.mark.integration
class TestDataAccessorOperations:
    def test_01_insert_via_put(self, data_accessor):
        unique = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        rows = [
            SimpleEntityModel(
                id=f"{unique}-1", type="Sign", time=now, location="POINT(1 1)"
            ),
            SimpleEntityModel(
                id=f"{unique}-2", type="Pole", time=now, location="POINT(2 2)"
            ),
        ]

        inserted = data_accessor.put(rows)
        assert inserted == len(rows)

        select_sql = (
            f"SELECT count(*) AS total FROM `{TEST_TABLE_FQN}` "
            f"WHERE id IN ('{rows[0].id}', '{rows[1].id}')"
        )

        count = data_accessor.get_raw_sql(select_sql)[0]["total"]
        assert count == len(rows)

    def test_02_filter_data(self, data_accessor):
        unique = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        target_id = f"{unique}-B"

        rows = [
            SimpleEntityModel(
                id=f"{unique}-A", type="Sign", time=now, location="POINT(1 1)"
            ),
            SimpleEntityModel(
                id=target_id, type="Pole", time=now, location="POINT(2 2)"
            ),
            SimpleEntityModel(
                id=f"{unique}-C", type="Light", time=now, location="POINT(3 3)"
            ),
        ]
        data_accessor.put(rows)

        filt = SimpleEntityModel.Filter(id=target_id, type="Pole")
        results = data_accessor.get(SimpleEntityModel, filt, limit=10)
        assert len(results) == 1
        assert results[0].id == target_id

    def test_03_time_after(self, data_accessor):
        unique = str(uuid.uuid4())

        split = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

        rows = [
            SimpleEntityModel(
                id=f"{unique}-A",
                type="Old",
                time=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
                location="POINT(1 1)",
            ),
            SimpleEntityModel(
                id=f"{unique}-B",
                type="New",
                time=datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc),
                location="POINT(2 2)",
            ),
        ]
        data_accessor.put(rows)

        filt = SimpleEntityModel.Filter(time_after=split, id_prefix=unique)
        results = data_accessor.get(SimpleEntityModel, filt, limit=10)
        assert len(results) == 1
        assert results[0].id == f"{unique}-B"

    def test_04_time_before(self, data_accessor):
        unique = str(uuid.uuid4())
        split = datetime(2025, 2, 1, 10, 0, tzinfo=timezone.utc)

        rows = [
            SimpleEntityModel(
                id=f"{unique}-C",
                type="Old",
                time=datetime(2025, 2, 1, 9, 0, tzinfo=timezone.utc),
                location="POINT(1 1)",
            ),
            SimpleEntityModel(
                id=f"{unique}-D",
                type="New",
                time=datetime(2025, 2, 1, 11, 0, tzinfo=timezone.utc),
                location="POINT(2 2)",
            ),
        ]
        data_accessor.put(rows)

        filt = SimpleEntityModel.Filter(time_before=split, id_prefix=unique)
        results = data_accessor.get(SimpleEntityModel, filt, limit=10)
        assert len(results) == 1
        assert results[0].id == f"{unique}-C"

    def test_05_limit_one_returns_single_model(self, data_accessor):
        unique = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        target_id = f"{unique}-TARGET"

        rows = [
            SimpleEntityModel(
                id=target_id, type="Target", time=now, location="POINT(1 1)"
            ),
            SimpleEntityModel(
                id=f"{unique}-Extra", type="Extra", time=now, location="POINT(2 2)"
            ),
        ]
        data_accessor.put(rows)

        filt = SimpleEntityModel.Filter(id_prefix=unique)
        result = data_accessor.get(SimpleEntityModel, filt, limit=1)

        # Updated assertions
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], SimpleEntityModel)


@pytest.mark.integration
class TestConfigDrivenInit:
    @pytest.fixture(scope="class")
    def config_data_accessor(self):
        """This path will be loaded by DataAccessor via AppSettings."""
        return DataAccessor(config_path=".env")

    def test_config_put(self, config_data_accessor):
        unique = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        rows = [
            SimpleEntityModel(
                id=f"{unique}-10", type="Test", time=now, location="POINT(1 1)"
            )
        ]
        inserted = config_data_accessor.put(rows)

        assert inserted == 1
        assert isinstance(config_data_accessor.client, BigQueryClient)

    def test_street_segment(self, config_data_accessor):
        results = config_data_accessor.get(
            StreetSegmentEntityModel, StreetSegmentFilterModel(), limit=10
        )
        assert isinstance(results, list)
        assert len(results) > 0
        assert isinstance(results[0], StreetSegmentEntityModel)

    def test_raw_sign(self, config_data_accessor):
        expected_prefix = "Traffic_Sign"
        results = config_data_accessor.get(
            RawSignAssetEntityModel,
            RawSignAssetFilterModel(cartegraph_id_prefix=expected_prefix),
            limit=10,
        )
        assert len(results) > 0
        for row in results:
            assert row.cartegraph_id.startswith(expected_prefix)

    def test_raw_sign_with_attachments(self, config_data_accessor):
        results = config_data_accessor.get(
            RawSignAssetEntityModelWithAttachments, BaseEntity(), limit=10
        )
        assert len(results) > 0
        assert isinstance(results[0], RawSignAssetEntityModelWithAttachments)

    def test_road_inventory_by_route_id(self, config_data_accessor):
        """
        Basic integration test for RoadInventoryEntityModel using
        a known-good sample route_id.
        """
        route_id = "L000620 NB"

        results = config_data_accessor.get(
            RoadInventoryEntityModel,
            RoadInventoryFilterModel(route_id=route_id),
            limit=10,
        )

        assert isinstance(results, list)
        assert len(results) > 0

        for row in results:
            assert isinstance(row, RoadInventoryEntityModel)
            # convention-based equality filter: route_id must match exactly
            assert row.route_id == route_id


@pytest.mark.integration
class TestCurbLineIntegration:
    @pytest.fixture(scope="class")
    def config_data_accessor(self):
        """Load DataAccessor using application config."""
        return DataAccessor(config_path=".env")

    def test_basic_get(self, config_data_accessor):
        """
        Basic retrieval of curb line data. Ensures model hydration works.
        """
        results = config_data_accessor.get(
            CurbLineEntityModel, CurbLineFilterModel(), limit=5
        )

        assert isinstance(results, list)
        assert len(results) > 0
        assert isinstance(results[0], CurbLineEntityModel)

    def test_exact_filter(self, config_data_accessor):
        """
        Test filtering on a curb_id that actually exists in the test dataset.
        """
        # Step 1: get a sample record
        sample_rows = config_data_accessor.get(
            CurbLineEntityModel,
            CurbLineFilterModel(),  # no filters → fetch first rows
            limit=1,
        )

        assert len(sample_rows) > 0, (
            "Test data must contain at least one curb line row."
        )
        known_id = sample_rows[0].curb_id

        # Step 2: run exact-filter test using a real value
        results = config_data_accessor.get(
            CurbLineEntityModel, CurbLineFilterModel(curb_id=known_id), limit=10
        )

        assert isinstance(results, list)
        assert len(results) > 1
        assert all(r.curb_id == known_id for r in results)

    def test_prefix_filter(self, config_data_accessor):
        """
        Ensure prefix search on street_name works.
        """
        prefix = "DORCHESTER"  # example prefix; adjust based on actual data
        results = config_data_accessor.get(
            CurbLineEntityModel,
            CurbLineFilterModel(street_name_prefix=prefix),
            limit=10,
        )

        assert isinstance(results, list)
        assert len(results) > 0

        for row in results:
            assert isinstance(row, CurbLineEntityModel)
            assert row.street_name.upper().startswith(prefix)

    def test_minimal_projection_and_included_fields(self, config_data_accessor):
        """
        Ensures that minimal=True selects only filter columns + included columns.

        Steps:
        1. Fetch a real curb line to get a known curb_id.
        2. Query again with minimal=True and curb_id_included=True.
        3. Verify:
                - curb_id returned (in filter)
                - street_name returned (explicitly included)
                - other fields NOT returned
                - filter still works (exact match)
        """

        # STEP 1: Fetch a known, real curb line using no filters
        sample_rows = config_data_accessor.get(
            CurbLineEntityModel,
            CurbLineFilterModel(),  # No filters → fetch first available
            limit=1,
        )

        assert len(sample_rows) > 0, "Test requires at least one curb line row."

        known = sample_rows[0]
        known_id = known.curb_id
        assert known_id is not None, "Sample record must have curb_id."

        # STEP 2: Query with minimal=True and explicit include
        results = config_data_accessor.get(
            CurbLineEntityModel,
            CurbLineFilterModel(
                curb_id=known_id, minimal=True, street_name_included=True
            ),
            limit=10,
        )

        # Basic checks
        assert len(results) >= 1
        assert all(r.curb_id == known_id for r in results)

        row = results[0]

        # ---- VALIDATION TARGETS ----

        # 1. Filtered column MUST be present
        assert row.curb_id == known_id

        # 2. Included column MUST be present
        assert row.street_name == known.street_name

        # 3. Columns NOT used or included should be None
        #    Example: roadway_id was not filtered or included
        assert row.roadway_id is None

        # 4. Geometry should also be None (not included, not filtered)
        assert row.geometry is None

        # 5. backend correctly executed minimal projection
        #    i.e., no unexpected fields show up with non-null values
        unexpected_fields = {
            "route_id",
            "route_direction",
            "ff_class",
            "buffer_left",
            "buffer_right",
            "curb_length_ft",
            "processed_timestamp",
            "schema_version",
        }

        for f in unexpected_fields:
            assert getattr(row, f) is None, (
                f"Field {f} should not be projected in minimal mode."
            )
