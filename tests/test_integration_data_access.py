import pytest
import os
import uuid
from datetime import datetime, timezone
import geopandas as gpd
import pandas as pd
from typing import Optional, Protocol, List, Dict, Any, Type, Union, Tuple, Literal, Callable, Sequence

from utilities.data_utilities.accessor import (
    DataAccessor, BigQueryClient, QuerySpec, 
    data_frame_to_geo_data_frame, entities_to_data_frame,
    geo_data_frame_to_data_frame, data_frame_to_entities)
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
    RoadInventoryFilterModel,
    CurbLineEntityModel,
    CurbLineFilterModel,
)
from shapely import wkt, geometry as shapely_geom
from shapely.geometry.base import BaseGeometry
from shapely.geometry import shape, LineString
from shapely.wkt import loads

import dotenv
dotenv.load_dotenv(".env", override=True)

# Pull test vars from .env
TEST_PROJECT_ID = os.environ.get("TEST_GCP_PROJECT_ID")
TEST_DATASET_ID = os.environ.get("TEST_BQ_DATASET_ID")
TEST_TABLE_FQN = f"{TEST_PROJECT_ID}.{TEST_DATASET_ID}.{TEST_TABLE_NAME}"







TOLERANCE_M = 0.025

def check_geometry_similarity(
    list_a: List[StreetSegmentEntityModel], 
    list_b: List[StreetSegmentEntityModel]
) -> List[tuple]:
    
    matches = []
    
    # 1. Convert List B to Shapely objects for faster lookup
    shapely_b = [(obj.segment_id, loads(obj.geom)) for obj in list_b if obj.geom]

    # 2. Iterate through List A and find the best match in List B
    for obj_a in list_a:
        if not obj_a.geom:
            continue
            
        geom_a = loads(obj_a.geom)
        best_match_id = None
        min_hausdorff_dist = float('inf')
        
        for id_b, geom_b in shapely_b:
            # Calculate distance
            dist = geom_a.hausdorff_distance(geom_b)
            
            if dist < min_hausdorff_dist:
                min_hausdorff_dist = dist
                best_match_id = id_b
        
        # 3. Check against tolerance
        is_match = (min_hausdorff_dist < TOLERANCE_M)
        
        matches.append({
            "segment_a_id": obj_a.segment_id,
            "segment_b_id": best_match_id,
            "hausdorff_distance": min_hausdorff_dist,
            "is_within_tolerance": is_match
        })
        
    return matches

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
        results = data_accessor.get(SimpleEntityModel, filt,
            limit=10)
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
        results = data_accessor.get(SimpleEntityModel, filt,
            limit=10)
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
        results = data_accessor.get(SimpleEntityModel, filt,
            limit=10)
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
            StreetSegmentFilterModel(),
            limit=10
        )
        assert isinstance(results, list)
        assert len(results) > 0
        assert isinstance(results[0], StreetSegmentEntityModel)

    def test_raw_sign(self, config_data_accessor):
        expected_prefix = "Traffic_Sign"
        results = config_data_accessor.get(
            RawSignAssetEntityModel,
            RawSignAssetFilterModel(cartegraph_id_prefix=expected_prefix),
            limit=10
        )
        assert len(results) > 0
        for row in results:
            assert row.cartegraph_id.startswith(expected_prefix)

    def test_raw_sign_with_attachments(self, config_data_accessor):
        results = config_data_accessor.get(
            RawSignAssetEntityModelWithAttachments,
            BaseEntity(),
            limit=10
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
    
    def test_to_geo_and_back(self, config_data_accessor):
        # 1. INITIAL RETRIEVAL
        street_segments = config_data_accessor.get(
            StreetSegmentEntityModel,
            StreetSegmentFilterModel(),
            limit=10,
        )
        df = entities_to_data_frame(street_segments)

        # 2. CONVERT TO GeoDF (This step performs the drops, creating 'gdf')
        gdf = data_frame_to_geo_data_frame(
            data_frame=df,
            initial_crs = "EPSG:4326",
            target_crs = "EPSG:4326",
            split_multiline_string = False,
            geom_source_col = None,
            ignore_bad_geometry= True,
        )
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) > 0
        assert gdf.crs.to_epsg() == 4326
        
        # 3. IDENTIFY SURVIVOR IDs
        # Get the IDs that survived the 'data_frame_to_geo_data_frame' step.
        survivor_ids = set(gdf['segment_id'].tolist()) # Use 'segment_id' column from the GeoDataFrame
        
        # 4. FILTER ORIGINAL ENTITIES
        # Keep only the original entities whose IDs are in the survivor set.
        street_segments_original_filtered = sorted(
            [e.segment_id for e in street_segments if e.segment_id in survivor_ids]
        )
        
        # 5. CONVERT BACK TO ENTITIES (The second half of the round trip)
        df_v2 = geo_data_frame_to_data_frame(
            gdf=gdf,
            drop_geometry=True
        )
        
        street_segments_v2 = data_frame_to_entities(
            df = df_v2,
            entity_model=StreetSegmentEntityModel
        )
        
        # 6. FINAL ASSERTION
        ids_v2 = sorted([e.segment_id for e in street_segments_v2])

        # 1. Assert that the IDs match
        assert street_segments_original_filtered == ids_v2

        comparison_results = check_geometry_similarity(street_segments, street_segments_v2)
        failed_matches = [
            result for result in comparison_results 
            if not result["is_within_tolerance"]
        ]
        assert not failed_matches, \
            f"{len(failed_matches)} segments failed the 1 cm check. Details: {failed_matches}"

        





    def test_road_inventory_by_route_id(self, config_data_accessor):
        """
        Basic integration test for RoadInventoryEntityModel using
        a known-good sample route_id.
        """
        route_id = "L000620 NB"

        results = config_data_accessor.get(
            RoadInventoryEntityModel,
            RoadInventoryFilterModel(route_id=route_id),
            limit=10
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
            CurbLineEntityModel,
            CurbLineFilterModel(),
            limit=5
        )

        assert isinstance(results, list)
        assert len(results) > 0
        assert isinstance(results[0], CurbLineEntityModel)

    def test_exact_filter(self, config_data_accessor):
        """
        Test filtering on known curb_id (example: 182625).
        """
        known_id = "182625"
        results = config_data_accessor.get(
            CurbLineEntityModel,
            CurbLineFilterModel(curb_id=known_id),
            limit=10
        )

        assert isinstance(results, list)
        assert len(results) > 0

        for row in results:
            assert isinstance(row, CurbLineEntityModel)
            assert row.curb_id == known_id

    def test_prefix_filter(self, config_data_accessor):
        """
        Ensure prefix search on street_name works.
        """
        prefix = "DORCHESTER"  # example prefix; adjust based on actual data
        results = config_data_accessor.get(
            CurbLineEntityModel,
            CurbLineFilterModel(street_name_prefix=prefix),
            limit=10
        )

        assert isinstance(results, list)
        assert len(results) > 0

        for row in results:
            assert isinstance(row, CurbLineEntityModel)
            assert row.street_name.upper().startswith(prefix)

    def test_geo_dataframe(self, config_data_accessor):
        """
        Validate hydration into GeoDataFrame from geometry column.
        """
        import geopandas as gpd

        gdf = config_data_accessor.get_as_geo_data_frame(
            CurbLineEntityModel,
            CurbLineFilterModel(),
            limit=20,
            ignore_bad_geometry=True,
        )

        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) > 0
        assert gdf.crs is not None
        assert gdf.crs.to_epsg() == 4326  # WGS84

        assert "geometry" in gdf.columns
        assert gdf["geometry"].notnull().any()


