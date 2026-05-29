"""
Test for main.py policy applier function.
Tests are defined based on test data in test_data/test_name folders.
Each test runs the main function with mocked dependencies to return the test data,
    then compares the actual output to expected output from the test data.
"""
import json
import pathlib
import pytest
import geopandas as gpd
import pandas as pd
from pandas.testing import assert_frame_equal

from policy_applier import core


TEST_DATA_DIR = pathlib.Path(__file__).resolve().parent / "test_data"


def load_test_description(test_name: str) -> str:
    """Load a human-readable test description from description.txt."""
    description_file = TEST_DATA_DIR / test_name / "description.txt"
    if description_file.exists():
        return description_file.read_text(encoding="utf-8").strip()
    return test_name


TEST_NAMES = sorted([p.name for p in TEST_DATA_DIR.iterdir() if p.is_dir()])
TEST_DESCRIPTIONS = [
    load_test_description(name) for name in TEST_NAMES
]


def load_test_data(test_name) -> dict[str, pd.DataFrame | gpd.GeoDataFrame]:
    """Load test data from test_data/test_name folder"""
    test_folder = TEST_DATA_DIR / test_name

    df_segments = gpd.read_file(test_folder / "curb_segments.geojson")
    for col in ["upstream_loc_list", "downstream_loc_list"]:
        df_segments[col] = df_segments[col].apply(
            lambda x: list(x) if x is not None and len(x) > 0 else x
        )
    df_segments.rename_geometry("geography", inplace=True)
    df_asset_locations = gpd.read_file(test_folder / "asset_locations.geojson")
    df_asset_locations.rename_geometry("location", inplace=True)
    df_meter_policies = pd.read_csv(test_folder / "meter_policies.csv")
    df_sign_policies = pd.read_csv(test_folder / "sign_policies.csv")
    for df in [df_meter_policies, df_sign_policies]:
        df["policy_json"] = df["policy_json"].apply(json.loads)

    df_expected = pd.read_csv(test_folder / "expected_output.csv")
    df_expected["policy_list"] = df_expected["policy_list"].str. \
        replace("'", '"').apply(json.loads)

    return {
        "segments": df_segments,
        "signs": pd.read_csv(test_folder / "signs.csv"),
        "asset_locations": df_asset_locations,
        "meter_policies": df_meter_policies,
        "sign_policies": df_sign_policies,
        "nonsign_features": pd.read_csv(test_folder / "nonsign_features.csv"),
        "expected_df": df_expected,
    }


def run_policy_applier_test(
        test_name: str
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the policy applier main function with mocked dependencies.
    Returns (df_actual, df_expected)"""
    test_info = load_test_data(test_name)

    df_segments = test_info["segments"]
    df_signs = test_info["signs"]
    df_asset_locations = test_info["asset_locations"]
    df_sign_policies = test_info["sign_policies"]
    df_meter_policies = test_info["meter_policies"]
    df_nonsign_features = test_info["nonsign_features"]
    df_expected = test_info["expected_df"]

    test_folder = TEST_DATA_DIR / test_name

    df_actual = core.process_segment_policies(
        df_segments=df_segments,
        df_signs=df_signs,
        df_asset_locations=df_asset_locations,
        df_sign_policies=df_sign_policies,
        df_meter_policies=df_meter_policies,
        df_nonsign_features=df_nonsign_features
    )

    df_actual.to_csv(test_folder / "curb_policy_output.csv", index=False)
    df_actual["policy_list"] = df_actual["policy_list"].apply(json.loads)

    return df_actual, df_expected


def remove_policy_priority_ordered(
        policy_list: list[dict]
    ) -> list:
    """Remove priority field from each policy in the list, keeping order."""
    return [
            {k: v for k, v in policy.items() if k != "priority"}
            if isinstance(policy, dict)
            else policy
            for policy in policy_list
    ]


def remove_policy_priority_unordered(
        policy_list: list[dict]
    ) -> list[str]:
    """Remove priority and sort policies for comparison."""
    normalized_values = []
    for policy in policy_list:
        # Remove priority and normalize
        policy_no_priority = {
            k: v for k, v in policy.items() if k != "priority"
        }
        policy_no_priority_sorted = json.loads(
            json.dumps(policy_no_priority, sort_keys=True)
        )
        normalized_values.append(
            json.dumps(policy_no_priority_sorted, sort_keys=True)
        )
    return sorted(normalized_values)


@pytest.mark.parametrize("test_name", TEST_NAMES, ids=TEST_DESCRIPTIONS)
def test_one_test_policies_ordered(
        test_name: str
    ) -> None:
    """
    Runs test for policy applier based on test data defined in test_data/test_name folder
    Does not ignore policy priority order in comparison,
    i.e. policies must be in same order in actual vs expected for test to pass,
    but the actual policy priority number is not checked
    """
    df_actual, df_expected = run_policy_applier_test(test_name)
    # Normalize policies: keep order by key, normalize internal dict ordering
    for df in [df_actual, df_expected]:
        df["policy_list"] = df["policy_list"].apply(
            remove_policy_priority_ordered
        )

    assert_frame_equal(df_actual, df_expected, check_like=True)


@pytest.mark.parametrize("test_name", TEST_NAMES, ids=TEST_DESCRIPTIONS)
def test_one_test_policies_unordered(
        test_name: str
    ) -> None:
    """
    Runs test for policy applier based on test data defined in test_data/test_name folder
    Ignores policy priority order in comparison,
    i.e. policies can be in any order in actual vs expected for test to pass
    """
    df_actual, df_expected = run_policy_applier_test(test_name)

    # Normalize policies: ignore both key order and value ordering
    for df in [df_actual, df_expected]:
        df["policy_list"] = df["policy_list"].apply(
            remove_policy_priority_unordered
        )

    assert_frame_equal(df_actual, df_expected, check_like=True)
