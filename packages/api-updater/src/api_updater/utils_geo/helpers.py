import uuid

import geopandas as gpd
import pandas as pd
from shapely import wkb
from shapely.ops import linemerge


def consolidate_curb_segments(
    curb_segments: pd.DataFrame, curb_segment_policies: pd.DataFrame
) -> pd.DataFrame:
    if curb_segments.empty or curb_segment_policies.empty:
        raise ValueError(
            "Input segment or policy table is empty; nothing to transform."
        )

    # Convert WKB geometries to Shapely objects
    curb_segments["geography"] = curb_segments["geography"].apply(
        lambda x: wkb.loads(x, hex=True)
    )

    # Merge the tables to align policies with their geometries
    df = pd.merge(
        curb_segment_policies[["segment_id", "policy_list"]],
        curb_segments[["segment_id", "blockface_id", "geography", "segment_seq"]],
        on="segment_id",
        how="left",
    )

    # Sort by blockface_id and segment_seq to ensure proper ordering for merging
    df = df.sort_values(["blockface_id", "segment_seq"]).reset_index(drop=True)
    # Create a policy key for comparison
    df["policy_key"] = df["policy_list"].apply(lambda x: str(x))

    # Create a marker that increments whenever the blockface_id OR policy changes
    condition = (df["policy_key"] != df["policy_key"].shift()) | (
        df["blockface_id"] != df["blockface_id"].shift()
    )
    df["adj_group"] = condition.cumsum()

    # Define aggregation functions for merging geometries
    agg_func = {
        "blockface_id": "first",
        "policy_list": "first",
        "geography": lambda x: linemerge(list(x)),
    }

    # Perform the merge
    df_merged = df.groupby("adj_group").agg(agg_func).reset_index(drop=True)

    # Assign a unique curb_zone_id to each merged segment
    df_merged["curb_zone_id"] = [uuid.uuid4() for _ in range(len(df_merged))]

    return df_merged


def get_linear_intersections(
    target_line, gdf: gpd.GeoDataFrame, geo_col="geometry"
) -> gpd.GeoDataFrame:
    # 1. Spatial Filter: Find anything that touches/intersects at all
    # This uses the spatial index for performance
    possible_matches = gdf[gdf.intersects(target_line)].copy()

    if possible_matches.empty:
        return possible_matches

    # 2. Dimension Check:
    def is_linear_intersection(geom, target) -> bool:
        # Calculate the actual shared geometry
        inter = geom.intersection(target)

        # Check if the shared part is a LineString or MultiLineString
        # This effectively checks for Dimension 1
        return inter.geom_type in ["LineString", "MultiLineString"]

    mask = possible_matches[geo_col].apply(
        lambda x: is_linear_intersection(x, target_line)
    )

    return possible_matches[mask]
