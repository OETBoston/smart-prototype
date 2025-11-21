import pytest
import os
import uuid
from datetime import datetime, timezone
import geopandas as gpd

from utilities.data_utilities.accessor import DataAccessor, BigQueryClient, QuerySpec
from utilities.data_utilities.queries_and_contracts import (
    BaseEntity,
    SimpleEntityModel, 
    SimpleEntityFilter, 
    TEST_TABLE_NAME, 
    StreetSegmentEntityModel,
    StreetSegmentFilterModel,
    RawSignAssetEntityModel,
    RawSignAssetEntityModelWithAttachments,
    RawSignAssetFilterModel,
    RoadInventoryEntityModel,
    RoadInventoryFilterModel
)

import dotenv
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
            SimpleEntityModel(id=f"{unique}-1", type="Sign", time=now, location="POINT(1 1)"),
            SimpleEntityModel(id=f"{unique}-2", type="Pole", time=now, location="POINT(2 2)"),
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
            SimpleEntityModel(id=f"{unique}-A", type="Sign", time=now, location="POINT(1 1)"),
            SimpleEntityModel(id=target_id, type="Pole", time=now, location="POINT(2 2)"),
            SimpleEntityModel(id=f"{unique}-C", type="Light", time=now, location="POINT(3 3)"),
        ]
        data_accessor.put(rows)

        filt = SimpleEntityFilter(id=target_id, type="Pole")
        results = data_accessor.get(SimpleEntityModel, filt)
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
                location="POINT(1 1)"
            ),
            SimpleEntityModel(
                id=f"{unique}-B",
                type="New",
                time=datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc),
                location="POINT(2 2)"
            ),
        ]
        data_accessor.put(rows)

        filt = SimpleEntityFilter(time_after=split, id_prefix=unique)
        results = data_accessor.get(SimpleEntityModel, filt)
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
                location="POINT(1 1)"
            ),
            SimpleEntityModel(
                id=f"{unique}-D",
                type="New",
                time=datetime(2025, 2, 1, 11, 0, tzinfo=timezone.utc),
                location="POINT(2 2)"
            ),
        ]
        data_accessor.put(rows)

        filt = SimpleEntityFilter(time_before=split, id_prefix=unique)
        results = data_accessor.get(SimpleEntityModel, filt)
        assert len(results) == 1
        assert results[0].id == f"{unique}-C"

    def test_05_limit_one_returns_single_model(self, data_accessor):
        unique = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        target_id = f"{unique}-TARGET"

        rows = [
            SimpleEntityModel(id=target_id, type="Target", time=now, location="POINT(1 1)"),
            SimpleEntityModel(id=f"{unique}-Extra", type="Extra", time=now, location="POINT(2 2)"),
        ]
        data_accessor.put(rows)

        filt = SimpleEntityFilter(id_prefix=unique)
        result = data_accessor.get(SimpleEntityModel, filt, limit=1)

        assert isinstance(result, SimpleEntityModel)
        assert result.id == target_id


@pytest.mark.integration
class TestConfigDrivenInit:

    @pytest.fixture(scope="class")
    def config_data_accessor(self):
        """This path will be loaded by DataAccessor via AppSettings."""
        return DataAccessor(config_path=".env")

    def test_config_put(self, config_data_accessor):
        unique = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        rows = [SimpleEntityModel(id=f"{unique}-10", type="Test", time=now, location="POINT(1 1)")]
        inserted = config_data_accessor.put(rows)

        assert inserted == 1
        assert isinstance(config_data_accessor.client, BigQueryClient)

    def test_street_segment(self, config_data_accessor):
        results = config_data_accessor.get(
            StreetSegmentEntityModel,
            StreetSegmentFilterModel()
        )
        assert isinstance(results, list)
        assert len(results) > 0
        assert isinstance(results[0], StreetSegmentEntityModel)

    def test_raw_sign(self, config_data_accessor):
        expected_prefix = "Traffic_Sign"
        results = config_data_accessor.get(
            RawSignAssetEntityModel,
            RawSignAssetFilterModel(cartegraph_id_prefix=expected_prefix)
        )
        assert len(results) > 0
        for row in results:
            assert row.cartegraph_id.startswith(expected_prefix)

    def test_raw_sign_with_attachments(self, config_data_accessor):
        results = config_data_accessor.get(
            RawSignAssetEntityModelWithAttachments,
            BaseEntity()
        )
        assert len(results) > 0
        assert isinstance(results[0], RawSignAssetEntityModelWithAttachments)

    def test_geo_dataframe(self, config_data_accessor):
        gdf = config_data_accessor.get_as_geo_data_frame(
            StreetSegmentEntityModel,
            StreetSegmentFilterModel(),
            limit=10,
            ignore_bad_geometry=True
        )
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) > 0
        assert gdf.crs.to_epsg() == 4326





    def test_road_inventory_by_route_id(self, config_data_accessor):
        """
        Basic integration test for RoadInventoryEntityModel using
        a known-good sample route_id.
        """
        route_id = "L000620 NB"

        results = config_data_accessor.get(
            RoadInventoryEntityModel,
            RoadInventoryFilterModel(route_id=route_id)
        )

        assert isinstance(results, list)
        assert len(results) > 0

        for row in results:
            assert isinstance(row, RoadInventoryEntityModel)
            # convention-based equality filter: route_id must match exactly
            assert row.route_id == route_id

    def test_road_inventory_geo_dataframe(self, config_data_accessor):
        """
        Ensure we can hydrate a GeoDataFrame for road inventory,
        with a valid CRS and geometry column.
        """
        route_id = "L000620 NB"

        gdf = config_data_accessor.get_as_geo_data_frame(
            RoadInventoryEntityModel,
            RoadInventoryFilterModel(route_id=route_id),
            limit=50,
        )

        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) > 0

        # Should be WGS84
        assert gdf.crs is not None
        assert gdf.crs.to_epsg() == 4326

        # Ensure geometry column is present and has non-null values
        assert "geometry" in gdf.columns
        assert gdf["geometry"].notnull().any()