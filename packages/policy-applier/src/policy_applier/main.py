import json

import geopandas as gpd
import pandas as pd
from dotenv import load_dotenv
from rich.progress import track

from policy_applier.db_utils import (
    append_curb_segment_policies,
    append_policy_handling_jobs,
    read_policy_applier_tables,
)
from policy_applier.handler_utils import Direction, generate_event_log, run_policy_pass
from policy_applier.handler_utils import PARKING_ANYTIME_POLICY
from policy_applier.io_utils.arguments import parse_args

load_dotenv()


def prepare_location_policies(
    df_segments: gpd.GeoDataFrame,
    df_signs: pd.DataFrame,
    df_asset_locations: gpd.GeoDataFrame,
    df_sign_policies: pd.DataFrame,
    df_meter_policies: pd.DataFrame,
    df_nonsign_features: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Prepare location-policy dataframe by joining signs/meters with their
    policies and creating a unified policy lookup.
    Also prepares geometry lookup and non-sign feature lookup.

    Returns:
    - df_location_policies: DataFrame with asset_location_id, location,
        policy_id, policy_json, policy_arrow
    - df_geom: DataFrame with id and geometry for segments and asset locations
    - feature_lookup: Dict mapping feature_location to feature_type for
        non-sign features
    """
    # Non-sign features lookup (e.g. fire hydrants, bus stops)
    feature_lookup = df_nonsign_features.set_index("feature_location")[
        "feature_type"
    ].to_dict()

    # Prepare Geometry Lookup
    df_geom = pd.concat(
        [
            df_segments[["segment_id", "geography"]].rename(
                columns={"segment_id": "id", "geography": "geometry"}
            ),
            df_asset_locations[["asset_location_id", "location"]].rename(
                columns={"asset_location_id": "id", "location": "geometry"}
            ),
        ]
    )

    # Join sign and policy information
    df_location_signs = pd.merge(
        df_asset_locations,
        df_signs,
        left_on="asset_location_id",
        right_on="sign_location_id",
        how="inner",
    )
    df_location_sign_policies = pd.merge(
        df_location_signs, df_sign_policies, on="sign_id", how="left"
    )
    df_location_sign_policies = df_location_sign_policies[
        [
            "asset_location_id",
            "location",
            "sign_policy_id",
            "policy_json",
            "policy_arrow",
        ]
    ]

    # Join meter and meter policy information
    df_location_meter_policies_start = pd.merge(
        df_asset_locations[["asset_location_id", "location"]],
        df_meter_policies[
            ["start_asset_location_id", "meter_policy_id", "policy_json"]
        ],
        left_on="asset_location_id",
        right_on="start_asset_location_id",
        how="inner",
    )
    df_location_meter_policies_start["policy_arrow"] = Direction.AWAY

    df_location_meter_policies_end = pd.merge(
        df_asset_locations[["asset_location_id", "location"]],
        df_meter_policies[["end_asset_location_id", "meter_policy_id", "policy_json"]],
        left_on="asset_location_id",
        right_on="end_asset_location_id",
        how="inner",
    )
    df_location_meter_policies_end["policy_arrow"] = Direction.TOWARD

    df_location_meter_policies = pd.concat(
        [df_location_meter_policies_start, df_location_meter_policies_end],
        ignore_index=True,
    )
    df_location_meter_policies = df_location_meter_policies[
        [
            "asset_location_id",
            "location",
            "meter_policy_id",
            "policy_json",
            "policy_arrow",
        ]
    ]

    # Combine sign and meter policies into a unified location-policy dataframe
    df_location_policies = pd.concat(
        [
            df_location_sign_policies.rename(columns={"sign_policy_id": "policy_id"}),
            df_location_meter_policies.rename(columns={"meter_policy_id": "policy_id"}),
        ],
        ignore_index=True,
    )
    return df_location_policies, df_geom, feature_lookup


def validate_blockface(df_block: gpd.GeoDataFrame, blockface_id: str) -> None:
    """Validate blockface consistency before processing.

    Raises:
        ValueError: If blockface has mixed one-way side values or
            broken sequence.
    """
    # Check for mixed one-way side values
    if df_block["is_left_side_oneway"].nunique() > 1:
        raise ValueError(
            f"Blockface {blockface_id} contains mixed one-way side values!"
        )

    # Assert 'segment_seq' is a perfect 0 to n-1 sequence
    expected_seq = pd.Series(range(len(df_block)), dtype=df_block["segment_seq"].dtype)
    if not df_block["segment_seq"].equals(expected_seq):
        raise ValueError(
            f"Sequence for {blockface_id} is broken or doesn't start at 0!"
        )


def process_single_blockface(
    df_block: gpd.GeoDataFrame,
    df_location_policies: pd.DataFrame,
    df_geom: pd.DataFrame,
    feature_lookup: dict,
) -> list[dict]:
    """Process a single blockface through forward/backward passes and
        return policies.

    Returns:
        list: List of dicts with segment_id and policy_list for each segment.
    """
    blockface_results = []
    is_left_side_oneway = df_block["is_left_side_oneway"].iloc[0]

    # 1. Generate Log
    df_events = generate_event_log(
        df_block, df_location_policies, is_left_side_oneway, feature_lookup
    )

    # 2. Attach Geometry and Projection (Mercator for distance calc)
    df_events = pd.merge(df_events, df_geom, on="id", how="left")
    gdf_events = gpd.GeoDataFrame(
        df_events, geometry=df_events["geometry"], crs="EPSG:4326"
    ).to_crs(epsg=3395)

    # 3. Forward Pass
    df_fwd = run_policy_pass(gdf_events)

    # 4. Backward Pass
    gdf_events_bwd = gdf_events.iloc[::-1].reset_index(drop=True)
    gdf_events_bwd["direction"] = gdf_events_bwd["direction"].replace(
        {Direction.TOWARD: Direction.AWAY, Direction.AWAY: Direction.TOWARD}
    )
    df_bwd = run_policy_pass(gdf_events_bwd)

    # 5. Merge and Resolve Distances
    fwd_filtered = df_fwd[~pd.isna(df_fwd["policy"])].dropna(axis=1, how="all")
    bwd_filtered = df_bwd[~pd.isna(df_bwd["policy"])].dropna(axis=1, how="all")
    merged = pd.concat([fwd_filtered, bwd_filtered])

    if len(merged) == 0:
        return blockface_results

    merged["segment"] = pd.Categorical(
        merged["segment"], categories=df_block["segment_id"], ordered=True
    )

    merged["policy_str"] = merged["policy"].apply(
        lambda x: json.dumps(x, sort_keys=True)
    )
    merged = merged.sort_values(
        by=["segment", "policy_str", "priority"]
    ).drop_duplicates(subset=["segment", "policy_str"], keep="first")

    merged = pd.merge(
        pd.DataFrame({"segment": df_block["segment_id"]}),
        merged,
        on="segment",
        how="left",
    )

    merged["policy"] = merged["policy"].where(pd.notna(merged["policy"]), None)

    # 6. Format Policy JSON per segment
    for segment_id in merged["segment"].unique():
        seg_policies = merged[merged["segment"] == segment_id].sort_values(
            by="priority"
        )
        policy_list = [
            row["policy"]
            for _, row in seg_policies.iterrows()
            if pd.notna(row["policy"])
        ]
        blockface_results.append({"segment_id": segment_id, "policy_list": policy_list})

    return blockface_results


def process_segment_policies(
    df_segments: gpd.GeoDataFrame,
    df_signs: pd.DataFrame,
    df_asset_locations: gpd.GeoDataFrame,
    df_sign_policies: pd.DataFrame,
    df_meter_policies: pd.DataFrame,
    df_nonsign_features: pd.DataFrame,
    blanket_allowance: bool = False
) -> pd.DataFrame | None:
    """Process all blockfaces to determine curb policies.

    Returns:
        pd.DataFrame: DataFrame with segment_id and policy_list columns,
            or None if no results.
    """
    df_location_policies, df_geom, feature_lookup = prepare_location_policies(
        df_segments,
        df_signs,
        df_asset_locations,
        df_sign_policies,
        df_meter_policies,
        df_nonsign_features,
    )

    all_blockface_results = []

    for blockface in track(
        df_segments["blockface_id"].unique(), description="processing blockfaces"
    ):
        df_block = df_segments[df_segments["blockface_id"] == blockface].reset_index(
            drop=True
        )
        df_block = df_block.sort_values(by="segment_seq").reset_index(drop=True)

        # Validate blockface
        validate_blockface(df_block, blockface)

        # Handle empty blockfaces
        if len(df_block) == 1:
            if (
                df_block.iloc[0]["upstream_loc_list"] is None
                and df_block.iloc[0]["downstream_loc_list"] is None
            ):
                all_blockface_results.append(
                    {"segment_id": df_block.iloc[0]["segment_id"], "policy_list": []}
                )
                continue

        # Process blockface and collect results
        try:
            results = process_single_blockface(
                df_block, df_location_policies, df_geom, feature_lookup
            )
            all_blockface_results.extend(results)
        # TODO: acceptable continue processing other blockfaces if one fails?
        except Exception as e:
            print(f"Error processing blockface {blockface}: {e}")
            continue

    # Format Final Output
    if all_blockface_results:
        df_final = pd.DataFrame(all_blockface_results)
        if blanket_allowance:
            df_final['policy_list'] = df_final['policy_list'].apply(
                lambda x: x + [PARKING_ANYTIME_POLICY])
        df_final["policy_list"] = df_final["policy_list"].apply(json.dumps)
        return df_final

    # TODO: Possibly raise an error instead?
    return None


def main(
        job_id: str,
        schema: str,
        write_to_csv: bool = False,
        blanket_allowance: bool = False) -> None:
    """Main execution block to fetch, process, and propagate curb policies.

    Args:
        job_id (str): Job ID for Curb Segmenter data retrieval.
        schema (str): Database schema for reading/writing data.
        write_to_csv (bool, optional): Optionally, write outputs to a CSV for debugging.
            Defaults to False.
        blanket_allowance (bool, optional): If True, append a blanket parking allowance
    """
    # Data Ingestion
    (
        df_segments,
        df_signs,
        df_asset_locations,
        df_sign_policies,
        df_meter_policies,
        df_nonsign_features,
    ) = read_policy_applier_tables(curb_segment_job_id=job_id, schema=schema)

    # Process policies
    df_final = process_segment_policies(
        df_segments=df_segments,
        df_signs=df_signs,
        df_asset_locations=df_asset_locations,
        df_sign_policies=df_sign_policies,
        df_meter_policies=df_meter_policies,
        df_nonsign_features=df_nonsign_features,
        blanket_allowance=blanket_allowance
    )

    # Write to database
    # TODO: df_final should not be None.
    if df_final is not None:
        # Optionally, write to csv file for debugging purposes
        if write_to_csv:
            df_final.to_csv("curb_policy_output.csv", index=False)
        new_job_id = append_policy_handling_jobs(schema=schema)
        append_curb_segment_policies(df_final, job_id=new_job_id, schema=schema)


if __name__ == "__main__":
    args = parse_args()
    # curb segmenter job
    job_id = args.job_id
    # schema for read/write
    schema = args.schema
    # not in argparser, but will want to add to config.
    write_to_csv = False
    blanket_allowance = False

    main(job_id=job_id,
         schema=schema,
         write_to_csv=write_to_csv,
         blanket_allowance=blanket_allowance)
