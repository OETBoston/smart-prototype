import json
import uuid
from enum import StrEnum
from typing import Any, Dict

import geopandas as gpd
import pandas as pd

from .policy_defaults import BUS_STOP_POLICY, FIRE_HYDRANT_POLICY


# Configuration
class Direction(StrEnum):
    TOWARD = "TOWARD"
    AWAY = "AWAY"


def run_policy_pass(events_df: gpd.GeoDataFrame) -> pd.DataFrame:
    """Runs a directional pass to determine active policies for each segment.

    Args:
        events_df: A GeoDataFrame containing ordered 'segment' and 'arrow' events
            with columns ['type', 'id', 'policy', 'direction', 'geometry'].

    Returns:
        pd.DataFrame: A dataframe with columns ['segment', 'policy', 'priority'].
    """
    results = []
    active_policies: Dict[str, Any] = {}  # policy_id -> geometry

    for _, row in events_df.iterrows():
        pol = json.dumps(row["policy"])
        if row["type"] == "segment":
            for policy_str, _ in active_policies.items():
                parsed_policy = json.loads(policy_str)
                priority = parsed_policy.get("priority")
                results.append(
                    {
                        "segment": row["id"],
                        "policy": parsed_policy,
                        "priority": priority,
                    }
                )
        elif row["type"] == "arrow":
            direct, geom = row["direction"], row["geometry"]
            if direct == Direction.TOWARD:
                active_policies.pop(pol, None)
            elif direct == Direction.AWAY:
                active_policies[pol] = geom

    return pd.DataFrame(results, columns=["segment", "policy", "priority"])


def generate_event_log(
    df_block: pd.DataFrame,
    df_location_policies: pd.DataFrame,
    is_left_side_oneway: bool,
    feature_lookup: Dict[uuid.UUID, str],
) -> pd.DataFrame:
    """Sequences physical assets and curb segments into an ordered table.

    Args:
        df_block: Dataframe of segments for a specific blockface.
        df_location_policies: Merged dataframe of locations, signs,
            meters, and policies.
        is_left_side_oneway: Boolean indicating if the blockface is
            one-way w/ signs on LHS.
        feature_lookup: A mapping of asset_location_id to feature_type
            (e.g., 'fire_hydrant', 'bus_stop').

    Returns:
        pd.DataFrame: A table of events with columns [type, id, policy, direction].
    """
    event_log = []

    def _append_arrow_events(
        loc_id: uuid.UUID, pol_json: str, pol_arrow: str
    ) -> pd.DataFrame | None:
        """Internal helper to map physical arrows to logical toward/away events."""
        if pol_arrow is None or pd.isna(pol_arrow) or pol_arrow == "both":
            event_log.append(["arrow", loc_id, pol_json, Direction.TOWARD])
            event_log.append(["arrow", loc_id, pol_json, Direction.AWAY])
        elif pol_arrow == "left":
            event_log.append(
                [
                    "arrow",
                    loc_id,
                    pol_json,
                    Direction.TOWARD if is_left_side_oneway else Direction.AWAY,
                ]
            )
        elif pol_arrow == "right":
            event_log.append(
                [
                    "arrow",
                    loc_id,
                    pol_json,
                    Direction.AWAY if is_left_side_oneway else Direction.TOWARD,
                ]
            )
        elif pol_arrow == Direction.TOWARD or pol_arrow == Direction.AWAY:
            event_log.append(["arrow", loc_id, pol_json, pol_arrow])
        else:
            raise ValueError(f"Unknown policy_arrow value: {pol_arrow}")

    flag_fire_hydrant = False
    flag_bus_stop = False

    for index, row in df_block.iterrows():
        # Handle segments without any associated asset
        if row["upstream_loc_list"] is None and row["downstream_loc_list"] is None:
            event_log.append(["segment", row["segment_id"], None, None])
            continue

        # Process Upstream (Start of block logic)
        if index == 0 and row["upstream_loc_list"]:
            for loc in row["upstream_loc_list"]:
                loc_policies = df_location_policies[
                    (df_location_policies["asset_location_id"] == loc)
                    & (~pd.isna(df_location_policies["policy_json"]))
                ]
                for _, p_row in loc_policies.iterrows():
                    _append_arrow_events(
                        loc, p_row["policy_json"], p_row["policy_arrow"]
                    )

        # Process Segment
        event_log.append(["segment", row["segment_id"], None, None])

        # Process Downstream
        if row["downstream_loc_list"]:
            for loc in row["downstream_loc_list"]:
                # Handle fire hydrant or bus stop segments
                if feature_lookup.get(loc, "") == "fire_hydrant":
                    if not flag_fire_hydrant:
                        event_log.extend(
                            [["arrow", loc, FIRE_HYDRANT_POLICY, Direction.AWAY]]
                        )
                        flag_fire_hydrant = True
                    else:
                        event_log.extend(
                            [["arrow", loc, FIRE_HYDRANT_POLICY, Direction.TOWARD]]
                        )
                        flag_fire_hydrant = False

                elif feature_lookup.get(loc, "") == "bus_stop":
                    if not flag_bus_stop:
                        event_log.extend(
                            [["arrow", loc, BUS_STOP_POLICY, Direction.AWAY]]
                        )
                        flag_bus_stop = True
                    else:
                        event_log.extend(
                            [["arrow", loc, BUS_STOP_POLICY, Direction.TOWARD]]
                        )
                        flag_bus_stop = False
                else:
                    loc_policies = df_location_policies[
                        (df_location_policies["asset_location_id"] == loc)
                        & (~pd.isna(df_location_policies["policy_json"]))
                    ]
                    for _, p_row in loc_policies.iterrows():
                        _append_arrow_events(
                            loc, p_row["policy_json"], p_row["policy_arrow"]
                        )

    return pd.DataFrame(event_log, columns=["type", "id", "policy", "direction"])
