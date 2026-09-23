"""Tests for curb segmentation output."""

from collections.abc import Iterable
from pathlib import Path

import geopandas as gpd
import pytest
import static_curb_segmentation as scs
from pandas.testing import assert_frame_equal

TEST_DATA_DIR = Path("tests/curb_segmenter/test_data")


def get_test_directories() -> list[Path]:
    """Discover all test directories under test_data."""
    return sorted([d for d in TEST_DATA_DIR.iterdir() if d.is_dir()])


@pytest.mark.parametrize(
    "test_dir",
    get_test_directories(),
    ids=lambda d: d.name,
)
def test_curb_segments_match_expected(test_dir) -> None:
    """
    Runs curb segmentation on static test data
    Then compares output curb_segments.geojson to expected_curb_segments.geojson
    """
    # Run curb segmentation for test data
    scs.run_static_curb_segmentation_pipeline(test_dir)

    # Check outputs
    actual_path = test_dir / "curb_segments.geojson"
    expected_path = test_dir / "expected_curb_segments.geojson"

    if not actual_path.exists():
        pytest.skip("curb_segments.geojson not found")
    if not expected_path.exists():
        pytest.skip("expected_curb_segments.geojson not found")

    # Read and drop segment_id
    # this is bc this changes on each curb segmentation run
    not_compare_cols = [
        "segment_id",
        "job_id",
        "upstream_location",
        "downstream_location",
    ]
    actual = gpd.read_file(actual_path).drop(columns=not_compare_cols, errors="ignore")
    expected = gpd.read_file(expected_path).drop(
        columns=not_compare_cols, errors="ignore"
    )
    for col in ["upstream_loc_list", "downstream_loc_list"]:
        for df in [actual, expected]:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: sorted(x) if isinstance(x, Iterable) else x
                )

    # Ensure same column order
    common_cols = sorted(set(actual.columns) & set(expected.columns))
    actual = actual[common_cols].reset_index(drop=True)
    expected = expected[common_cols].reset_index(drop=True)

    # Compare with lenient settings for floating point and dtype
    # pandas' numeric tolerance does not apply inside Shapely geometry objects.
    assert actual.geometry.geom_equals_exact(expected.geometry, tolerance=1e-5).all()
    assert_frame_equal(
        actual.drop(columns="geometry"),
        expected.drop(columns="geometry"),
        check_dtype=False,
        atol=1e-5,
        rtol=1e-5,
        check_names=True,
    )
