from typing import (
    List,
)

import geopandas as gpd
import pytest
from data_utils.accessor import (
    DataAccessor,
    data_frame_to_entities,
    data_frame_to_geo_data_frame,
    entities_to_data_frame,
    geo_data_frame_to_data_frame,
)
from data_utils.queries_and_contracts import (
    CurbLineEntityModel,
    CurbLineFilterModel,
    RoadInventoryEntityModel,
    RoadInventoryFilterModel,
    StreetSegmentEntityModel,
    StreetSegmentFilterModel,
)
from shapely.wkt import loads

TOLERANCE_M = 0.025


def check_geometry_similarity(
    list_a: List[StreetSegmentEntityModel], list_b: List[StreetSegmentEntityModel]
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
        min_hausdorff_dist = float("inf")

        for id_b, geom_b in shapely_b:
            # Calculate distance
            dist = geom_a.hausdorff_distance(geom_b)

            if dist < min_hausdorff_dist:
                min_hausdorff_dist = dist
                best_match_id = id_b

        # 3. Check against tolerance
        is_match = min_hausdorff_dist < TOLERANCE_M

        matches.append(
            {
                "segment_a_id": obj_a.segment_id,
                "segment_b_id": best_match_id,
                "hausdorff_distance": min_hausdorff_dist,
                "is_within_tolerance": is_match,
            }
        )

    return matches


@pytest.mark.integration
class TestConfigDrivenInit:
    @pytest.fixture(scope="class")
    def config_data_accessor(self):
        """This path will be loaded by DataAccessor via AppSettings."""
        return DataAccessor(config_path=".env")

    def test_geo_dataframe(self, config_data_accessor):
        gdf = config_data_accessor.get_as_geo_data_frame(
            StreetSegmentEntityModel,
            StreetSegmentFilterModel(),
            limit=10,
            ignore_bad_geometry=True,
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
            initial_crs="EPSG:4326",
            target_crs="EPSG:4326",
            split_multiline_string=False,
            geom_source_col=None,
            ignore_bad_geometry=True,
        )
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) > 0
        assert gdf.crs.to_epsg() == 4326

        # 3. IDENTIFY SURVIVOR IDs
        # Get the IDs that survived the 'data_frame_to_geo_data_frame' step.
        survivor_ids = set(
            gdf["segment_id"].tolist()
        )  # Use 'segment_id' column from the GeoDataFrame

        # 4. FILTER ORIGINAL ENTITIES
        # Keep only the original entities whose IDs are in the survivor set.
        street_segments_original_filtered = sorted(
            [e.segment_id for e in street_segments if e.segment_id in survivor_ids]
        )

        # 5. CONVERT BACK TO ENTITIES (The second half of the round trip)
        df_v2 = geo_data_frame_to_data_frame(gdf=gdf, drop_geometry=True)

        street_segments_v2 = data_frame_to_entities(
            df=df_v2, entity_model=StreetSegmentEntityModel
        )

        # 6. FINAL ASSERTION
        ids_v2 = sorted([e.segment_id for e in street_segments_v2])

        # 1. Assert that the IDs match
        assert street_segments_original_filtered == ids_v2

        comparison_results = check_geometry_similarity(
            street_segments, street_segments_v2
        )
        failed_matches = [
            result for result in comparison_results if not result["is_within_tolerance"]
        ]
        assert not failed_matches, (
            f"{len(failed_matches)} segments failed the 1 cm check. Details: {failed_matches}"
        )

    def test_road_inventory_geo_dataframe(self, config_data_accessor):
        """
        Ensure we can hydrate a GeoDataFrame for road inventory,
        with a valid CRS and geometry column.
        """
        route_id = "L000620 NB"

        gdf = config_data_accessor.get_as_geo_data_frame(
            RoadInventoryEntityModel,
            RoadInventoryFilterModel(route_id=route_id),
            limit=5,
        )

        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) > 0

        # Should be WGS84
        assert gdf.crs is not None
        assert gdf.crs.to_epsg() == 4326

        # Ensure geometry column is present and has non-null values
        assert "geometry" in gdf.columns
        assert gdf["geometry"].notnull().any()

    def test_geo_dataframe(self, config_data_accessor):
        """
        Validate hydration into GeoDataFrame from geometry column for CurblineEntityModel.
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
