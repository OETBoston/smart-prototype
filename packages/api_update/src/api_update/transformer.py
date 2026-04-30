"""
transformer.py

Contains modular functions for curb data acquisition, processing, and export.
"""

import ast
import uuid
import json
import pandas as pd
import logging
from typing import cast
import geopandas as gpd
from shapely import wkb

from packages.api_update.src.utils import get_policy_json, get_policy_signatures
from packages.api_update.src.utils_geo import consolidate_curb_segments


logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


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

    return unique_dicts, cast(dict[str, list[str]], zone_to_policies)


def _create_policy_sub_elements(
        policy_id: uuid.UUID,
        policy_data: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Extracts rules, time spans, and rates from a policy dictionary."""
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
                                      "days_of_month",
                                      "weeks_of_month",
                                      "months",
                                      "time_of_day_start",
                                      "time_of_day_end",
                                      "designated_period",
                                      "designated_period_except"]}
        }
        for ts in policy_data.get("time_spans", [])
    ]

    rates = [
        {
            "rate_id": uuid.uuid4(),
            "curb_policy_id": policy_id,
            **{k: rule.get('rate', {}).get(k) for k in
               ["rate",
                "rate_unit",
                "rate_unit_period",
                "increment_duration",
                "increment_amount",
                "start_duration",
                "end_duration",
                "max_fee"]}
        }
        for rule in policy_data.get("rules", [])
        if rule.get('rate')
    ]

    return rules, time_spans, rates


def build_policy_tables(
        unique_policies: list[dict],
        run_time: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Builds the Curb Policy, Rules, Time Span, and Rates dataframes."""
    policies, rules, spans, rates = [], [], [], []
    json_to_id_map = {}

    logger.info(f"Building Policy tables for {len(unique_policies)} policies...")

    for i, policy in enumerate(unique_policies):

        p_id = uuid.uuid4()
        p_json = json.dumps(policy, sort_keys=True)
        json_to_id_map[p_json] = p_id

        policies.append({
            "curb_policy_id": p_id,
            "name": policy.get("name", None),
            "description": policy.get("description", None),
            "published_date": run_time,
            "priority": policy.get("priority"),
            "policy_color_id": None
        })

        r, s, rt = _create_policy_sub_elements(p_id, policy)
        rules.extend(r)
        spans.extend(s)
        rates.extend(rt)

    return pd.DataFrame(policies), pd.DataFrame(rules), pd.DataFrame(spans), pd.DataFrame(rates), json_to_id_map


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

    # 1. Pre-process Existing Data
    old_policies = api_data_dict["curb_policies"].copy()
    old_rules = api_data_dict["curb_policy_rules"].copy()
    old_spans = api_data_dict["curb_policy_time_spans"].copy()
    old_rates = api_data_dict["curb_policy_rates"].copy()
    old_zone_policies = api_data_dict["curb_zone_policies"].copy()

    # Vectorized eval
    old_spans['designated_period'] = old_spans['designated_period'].apply(
        lambda x: list(ast.literal_eval(x)) if pd.notna(x) else None)

    old_policies['policy_json'] = get_policy_json(old_policies, old_rules, old_spans, old_rates)
    old_policies["signature"] = get_policy_signatures(old_policies)

    # 2. Process Staging Data
    df_updates = consolidate_curb_segments(
        staging_data_dict["curb_segments"],
        staging_data_dict["curb_segment_policies"])

    # Flatten and get unique policies
    unique_policies, zone_to_json_map = extract_unique_policies(df_updates)
    # Build Policy related tables
    new_policies, new_rules, new_spans, new_rates, json_to_id_map = build_policy_tables(unique_policies, run_time)

    new_policies['policy_json'] = get_policy_json(new_policies, new_rules, new_spans, new_rates)
    new_policies["signature"] = get_policy_signatures(new_policies)

    # 3. Geo Processing
    new_zones, new_zone_policies = build_zone_tables(df_updates, zone_to_json_map, json_to_id_map, run_time)
    new_zones['geometry'] = gpd.GeoSeries.from_wkt(new_zones['geometry'])
    new_zones = gpd.GeoDataFrame(new_zones, geometry='geometry', crs="EPSG:4326")

    old_zones = api_data_dict["curb_zones"].copy()
    old_zones['geometry'] = old_zones['geometry'].apply(lambda x: wkb.loads(x, hex=True) if isinstance(x, str) else x)
    old_zones = gpd.GeoDataFrame(old_zones, geometry='geometry', crs="EPSG:4326")

    #
    lookup = old_policies.set_index('signature')['curb_policy_id']
    valid_new = new_policies[new_policies['signature'].isin(lookup.index)]
    mapping_dict = dict(zip(
        valid_new['curb_policy_id'],
        valid_new['signature'].map(lookup)
    ))
    new_zone_policies['curb_policy_id'] = new_zone_policies['curb_policy_id'].replace(mapping_dict)
    new_policies = new_policies[~new_policies['curb_policy_id'].isin(mapping_dict.keys())]
    new_rules = new_rules[~new_rules['curb_policy_id'].isin(mapping_dict.keys())]
    new_spans = new_spans[~new_spans['curb_policy_id'].isin(mapping_dict.keys())]
    new_rates = new_rates[~new_rates['curb_policy_id'].isin(mapping_dict.keys())]

    # 4. Change Detection
    # Spatial join to find candidates
    zones_change = gpd.sjoin(new_zones, old_zones, how="inner", predicate="intersects", lsuffix='new', rsuffix='old')
    left_geom = zones_change.geometry
    right_geom = gpd.GeoSeries(
        old_zones.loc[zones_change["index_old"], "geometry"].values,
        index=zones_change.index,
        crs=zones_change.crs
    )
    zones_change['geometry_existing'] = right_geom
    intersections = left_geom.intersection(right_geom)
    zones_change = zones_change[intersections.geom_type.isin(['LineString', 'MultiLineString'])]

    # Pre-map policies to zones
    new_zone_policies_dict = new_zone_policies.groupby('curb_zone_id')['curb_policy_id'].apply(set).to_dict()
    old_zone_policies_dict = old_zone_policies.groupby('curb_zone_id')['curb_policy_id'].apply(set).to_dict()

    old_zones = old_zones.set_index('curb_zone_id')

    zones_to_drop_from_new = set()
    zones_to_expire_in_old = set()
    zone_id_replacements = {}

    # Iterating only over intersections is faster, but we use dict lookups inside
    for _, row in zones_change.iterrows():
        n_id, o_id = row['curb_zone_id_new'], row['curb_zone_id_old']

        # Check geometry equality
        if row['geometry'].equals(row['geometry_existing']):
            zones_to_drop_from_new.add(n_id)
            if new_zone_policies_dict.get(n_id) == old_zone_policies_dict.get(o_id):
                # Identical: just update timestamp and discard the "new" one
                old_zones.at[o_id, 'last_updated_date'] = run_time
            else:
                # Same geometry, different policy: update old, map new ID to old ID
                old_zones.at[o_id, 'last_updated_date'] = run_time
                zones_to_expire_in_old.add(o_id)  # Clear old policies
                zone_id_replacements[n_id] = o_id
        else:
            # Different geometry: Expire old zone
            old_zones.loc[o_id, ['last_updated_date', 'end_date']] = run_time
            zones_to_expire_in_old.add(o_id)

    # 5. Bulk Updates
    old_zones = old_zones.reset_index()
    new_zones = new_zones[~new_zones['curb_zone_id'].isin(zones_to_drop_from_new)]
    old_zone_policies_to_delete = old_zone_policies[
        old_zone_policies['curb_zone_id'].isin(zones_to_expire_in_old)].reset_index(drop=True)
    old_zone_policies = old_zone_policies[
        ~old_zone_policies['curb_zone_id'].isin(zones_to_expire_in_old)]

    # Apply ID replacements in bulk
    new_zone_policies['curb_zone_id'] = new_zone_policies['curb_zone_id'].replace(zone_id_replacements)

    # --- 5. CLEANUP & ORPHAN REMOVAL ---
    # Only keep policies that are actually linked to an active zone
    active_old_zone_ids = set(old_zones[old_zones['end_date'].isna()]['curb_zone_id'])
    active_new_zone_ids = set(new_zones['curb_zone_id'])
    active_zone_ids = active_new_zone_ids.union(active_old_zone_ids)

    new_zone_policies = new_zone_policies[new_zone_policies['curb_zone_id'].isin(active_zone_ids)]
    old_zone_policies = old_zone_policies[old_zone_policies['curb_zone_id'].isin(active_zone_ids)]

    active_policy_ids = set(new_zone_policies['curb_policy_id']).union(set(old_zone_policies['curb_policy_id']))

    # Helper to filter multiple dataframes at once
    def filter_by_policy(dfs, ids):
        return [df[df['curb_policy_id'].isin(ids)] for df in dfs]

    [new_policies, new_rules, new_spans, new_rates] = filter_by_policy(
        [new_policies, new_rules, new_spans, new_rates], active_policy_ids
    )
    [old_policies, old_rules, old_spans, old_rates] = filter_by_policy(
        [old_policies, old_rules, old_spans, old_rates], active_policy_ids
    )

    new_policies['description'] = "dummy description"

    # --- 6. FINAL CONCATENATION ---
    return {
        "curb_zones":
            {
                "table": pd.concat([new_zones, old_zones], ignore_index=True),
                "keys": ["curb_zone_id"]
             },
        "curb_policies":
            {
                "table": pd.concat([new_policies, old_policies], ignore_index=True),
                "keys": ["curb_policy_id"]
             },
        "curb_zone_policies":
            {
                "table": pd.concat([new_zone_policies, old_zone_policies], ignore_index=True),
                "keys": ["curb_zone_id", "curb_policy_id"]
            },
        "curb_zone_policies_to_delete":
            {
                "table": old_zone_policies_to_delete,
                "keys": ["curb_zone_id", "curb_policy_id"]
            },
        "curb_policy_rules":
            {
                "table": pd.concat([new_rules, old_rules], ignore_index=True),
                "keys": ["rule_id"]
            },
        "curb_policy_time_spans":
            {
                "table": pd.concat([new_spans, old_spans], ignore_index=True),
                "keys": ["time_span_id"]
            },
        "curb_policy_rates":
            {
                "table": pd.concat([new_rates, old_rates], ignore_index=True),
                "keys": ["rate_id"]
            },
    }
