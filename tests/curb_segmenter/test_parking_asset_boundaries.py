"""Regression checks for boundaries added to the actual snapping output."""

import geopandas as gpd
import pytest
from curb_segmenter.curb_segmentation import (
    create_curb_segments_with_parking_asset,
    snap_points_to_curbs,
)
from shapely.geometry import LineString, Point


@pytest.mark.parametrize(("point_column", "prefix"), [("ps_id", "PS"), ("mp_id", "PM")])
def test_endpoint_row_accepts_snapping_metadata(point_column, prefix) -> None:
    """Sign and meter splits retain the two boundary IDs and complete curb."""
    curbs = gpd.GeoDataFrame(
        {
            "blockface_id": ["curb"],
            "is_left_side_oneway": [False],
            "segment_length_ft": [100.0],
        },
        geometry=[LineString([(0, 0), (100, 0)])],
        crs="EPSG:2249",
    )
    points = gpd.GeoDataFrame(
        {point_column: ["first", "second"]},
        geometry=[Point(25, 2), Point(75, 2)],
        crs=curbs.crs,
    )
    snapped, unsnapped = snap_points_to_curbs(
        points, point_column, curbs, "blockface_id"
    )
    assert unsnapped.empty
    assert "curb_geometry" in snapped.columns
    segments = create_curb_segments_with_parking_asset(
        curbs,
        "blockface_id",
        snapped,
        point_column,
        prefix,
        [],
    )
    assert len(segments) == 3
    assert segments.geometry.length.sum() == pytest.approx(100)
    assert segments[f"start_{point_column}"].dropna().tolist() == ["first", "second"]
    assert segments[f"end_{point_column}"].dropna().tolist() == ["first", "second"]
