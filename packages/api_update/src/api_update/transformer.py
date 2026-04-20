"""
transformer.py

Contains modular functions for curb data acquisition, processing, and export.
"""

import uuid
import json
import pandas as pd

from packages.api_update.src.utils_geo import consolidate_curb_segments


def extract_unique_policies(df_updates: pd.DataFrame) \
        -> tuple[list[dict], dict[str, list[str]]]:
    """Flattens the nested policy data and returns unique policy dicts and a zone-to-json mapping."""
    df_exploded = df_updates[['curb_zone_id', 'policy_list']].explode('policy_list').dropna()
    df_exploded['policy_json'] = df_exploded['policy_list'].apply(lambda x: json.dumps(x, sort_keys=True))

    # Map Zone ID -> List of Policy JSON strings
    zone_to_policies = df_exploded.groupby('curb_zone_id')['policy_json'].apply(list).to_dict()

    # Get unique policy dictionaries
    unique_json = df_exploded['policy_json'].unique()
    unique_dicts = [json.loads(x) for x in unique_json]

    return unique_dicts, zone_to_policies


def _create_policy_sub_elements(
        policy_id: uuid.UUID,
        policy_data: dict) -> tuple[list[dict], list[dict]]:
    """Extracts rules and time spans from a policy dictionary."""
    rules = [
        {
            "rule_id": uuid.uuid4(),
            "curb_policy_id": policy_id,
            **{k: rule.get(k) for k in
               ["activity",
                "max_stay",
                "max_stay_unit",
                "no_return",
                "no_return_unit",
                "user_classes",
                "user_classes_except",
                "purposes"]}
        }
        for rule in policy_data.get("rules", [])
    ]

    time_spans = [
        {
            "time_span_id": uuid.uuid4(),
            "curb_policy_id": policy_id,
            **{k: ts.get(k) for k in ["start_date",
                                      "end_date",
                                      "days_of_week",
                                      "time_of_day_start",
                                      "time_of_day_end"]}
        }
        for ts in policy_data.get("time_spans", [])
    ]
    return rules, time_spans


def build_policy_tables(
        unique_policies: list[dict],
        run_time: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Builds the Curb Policy, Rules, and Time Span dataframes."""
    policies, rules, spans = [], [], []
    json_to_id_map = {}

    for policy in unique_policies:
        p_id = uuid.uuid4()
        p_json = json.dumps(policy, sort_keys=True)
        json_to_id_map[p_json] = p_id

        policies.append({
            "curb_policy_id": p_id,
            "published_date": run_time,
            "priority": policy.get("priority"),
        })

        r, s = _create_policy_sub_elements(p_id, policy)
        rules.extend(r)
        spans.extend(s)

    return pd.DataFrame(policies), pd.DataFrame(rules), pd.DataFrame(spans), json_to_id_map


def build_zone_tables(
        df_updates: pd.DataFrame,
        zone_to_json: dict,
        json_to_id: dict,
        run_time: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:

    """Builds the Curb Zone and Zone-Policy relationship tables."""
    zones, zone_policies = [], []

    for row in df_updates.to_dict("records"):
        z_id = row["curb_zone_id"]
        zones.append({
            "curb_zone_id": z_id,
            "geometry": row["geography"],
            "published_date": run_time,
            "last_updated_date": run_time,
            "start_date": run_time,
            "end_date": None,
        })

        policy_jsons = zone_to_json.get(z_id, [])
        for p_json in policy_jsons:
            zone_policies.append({
                "curb_zone_id": z_id,
                "curb_policy_id": json_to_id[p_json]
            })

    zones = pd.DataFrame(zones)
    zones['geometry'] = zones['geometry'].apply(lambda g: g.wkt if g else None)

    zone_policies = pd.DataFrame(zone_policies)

    return zones, zone_policies


def transform_policy_updates(
    staging_data_dict: dict[str, pd.DataFrame],
    api_data_dict: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    """
    Processes and flattens the data, returning updated DataFrames.

    Args:
        staging_data_dict (dict): DataFrames from "staging" schema.
        api_data_dict (dict): DataFrames from "public_cds" schema.

    Returns:
        dict: Updated DataFrames to "public_cds" schema.
    """

    run_time = pd.Timestamp.now()

    # Process staging tables to create a consolidated view
    df_updates = consolidate_curb_segments(
        staging_data_dict["curb_segments"],
        staging_data_dict["curb_segment_policies"])

    # Flatten and get unique policies
    unique_policies, zone_to_json_map = extract_unique_policies(df_updates)

    # Build Policy related tables
    df_policies, df_rules, df_spans, json_to_id_map = build_policy_tables(unique_policies, run_time)

    # Build Zone related tables
    df_zones, df_zone_policies = build_zone_tables(df_updates, zone_to_json_map, json_to_id_map, run_time)

    return {
        "curb_zones": df_zones,
        "curb_policies": df_policies,
        "curb_zone_policies": df_zone_policies,
        "curb_policy_rules": df_rules,
        "curb_policy_time_spans": df_spans,
    }
