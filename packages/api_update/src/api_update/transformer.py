"""
processors.py

Contains modular functions for curb data acquisition, processing, and export.
"""

import gc
import hashlib
import json
import uuid
from typing import cast

import geopandas as gpd
import pandas as pd
from shapely import wkb
from shapely.geometry.base import BaseGeometry


def add_curb_zone(
    curb_zones_list: list[dict],
    segment_id: uuid.UUID,
    geom: BaseGeometry,
    run_date: pd.Timestamp,
) -> None:
    """
    Appends a formatted curb zone dictionary to the provided list.
    """
    curb_zones_list.append(
        {
            "curb_zone_id": segment_id,
            "geometry": geom,
            "published_date": run_date,
            "last_updated_date": run_date,
        }
    )


def add_rule(curb_policy_rules: list[dict], policy_id: uuid.UUID, rule: dict) -> None:
    """Processes and appends rule record"""
    curb_policy_rules.append(
        {
            "rule_id": uuid.uuid4(),
            "curb_policy_id": policy_id,
            "activity": rule.get("activity"),
            "max_stay": rule.get("max_stay"),
            "max_stay_unit": rule.get("max_stay_unit"),
            "no_return": rule.get("no_return"),
            "no_return_unit": rule.get("no_return_unit"),
            "user_classes": rule.get("user_classes"),
            "user_classes_except": rule.get("user_classes_except"),
            "purposes": rule.get("purposes"),
        }
    )


def add_time_span(
    curb_policy_time_spans: list[dict],
    policy_id: uuid.UUID,
    time_span: dict,
) -> None:
    curb_policy_time_spans.append(
        {
            "time_span_id": uuid.uuid4(),
            "curb_policy_id": policy_id,
            "start_date": time_span.get("start_date"),
            "end_date": time_span.get("end_date"),
            "days_of_week": time_span.get("days_of_week"),
            "time_of_day_start": time_span.get("time_of_day_start"),
            "time_of_day_end": time_span.get("time_of_day_end"),
        }
    )


def add_curb_policy(
    curb_policies: list[dict],
    policy_id: uuid.UUID,
    run_date: pd.Timestamp,
    priority: str,
) -> None:
    curb_policies.append(
        {
            "curb_policy_id": policy_id,
            "published_date": run_date,
            "priority": int(priority),
        }
    )


def add_curb_zone_policy(
    curb_zone_policies: list[dict], segment_id: uuid.UUID, policy_id: uuid.UUID
) -> None:
    curb_zone_policies.append({"curb_zone_id": segment_id, "curb_policy_id": policy_id})


def policy_hashing(policy_dict: dict) -> str:
    """
    Generates a hash for a given policy dictionary to assist with de-duplication.
    """

    # Convert the policy dict to a sorted JSON string to ensure consistent hashing
    policy_str = json.dumps(policy_dict, sort_keys=True, default=str)
    return hashlib.sha256(policy_str.encode("utf-8")).hexdigest()


def assign_policy(
    policy_dict: dict,
    priority: str,
    segment_id: uuid.UUID,
    run_date: pd.Timestamp,
    policy_hash_map: dict,
    curb_policies: list,
    curb_zone_policies: list,
    curb_policy_rules: list,
    curb_policy_time_spans: list,
) -> None:
    policy_hash = policy_hashing(policy_dict)

    if policy_hash in policy_hash_map:
        # Use the existing ID
        policy_id = policy_hash_map[policy_hash]
    else:
        # Create a new ID and store it in the map
        policy_id = uuid.uuid4()
        policy_hash_map[policy_hash] = policy_id
        add_curb_policy(curb_policies, policy_id, run_date, priority)
        for rule in policy_dict.get("rules", []):
            add_rule(curb_policy_rules, policy_id, rule)
        for time_span in policy_dict.get("time_spans", []):
            add_time_span(curb_policy_time_spans, policy_id, time_span)

    add_curb_zone_policy(curb_zone_policies, segment_id, policy_id)


def transform_policy_updates(
    staging_data_dict: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """
    Processes and flattens the data, returning updated DataFrames.

    Args:
        staging_data_dict (dict): DataFrames from "staging" schema.

    Returns:
        dict: Updated DataFrames to "public_cds" schema.
    """
    curb_zones = []
    curb_policies = []
    curb_zone_policies = []
    curb_policy_rules = []
    curb_policy_time_spans = []
    policy_hash_map = {}

    curb_segments = staging_data_dict["curb_segments"]
    curb_segment_policies = staging_data_dict["curb_segment_policies"]

    if curb_segments.empty or curb_segment_policies.empty:
        raise ValueError(
            "Input segment or policy table is empty; nothing to transform."
        )

    df_updates = pd.merge(
        curb_segment_policies[["segment_id", "policy_list"]],
        curb_segments[["segment_id", "run_date", "geography"]],
        on="segment_id",
        how="left",
    )

    # Explicitly delete the source tables to free up memory
    del curb_segment_policies, curb_segments

    # Force garbage collection to reclaim memory immediately
    gc.collect()

    for row in df_updates.to_dict("records"):
        segment_id = row["segment_id"]
        geom = wkb.loads(row["geography"], hex=True)
        run_date = row["run_date"]

        # Add curb zone for the segment
        add_curb_zone(curb_zones, segment_id, geom, run_date)

        policy_list = cast(dict[str, dict], row["policy_list"])
        if not isinstance(policy_list, dict):
            raise ValueError(
                f"Expected policy_list to be a dict, "
                f"got {type(policy_list)} for segment_id {segment_id}"
            )

        for priority, policy_dict in policy_list.items():
            assign_policy(
                policy_dict,
                priority,
                segment_id,
                run_date,
                policy_hash_map,
                curb_policies,
                curb_zone_policies,
                curb_policy_rules,
                curb_policy_time_spans,
            )

    # Convert lists to DataFrames once at the end
    curb_zones = gpd.GeoDataFrame(curb_zones, geometry="geometry")
    curb_policies = pd.DataFrame(curb_policies)
    curb_zone_policies = pd.DataFrame(curb_zone_policies)
    curb_policy_rules = pd.DataFrame(curb_policy_rules)
    curb_policy_time_spans = pd.DataFrame(curb_policy_time_spans)

    # Returns modified CS dataframes.
    return {
        "curb_zones": curb_zones,
        "curb_policies": curb_policies,
        "curb_zone_policies": curb_zone_policies,
        "curb_policy_rules": curb_policy_rules,
        "curb_policy_time_spans": curb_policy_time_spans,
    }
