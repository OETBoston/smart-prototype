"""
==============================================================================
Curb Segmentation Module
==============================================================================
This module implements the core logic for detecting and segmenting curbs.
It contains algorithms and utilities that perform feature snapping,
segmentation point detection, inference, and post-processing to accurately
identify curb boundaries.

The module is designed to provide helper functions and APIs for relevant
processing. Parameters controlling model behavior and thresholds are defined
in `config.yaml`.
==============================================================================
"""

# Packages
# ==============================================================================
import uuid
import warnings
from collections import defaultdict
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
from curb_utils.logging import get_logger
from rtree import index
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, substring, unary_union

warnings.filterwarnings("ignore")


# Functions
# ==============================================================================


def check_and_set_crs(gdf: gpd.GeoDataFrame, proj_crs: str) -> gpd.GeoDataFrame:
    """
    Check if a GeoDataFrame contains a valid CRS.
    """
    target = pyproj.CRS.from_user_input(proj_crs)

    if gdf.crs:
        if pyproj.CRS.from_user_input(gdf.crs) != target:
            gdf = gdf.to_crs(target)
    else:
        gdf = gdf.set_crs(target)

    return gdf


def confirm_gdf(gdf: gpd.GeoDataFrame):
    """
    Checks if the provided object is a GeoDataFrame.

    This function verifies that the input object is an instance of GeoPandas' GeoDataFrame.
    If the input does not match the expected type, a TypeError is raised.

    Args:
        gdf: The input objects to be validated.

    Raises:
        TypeError: If the provided object is not a GeoDataFrame.
    """
    if not isinstance(gdf, gpd.GeoDataFrame):
        raise TypeError("Curb dataset is not a GeoDataFrame.")
    else:
        pass


def convert_point_to_line(geom):
    """Convert a Point geometry to a LineString geometry."""
    if geom.geom_type == "Point":
        return LineString([geom.coords[0], geom.coords[0]])
    return geom


def keep_tuple_item(series: pd.Series, position: str = "first") -> pd.Series:
    """
    Maps a Pandas Series, extracting either the first or the last item from each
    tuple. Non-tuple values in the Series are returned unchanged.

    Args:
        series (pandas.Series): The input series whose tuples will be mapped.
        position (str): Determines whether to select the first or the last element
            of the tuple. Use "first" to select the first element, or "last" to
            select the last element. Defaults to "first".

    Returns:
        pandas.Series: A Series containing the extracted tuple items, or unchanged
        values for non-tuple elements.

    Raises:
        ValueError: If the `position` is not "first" or "last".
    """

    if position not in ("first", "last"):
        raise ValueError("position must be 'first' or 'last'")

    ix = 0 if position == "first" else -1

    return series.map(lambda x: x[ix] if isinstance(x, tuple) else x)


def raise_if_tuple(series: pd.Series, column_name: str | None = None) -> None:
    """
    Checks if a Pandas Series contains tuple values and raises a ValueError if found.

    Args:
        series (pd.Series): The Pandas Series to check for tuple values.
        column_name (str, optional): An optional name to represent the column for
        error messaging. Defaults to None.

    Raises:
        ValueError: Raised if the Series contains any tuple values.
    """
    if series.apply(lambda x: isinstance(x, tuple)).any():
        name = column_name or series.name or "column"
        raise ValueError(f"{name} contains tuple values.")


def nan_to_none(df: pd.DataFrame | gpd.GeoDataFrame) -> pd.DataFrame | gpd.GeoDataFrame:
    """
    Replace NaN / NaT with None in a Pandas DataFrame.
    """
    return df.where(pd.notna(df), None)


def length_in_feet(geom, crs) -> float | None:
    """
    Calculate geometry length in feet without changing CRS.
    """
    if geom is None or geom.is_empty:
        return None

    if crs is None:
        return geom.length

    try:
        crs_obj = pyproj.CRS.from_user_input(crs)
    except pyproj.exceptions.CRSError:
        return geom.length

    if crs_obj.is_geographic:
        try:
            geod = pyproj.Geod.from_crs(crs_obj, crs_obj)
        except Exception:
            try:
                ellps_name = crs_obj.ellipsoid.name or "WGS84"
                geod = pyproj.Geod(ellps=ellps_name)
            except Exception:
                geod = pyproj.Geod(ellps="WGS84")
        meters = geod.geometry_length(geom)
        return round(meters * 3.280839895, 2)

    unit_name = None
    if crs_obj.axis_info:
        unit_name = (crs_obj.axis_info[0].unit_name or "").lower()

    if unit_name in {"foot", "us_survey_foot", "foot_us", "ft"}:
        return round(geom.length, 2)
    if unit_name in {"metre", "meter", "m"}:
        return round(geom.length * 3.280839895, 2)

    return round(geom.length, 2)


def add_upstream_downstream_assets(
    curb_segments: pd.DataFrame,
    asset_dict: dict[str, gpd.GeoDataFrame],
    upstream_col: str = "upstream_location",
    downstream_col: str = "downstream_location",
) -> pd.DataFrame:
    """
    Add upstream_asset and downstream_asset columns based on asset ID lookups.

    Asset priority order: parking sign (PS), fire hydrant (FH), bus stop (BS), meter policy (MP).
    """
    ps = asset_dict.get("parking_sign")
    fh = asset_dict.get("fire_hydrant")
    bs = asset_dict.get("bus_stop")
    mp = asset_dict.get("meter_policies")

    ps_ids = (
        set(ps["ps_id"].dropna()) if ps is not None and "ps_id" in ps.columns else set()
    )
    fh_ids = (
        set(fh["fh_id"].dropna()) if fh is not None and "fh_id" in fh.columns else set()
    )
    bs_ids = (
        set(bs["bs_id"].dropna()) if bs is not None and "bs_id" in bs.columns else set()
    )
    mp_ids = (
        set(mp["mp_id"].dropna()) if mp is not None and "mp_id" in mp.columns else set()
    )

    def lookup_asset(value):
        if pd.isna(value):
            return None
        if value in ps_ids:
            return "PS"
        if value in fh_ids:
            return "FH"
        if value in bs_ids:
            return "BS"
        if value in mp_ids:
            return "MP"
        return None

    out = curb_segments.copy()
    crs = getattr(curb_segments, "crs", None)
    if "geography" in out.columns:
        out["seg_length"] = out["geography"].apply(lambda g: length_in_feet(g, crs))
    out["upstream_asset"] = out[upstream_col].map(lookup_asset)
    out["downstream_asset"] = out[downstream_col].map(lookup_asset)
    return out


def clean_curb_geometries(
    curb_lines: gpd.GeoDataFrame,
    min_curb_len_ft: float = 2.0,
    eps_fraction: float = 1e-6,
) -> gpd.GeoDataFrame:
    """
    Clean and preprocess curb LineStrings for the segmentation process.
    Assumes input CRS is already projected (in feet).

    Steps:
    1. Drop invalid or empty geometries.
    2. Ensure required columns are present in the curb dataset.
    3. Compute curb lengths (in feet).
    4. Drop very short segments below min_curb_len_ft.
    5. Perform QA summary.

    Args:
        curb_lines (GeoDataFrame): Input curb geometries with "geometry" column (LineString or MultiLineString).
        min_curb_len_ft (float): Minimum curb length (feet) to keep (default: 2.0).
        eps_fraction (float): Small tolerance for floating point precision (default: 1e-6).

    Returns:
        curbs_clean (gpd.GeoDataFrame): Cleaned curb geometries.
    """

    logger = get_logger(__name__)

    curbs_clean = curb_lines.copy()
    total_before = len(curbs_clean)

    # Check if curb dataset is already in GeoDataFrame
    confirm_gdf(curbs_clean)

    # Rename the geometry column to "geometry"
    if curbs_clean.geometry.name != "geometry":
        curbs_clean = curbs_clean.rename_geometry("geometry")

    # Ensure required columns are present in curb dataset
    required_columns = ["blockface_id", "is_left_side_oneway", "geometry"]

    missing_columns = [c for c in required_columns if c not in curbs_clean.columns]

    if missing_columns:
        raise KeyError(
            f"Curb dataset is missing these required columns: {missing_columns}"
        )

    # Check if curb IDs are duplicated
    if curbs_clean["blockface_id"].duplicated().any():
        logger.info(
            "'blockface_id' column has duplicate IDs. Removing duplicate IDs..."
        )
        curbs_clean = curbs_clean.drop_duplicates(subset=["blockface_id"], keep="first")

    # Check if any geometry is not a LineString
    if not curbs_clean.geometry.geom_type.eq("LineString").all():
        raise ValueError("Curb dataset contains non-LineString geometries.")

    # Drop invalid/empty
    curbs_clean = curbs_clean[curbs_clean.is_valid & ~curbs_clean.is_empty].copy()
    invalid_count = total_before - len(curbs_clean)

    # Compute lengths
    if "curb_length_ft" not in curbs_clean.columns:
        curbs_clean["curb_length_ft"] = curbs_clean.geometry.length

    # Drop short segments
    short_segments = curbs_clean[
        curbs_clean["curb_length_ft"] < (min_curb_len_ft - eps_fraction)
    ]
    curbs_clean = curbs_clean[
        curbs_clean["curb_length_ft"] >= (min_curb_len_ft - eps_fraction)
    ].copy()
    curbs_clean.reset_index(drop=True, inplace=True)
    curbs_clean["segment_length_ft"] = curbs_clean["curb_length_ft"]
    # Reduce columns; dropped columns can be merged again from the initial curb DataFrame
    columns_to_keep = [
        "blockface_id",
        "is_left_side_oneway",
        "curb_length_ft",
        "segment_length_ft",
        "geometry",
    ]

    # QA Summary
    logger.debug("=== Curb Cleaning Summary ===")
    logger.debug(f"Input features:         {total_before:,}")
    logger.debug(f"Invalid/empty dropped:  {invalid_count:,}")
    logger.debug(
        f"Short segments dropped: {len(short_segments):,} (< {min_curb_len_ft} ft)",
    )
    # log info is intentional here
    logger.info(f"Final valid curbs:      {len(curbs_clean):,}")
    logger.debug(f"Average length (ft):    {curbs_clean['curb_length_ft'].mean():.2f}")
    logger.debug("==============================")

    return curbs_clean[columns_to_keep]


def snap_points_to_curbs(
    points_clean: gpd.GeoDataFrame,
    points_id_col: str,
    curbs_clean: gpd.GeoDataFrame,
    curb_id_col: str,
    snap_tolerance_ft: float = 25,
    proj_crs: str = "epsg:2249",
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Snap points to the nearest curb lines within a specified tolerance.

    Args:
        points_clean (GeoDataFrame): Clean points (FH signs).
        points_id_col (str): Column name of point ID.
        curbs_clean (GeoDataFrame): Clean curbs.
        curb_id_col (str): Column name of curb ID.
        snap_tolerance_ft (float): Maximum snapping tolerance in feet.
        proj_crs (CRS): Projection CRS.

    Returns:
        projected_points (gpd.GeoDataFrame): GeoDataFrame of snapped points.
        unsnapped_sign_ids (gpd.GeoDataFrame): GeoDataFrame of original points
            that could not be snapped.
    """

    logger = get_logger(__name__)

    # Check CRS
    points_clean = check_and_set_crs(points_clean, proj_crs)
    curbs_clean = check_and_set_crs(curbs_clean, proj_crs)

    # Build spatial index for curbs
    logger.info("Building spatial index for curbs...")
    curb_idx = index.Index()
    for pos, (_, curb) in enumerate(curbs_clean.iterrows()):
        curb_idx.insert(pos, curb.geometry.bounds)

    # Initialize lists to store results
    snapped_data = []
    unsnapped_ids = []

    logger.info(f"Snapping {len(points_clean):,} points to curbs...")

    for _, point_row in points_clean.iterrows():
        point_geom = point_row["geometry"]
        point_id = point_row[points_id_col]

        # Get candidate curbs via bbox query (extended by snap tolerance)
        search_bounds = (
            point_geom.x - snap_tolerance_ft,
            point_geom.y - snap_tolerance_ft,
            point_geom.x + snap_tolerance_ft,
            point_geom.y + snap_tolerance_ft,
        )

        candidate_curb_indices = list(curb_idx.intersection(search_bounds))

        if not candidate_curb_indices:
            unsnapped_ids.append(point_id)
            continue

        # Find the minimum distance and corresponding curb
        min_dist = float("inf")
        best_curb_id = None
        best_projected_point = None
        best_fraction = None
        best_curb_length = None

        for curb_idx_val in candidate_curb_indices:
            curb_row = curbs_clean.iloc[curb_idx_val]
            curb_geom = curb_row["geometry"]
            curb_id = curb_row[curb_id_col]

            # Project point to curb line and get distance
            projected = curb_geom.interpolate(curb_geom.project(point_geom))
            distance = point_geom.distance(projected)

            if distance < min_dist:
                min_dist = distance
                best_curb_id = curb_id
                best_projected_point = projected

                # Calculate the fraction along the line
                line_length = curb_geom.length
                best_fraction = (
                    curb_geom.project(point_geom) / line_length
                    if line_length > 0
                    else 0
                )
                best_curb_length = line_length

        # Check if the minimum distance is within snap tolerance
        if min_dist <= snap_tolerance_ft:
            snapped_data.append(
                {
                    points_id_col: point_id,
                    curb_id_col: best_curb_id,
                    "segment_length_ft": best_curb_length,
                    "projected_fraction": best_fraction,
                    "distance_ft": min_dist,
                    "geometry": best_projected_point,
                }
            )
        else:
            unsnapped_ids.append(point_id)

    # Create projected points GeoDataFrame
    if snapped_data:
        projected_points_df = gpd.GeoDataFrame(
            snapped_data, geometry="geometry", crs=points_clean.crs
        )
    else:
        # Create empty GeoDataFrame with correct schema
        projected_points_df = gpd.GeoDataFrame(
            columns=[
                points_id_col,
                curb_id_col,
                "segment_length_ft",
                "projected_fraction",
                "distance_ft",
                "geometry",
            ],
            geometry="geometry",
            crs=points_clean.crs,
        )

    unsnapped_points_df = points_clean[points_clean[points_id_col].isin(unsnapped_ids)]

    logger.info(f"Snapped points: {len(projected_points_df):,}")
    logger.info(f"Unsnapped points: {len(unsnapped_ids):,}")

    return projected_points_df.reset_index(drop=True), unsnapped_points_df.reset_index(
        drop=True
    )


def calculate_fractions_for_fh_buffer_zones(
    projected_points: gpd.GeoDataFrame,
    points_id_col: str,
    curb_id_col: str,
    buffer_distance_ft: float,
) -> tuple[dict[int | str, list[float]], pd.DataFrame]:
    """
    For each curb:
      * Compute buffer intervals [start_fraction, end_fraction] around each projected point.
      * Detect regions where at least 2 buffers overlap (coverage count >= 2).
      * On that curb:
          - If no overlap anywhere:
              - Fractions = all unique interval starts/ends + {0.0, 1.0}.
          - If there is overlap:
              - Build one or more disjoint "overlap clusters" along [0,1].
              - For each cluster, take the envelope of all intervals that
                participate in that cluster: env_min = min(start), env_max = max(end) over those intervals.
              - Collapse boundaries strictly inside each envelope, while keeping:
                    * all boundaries <= env_min or >= env_max,
                    * env_min and env_max themselves,
                    * 0.0 and 1.0.

    As a result:
      * Non-overlapping buffer edges are preserved.
      * Overlapping groups of buffers are represented by the outermost
        min / max fraction of the buffers that participate in each group.

    Returns:
        fractions_dict: {curb_id: sorted list of fractions}
        fractions_df: DataFrame with columns [curb_id_col, "fractions", "num_fractions"]
    """
    logger = get_logger(__name__)
    logger.info(
        "Calculating fractions for buffer zones (with multi-cluster overlap envelopes)...",
    )

    # Validate inputs
    if buffer_distance_ft <= 0:
        raise ValueError("Buffer distance must be positive.")

    required_columns = [
        points_id_col,
        curb_id_col,
        "projected_fraction",
        "segment_length_ft",
    ]
    missing_columns = [
        col for col in required_columns if col not in projected_points.columns
    ]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    # Check for invalid fractions
    invalid_fractions = projected_points[
        (projected_points["projected_fraction"] < 0)
        | (projected_points["projected_fraction"] > 1)
    ]
    if len(invalid_fractions) > 0:
        logger.warning(
            f"Warning: {len(invalid_fractions):,} points have fraction outside [0,1] range."
        )
        raise ValueError("Invalid fractions found.")

    # First pass: compute intervals per curb: curb_id -> list[(start_fraction, end_fraction)]
    curb_intervals: dict[int | str, list[tuple[float, float]]] = defaultdict(list)
    stats = {"points_processed": 0, "curbs_updated": 0, "curbs_reused": 0}
    seen_curbs = set()

    for _, point in projected_points.iterrows():
        curb_id = point[curb_id_col]
        curb_length = point["segment_length_ft"]
        point_fraction = point["projected_fraction"]

        # Skip if invalid data
        if curb_length <= 0 or point_fraction < 0 or point_fraction > 1:
            logger.debug(f"Skipping point {point[points_id_col]} with invalid data")
            continue

        # Compute buffer-edge fractions
        start_fraction = (
            curb_length * point_fraction - buffer_distance_ft
        ) / curb_length
        end_fraction = (curb_length * point_fraction + buffer_distance_ft) / curb_length

        # Clamp to [0, 1]
        start_fraction = max(0.0, start_fraction)
        end_fraction = min(1.0, end_fraction)

        # Ensure start <= end
        if end_fraction < start_fraction:
            start_fraction, end_fraction = end_fraction, start_fraction

        curb_intervals[curb_id].append((start_fraction, end_fraction))

        stats["points_processed"] += 1
        if curb_id not in seen_curbs:
            seen_curbs.add(curb_id)
            stats["curbs_updated"] += 1
        else:
            stats["curbs_reused"] += 1

    # Second pass: per curb, detect overlap clusters and build final fractions
    fractions_dict: dict[int | str, list[float]] = {}

    for curb_id, intervals in curb_intervals.items():
        if not intervals:
            fractions_dict[curb_id] = [0.0, 1.0]
            continue

        # All raw fraction boundaries (starts/ends) + 0 & 1
        raw_fracs = {0.0, 1.0}
        for s, e in intervals:
            raw_fracs.add(s)
            raw_fracs.add(e)

        # Sweep-line events for coverage count
        events = []
        for s, e in intervals:
            events.append((s, 1))  # interval starts
            events.append((e, -1))  # interval ends
        events.sort()

        count = 0
        prev_pos = None
        overlap_segments: list[tuple[float, float]] = []

        # Step 1: collect segments where coverage counts >= 2
        for pos, delta in events:
            if prev_pos is not None and pos > prev_pos and count >= 2:
                overlap_segments.append((prev_pos, pos))
            count += delta
            prev_pos = pos

        if not overlap_segments:
            # No overlap anywhere on this curb: keep all raw boundaries
            fractions_dict[curb_id] = sorted(raw_fracs)
            continue

        # Step 2: merge adjacent/overlapping overlap_segments into disjoint clusters
        overlap_segments.sort()
        clusters: list[tuple[float, float]] = []
        cur_start, cur_end = overlap_segments[0]
        for s, e in overlap_segments[1:]:
            if s <= cur_end:
                # Overlapping or touching; extend the current cluster
                cur_end = max(cur_end, e)
            else:
                clusters.append((cur_start, cur_end))
                cur_start, cur_end = s, e
        clusters.append((cur_start, cur_end))

        # Step 3: for each cluster, compute the envelope over participating intervals
        envelopes: list[tuple[float, float]] = []
        for cs, ce in clusters:
            involved = [(s, e) for (s, e) in intervals if e > cs and s < ce]
            env_min = min(s for (s, _) in involved)
            env_max = max(e for (_, e) in involved)
            envelopes.append((env_min, env_max))

        # Step 4: build final fractions
        final_fracs = set(raw_fracs)

        # For each envelope [env_min, env_max], remove interior boundaries and keep envelope edges
        for env_min, env_max in envelopes:
            to_remove = {f for f in final_fracs if env_min < f < env_max}
            final_fracs.difference_update(to_remove)
            final_fracs.add(env_min)
            final_fracs.add(env_max)

        fractions_dict[curb_id] = sorted(final_fracs)

    # Logging / debug summary
    logger.debug(f"Completed: {stats['points_processed']:,} points processed")
    logger.debug(f"Completed: {len(fractions_dict):,} curbs with fraction sets")
    logger.debug(f"Completed: {stats['curbs_reused']:,} curbs reused multiple times")
    logger.debug(
        "Completed: Average "
        f"{sum(len(f) for f in fractions_dict.values()) / max(len(fractions_dict), 1):.1f} "
        "fractions/curb",
    )

    # Convert to DataFrame
    fractions_df = pd.DataFrame(
        [
            {
                curb_id_col: curb_id,
                "fractions": fractions,
                "num_fractions": len(fractions),
            }
            for curb_id, fractions in fractions_dict.items()
        ]
    )

    return fractions_dict, fractions_df


def collapse_fire_hydrant_ids(
    gdf: gpd.GeoDataFrame,
    fh_col: str = "fh_id",
    sort_ids: bool = True,
    empty_as_none: bool = True,
) -> gpd.GeoDataFrame:
    """
    Collapse fh_id values into a list whenever all other fields are identical.
    Geometry is preserved; for each group we keep the first geometry.
    """
    geom_col = gdf.geometry.name

    # Group by all non-fh_id columns (including geometry, considering strict equality)
    group_cols = [c for c in gdf.columns if c != fh_col]

    def agg_fh(series: pd.Series):
        vals = series.dropna().unique().tolist()
        if sort_ids:
            vals = sorted(vals)
        if not vals:
            return None if empty_as_none else ()
        return tuple(vals)

    grouped = gdf.groupby(group_cols, dropna=False, as_index=False).agg(
        {fh_col: agg_fh}
    )

    # Ensure we get back a GeoDataFrame with the correct geometry column
    grouped = gpd.GeoDataFrame(grouped, geometry=geom_col, crs=gdf.crs)
    return grouped


def create_curb_segments_with_fh_point_buffer(
    curbs_clean: gpd.GeoDataFrame,
    curb_id_col: str,
    fraction_dict: dict[int, list[float]],
    projected_points: gpd.GeoDataFrame,
    points_id_col: str,
    seg_prefix: str,
    point_id_cols: list,
    min_segment_len_ft: float = 1.0,
) -> gpd.GeoDataFrame | None:
    """
    Create curb segments using fractions for point buffer boundaries.

    Args:
        curbs_clean (gpd.GeoDataFrame): Cleaned curb geometries.
        curb_id_col (str): Column name of curb ID.
        fraction_dict (dict[int, list[float]]): Fractions for buffer boundaries for each curb.
        projected_points (gpd.GeoDataFrame): Projected point geometries.
        points_id_col (str): Column name of point ID.
        seg_prefix (str): Prefix string for segment name.
        point_id_cols (list): List of points_id_cols to be brought to final df.
        min_segment_len_ft (float, optional): Minimum length of curb segments.

    Returns:
        A geopandas GeoDataFrame containing the curb segments.
    """
    logger = get_logger(__name__)

    # Filter curbs to only those in fraction_dict
    selected_curb_ids = list(fraction_dict.keys())
    selected_curbs = curbs_clean[
        curbs_clean[curb_id_col].isin(selected_curb_ids)
    ].copy()

    logger.info(f"Processing {len(selected_curbs):,} curbs with fraction sets...")

    segments_data = []
    point_assignments = []

    stats = {
        "total_segments_created": 0,
        "segments_filtered_out": 0,
        "points_assigned": 0,
        "curbs_processed": 0,
    }

    for _, curb_row in selected_curbs.iterrows():
        curb_id = curb_row[curb_id_col]

        # Get fractions for this curb
        fractions = fraction_dict.get(curb_id, [])

        if len(fractions) < 2:
            continue

        stats["curbs_processed"] += 1
        curb_points_assigned = 0
        segment_id_counter = 1

        # Create consecutive fraction pairs
        for i in range(len(fractions) - 1):
            start_frac = fractions[i]
            end_frac = fractions[i + 1]

            if_skip, segment_length_ft, segment_geom = find_segment_length(
                curb_row=curb_row,
                start_frac=start_frac,
                end_frac=end_frac,
                stats=stats,
                min_segment_len_ft=min_segment_len_ft,
                drop_tiny_segments=True,
            )

            if if_skip:
                continue

            # Create segment records
            segment_record = {
                "segment_id": f"{seg_prefix}{segment_id_counter}",
                curb_id_col: curb_id,
                "start_fraction": start_frac,
                "end_fraction": end_frac,
                "segment_length_ft": segment_length_ft,
                "is_left_side_oneway": curb_row["is_left_side_oneway"],
                "geometry": segment_geom,
            }
            for col in point_id_cols:
                segment_record[col] = curb_row[col]

            segments_data.append(segment_record)

            # Find points that fall in this segment
            curb_points = projected_points[projected_points[curb_id_col] == curb_id]
            for _, point in curb_points.iterrows():
                point_frac = point["projected_fraction"]
                if start_frac <= point_frac <= end_frac:
                    point_assignments.append(
                        {
                            points_id_col: point[points_id_col],
                            "segment_id": f"{seg_prefix}{segment_id_counter}",
                            curb_id_col: curb_id,
                            f"{points_id_col}_fraction": point_frac,
                        }
                    )
                    curb_points_assigned += 1
                    stats["points_assigned"] += 1

            segment_id_counter += 1
            stats["total_segments_created"] += 1

    # Create outputs
    if segments_data:
        segments_gdf = gpd.GeoDataFrame(
            segments_data, geometry="geometry", crs=curbs_clean.crs
        )
    else:
        segments_gdf = gpd.GeoDataFrame(
            columns=[
                "segment_id",
                curb_id_col,
                "start_fraction",
                "end_fraction",
                "segment_length_ft",
                "is_left_side_oneway",
                "geometry",
            ],
            geometry="geometry",
            crs=curbs_clean.crs,
        )

    point_assignments_df = pd.DataFrame(point_assignments)

    # Print statistics
    log_segment_process(stats)

    # Validation
    pt_df_len = len(point_assignments_df)
    if pt_df_len > 0:
        unique_point_assignments = len(point_assignments_df[points_id_col].unique())
        if unique_point_assignments != pt_df_len:
            logger.info(
                f"VALIDATION ISSUE: {pt_df_len - unique_point_assignments} duplicate point assignments!"
            )
        else:
            logger.info("All points assigned to exactly one segment")

    # Merge point information to segments
    point_id_cols.append(points_id_col)
    if (len(segments_gdf) > 0) & (pt_df_len > 0):
        segments_gdf = segments_gdf.merge(
            point_assignments_df, on=[curb_id_col, "segment_id"], how="left"
        )

        # Use null-able integer data type
        # segments_gdf[points_id_col] = segments_gdf[points_id_col].astype("Int64")

        segments_gdf = segments_gdf[
            [
                curb_id_col,
                "segment_id",
                "segment_length_ft",
                "is_left_side_oneway",
                "geometry",
            ]
            + point_id_cols
        ]
        segments_gdf = add_curbs_not_segmented_by_point(
            curb_segments=segments_gdf,
            curbs_clean=curbs_clean,
            curb_id_col=curb_id_col,
            points_id_col=points_id_col,
            seg_prefix=seg_prefix,
        )
        # Collapse fh_id values into a list whenever all other fields are identical.
        # This applies to the cases where fire hydrant buffer zones overlap.
        segments_gdf = collapse_fire_hydrant_ids(segments_gdf)

        # Keep just one Fire Hydrant ID per segment.
        # When overlapping buffer zones are present, we keep the first one.
        # Those fire hydrant zones will have a longer length. It should not impact downstream processes.
        segments_gdf[points_id_col] = keep_tuple_item(
            segments_gdf[points_id_col], "first"
        )

        logger.info(
            f"Total segments after segmentation by fire hydrant: {len(segments_gdf):,}"
        )
        return segments_gdf
    else:
        return None


def add_curbs_not_segmented_by_point(
    curb_segments: pd.DataFrame,
    curbs_clean: gpd.GeoDataFrame,
    curb_id_col: str,
    points_id_col: str,
    seg_prefix: str,
) -> gpd.GeoDataFrame:
    """
    Add the curbs that are not segmented to create a comprehensive curb segment dataset.
    The whole curb is considered as a single segment (e.g., FS1).

    Args:
        curb_segments (gpd.DataFrame): Curb segments GeoDataFrame.
        curbs_clean (gpd.GeoDataFrame): Clean curb GeoDataFrame.
        curb_id_col (str): Column name of curb ID.
        points_id_col (str): Column name of point ID.
        seg_prefix (str): Prefix of curb segment ID.

    Returns:
        A geopandas GeoDataFrame containing the all curb segments (segmented and whole).

    """
    logger = get_logger(__name__)

    # Create new columns for the curbs that are not segmented
    curbs_not_segmented = curbs_clean[
        ~curbs_clean[curb_id_col].isin(curb_segments[curb_id_col].unique())
    ].copy()

    if len(curbs_not_segmented) > 0:
        logger.info(
            f"{len(curbs_not_segmented):,} curbs were not segmented. "
            f"Each of them were added as a single segment..."
        )

    if "segment_length_ft" not in curbs_not_segmented.columns:
        curbs_not_segmented["segment_length_ft"] = curbs_not_segmented[
            "segment_length_ft"
        ]
    curbs_not_segmented["segment_id"] = f"{seg_prefix}1"
    curbs_not_segmented[points_id_col] = pd.Series(
        [np.nan] * len(curbs_not_segmented), dtype="Int64"
    )
    curbs_not_segmented = curbs_not_segmented[curb_segments.columns]

    # Concatenate curb segments with whole curbs which were not segmented.
    curb_segments = pd.concat([curb_segments, curbs_not_segmented])

    curb_segments = curb_segments.sort_values(
        by=[curb_id_col, "segment_id"]
    ).reset_index(drop=True)
    curb_segments = gpd.GeoDataFrame(
        curb_segments, geometry="geometry", crs=curbs_clean.crs
    )

    return curb_segments


def run_segmentation_by_fire_hydrants(
    configuration: dict,
    asset_dict: dict[str, gpd.GeoDataFrame],
    clean_curbs: gpd.GeoDataFrame,
    segment_id_cols: list,
) -> gpd.GeoDataFrame:
    """
    Wrapper function to run segmentation by fire hydrants.

    Args:
        configuration (dict): Dictionary of configuration parameters.
        asset_dict (dict[str, gpd.GeoDataFrame]): Dictionary of asset data.
        clean_curbs (gpd.GeoDataFrame): Cleaned curb GeoDataFrame.
        segment_id_cols (list): List of points_id_cols to be brought to the final df.

    Returns:
        curb_segmentation (gpd.GeoDataFrame):
            Cleaned curb segments after segmentation by fire hydrants
    """
    logger = get_logger(__name__)
    asset_type = "fire_hydrant"
    point_id_col = configuration["assets"][asset_type]["new_id_col"]
    curb_id_col = "blockface_id"
    buffer_distance_ft = configuration["assets"][asset_type]["buffer_distance_ft"]

    logger.info(f"--> Starting curb segmentation by {asset_type.replace('_', ' ')}...")

    # Get the fire hydrants file
    fh = asset_dict[asset_type].copy()

    # Snap fire hydrants to the curb
    snapped_fh, unsnapped_fh = snap_points_to_curbs(
        points_clean=fh,
        points_id_col=point_id_col,
        curbs_clean=clean_curbs,
        curb_id_col=curb_id_col,
        snap_tolerance_ft=configuration["snap_tolerance_ft"],
        proj_crs=configuration["proj_crs"],
    )

    # Calculate fractions for buffer zones
    fractions_dict, fractions_df = calculate_fractions_for_fh_buffer_zones(
        projected_points=snapped_fh,
        points_id_col=point_id_col,
        curb_id_col=curb_id_col,
        buffer_distance_ft=buffer_distance_ft,
    )

    # Create curb segments
    curb_segments = create_curb_segments_with_fh_point_buffer(
        curbs_clean=clean_curbs,
        curb_id_col=curb_id_col,
        fraction_dict=fractions_dict,
        projected_points=snapped_fh,
        points_id_col=point_id_col,
        seg_prefix="FS",
        point_id_cols=segment_id_cols,
        min_segment_len_ft=configuration["min_segment_len_ft"],
    )

    if curb_segments is None or curb_segments.empty:
        logger.info("No curb segments were created; returning empty GeoDataFrame.")
        return gpd.GeoDataFrame(
            columns=[
                f"parent_{curb_id_col}",
                curb_id_col,
                point_id_col,
                "is_left_side_oneway",
                "geometry",
            ],
            geometry="geometry",
            crs=clean_curbs.crs,
        )
    else:
        # Format curb segment DataFrame.
        # Store the main curb ID in the "parent_curb_id" column.
        # Combine curb IDs with segment IDs to create a new curb ID column.
        # New curb ID column will be input for the later processes.
        curb_segments.insert(
            loc=0, column=f"parent_{curb_id_col}", value=curb_segments[f"{curb_id_col}"]
        )
        curb_segments.drop(columns=[curb_id_col], inplace=True)

        curb_segments.insert(
            loc=1,
            column=curb_id_col,
            value=curb_segments[f"parent_{curb_id_col}"].astype(str)
            + ":"
            + curb_segments["segment_id"].astype(str),
        )

        cols_to_keep = [
            f"parent_{curb_id_col}",
            curb_id_col,
            "segment_length_ft",
            "is_left_side_oneway",
            "geometry",
        ] + segment_id_cols

        # Keep relevant columns only
        curb_segments = curb_segments[cols_to_keep]

        # Final checks
        raise_if_tuple(curb_segments, point_id_col)
        curb_segments = nan_to_none(curb_segments)

        return curb_segments


def run_segmentation_by_parking_signs(
    configuration: dict,
    asset_dict: dict[str, gpd.GeoDataFrame],
    clean_curbs: gpd.GeoDataFrame,
    segment_id_cols: list,
) -> gpd.GeoDataFrame:
    """
    Wrapper function to run segmentation by parking signs.

    Args:
        configuration (dict): Dictionary of configuration parameters.
        asset_dict (dict[str, gpd.GeoDataFrame]): Dictionary of asset data.
        clean_curbs (gpd.GeoDataFrame): Cleaned curb GeoDataFrame,
            previously segmented by fire hydrants.
        segment_id_cols (list): List of points_id_cols to be brought to the final df.

    Returns:
        curb_segmentation (gpd.GeoDataFrame):
            Cleaned curb segments after segmentation by parking signs
    """
    logger = get_logger(__name__)
    asset_type = "parking_sign"
    point_id_col = configuration["assets"][asset_type]["new_id_col"]
    curb_id_col = "blockface_id"

    logger.info(f"--> Starting curb segmentation by {asset_type.replace('_', ' ')}...")

    # Get the parking signs file
    ps = asset_dict[asset_type].copy()

    # Snap parking signs to the curb
    snapped_ps, unsnapped_ps = snap_points_to_curbs(
        points_clean=ps,
        points_id_col=point_id_col,
        curbs_clean=clean_curbs,
        curb_id_col=curb_id_col,
        snap_tolerance_ft=configuration["snap_tolerance_ft"],
        proj_crs=configuration["proj_crs"],
    )

    # Create curb segments
    curb_segments = create_curb_segments_with_parking_asset(
        curbs_clean=clean_curbs,
        curb_id_col=curb_id_col,
        fraction_df=snapped_ps,
        points_id_col=point_id_col,
        seg_prefix="PS",
        point_id_cols=segment_id_cols,
        min_segment_len_ft=configuration["min_segment_len_ft"],
    )

    # Final checks
    raise_if_tuple(curb_segments, point_id_col)
    curb_segments = nan_to_none(curb_segments)

    return curb_segments


def create_curb_segments_with_parking_asset(
    curbs_clean: gpd.GeoDataFrame,
    curb_id_col: str,
    fraction_df: gpd.GeoDataFrame,
    points_id_col: str,
    seg_prefix: str,
    point_id_cols: list,
    min_segment_len_ft: float = 1.0,
) -> gpd.GeoDataFrame | None:
    """
    Create curb segments using fractions for parking signs points and parking meter points.

    Args:
        curbs_clean (gpd.GeoDataFrame): Clean curbs segmented by fire hydrants and bus stops.
        curb_id_col (str): Column name of curb ID.
        fraction_df (gpd.GeoDataFrame): GeoDataFrame of snapped parking signs to the curbs,
            including the location of the sign on the curb as a fraction of the curb.
        points_id_col (str): Column name of point ID.
        seg_prefix (str): Prefix string for segment name.
        point_id_cols (list): List of points_id_cols to be brought to final df.
        min_segment_len_ft (float, optional): Minimum length of curb segments.

    Returns:
        A geopandas GeoDataFrame containing the curb segments by parking signs (and fire hydrants).
    """
    logger = get_logger(__name__)
    # Filter curbs to only those in fraction_df
    selected_curb_ids = list(fraction_df[curb_id_col])
    selected_curbs = curbs_clean[curbs_clean[curb_id_col].isin(selected_curb_ids)]
    logger.info(f"Processing {len(selected_curbs):,} curbs with fraction sets...")

    segments_data = []

    stats = {
        "total_segments_created": 0,
        "segments_filtered_out": 0,
        "points_assigned": 0,
        "curbs_processed": 0,
    }

    for _, curb_row in selected_curbs.iterrows():
        curb_id = curb_row[curb_id_col]

        # Get fractions for this curb
        fractions = fraction_df[fraction_df[curb_id_col] == curb_id].copy()

        # check if any breaks in the original segment
        if len(fractions) < 1:
            continue

        # Add the start/end fraction
        fractions.loc[len(fractions)] = [None, curb_id, None, 0.0, None, None]
        fractions = fractions.sort_values("projected_fraction")
        fractions["next_frac"] = fractions["projected_fraction"].shift(-1).fillna(1.0)

        # Get sign at the end of a segment
        fractions["next_sign"] = fractions[points_id_col].shift(-1)

        stats["curbs_processed"] += 1
        segment_id_counter = 1

        # Create consecutive fraction pairs
        for _, frac_row in fractions.iterrows():
            start_frac = frac_row["projected_fraction"]
            end_frac = frac_row["next_frac"]

            if_skip, segment_length_ft, segment_geom = find_segment_length(
                curb_row, start_frac, end_frac, stats, min_segment_len_ft
            )

            if if_skip:
                continue

            # Create segment records
            segment_record = {
                "segment_id": f"{seg_prefix}{segment_id_counter}",
                curb_id_col: curb_id,
                "start_fraction": start_frac,
                "end_fraction": end_frac,
                "segment_length_ft": segment_length_ft,
                f"start_{points_id_col}": frac_row[points_id_col],
                f"end_{points_id_col}": frac_row["next_sign"],
                "is_left_side_oneway": curb_row["is_left_side_oneway"],
                "geometry": segment_geom,
            }
            for col in point_id_cols:
                segment_record[col] = curb_row[col]
            segments_data.append(segment_record)

            segment_id_counter += 1
            stats["total_segments_created"] += 1

    # Create outputs
    for point_col in [f"start_{points_id_col}", f"end_{points_id_col}"]:
        point_id_cols.append(point_col)

    segments_gdf = make_curb_gdf(
        segments_data,
        curbs_clean,
        point_id_cols,
        points_id_col,
        curb_id_col,
        seg_prefix,
        stats,
    )

    logger.info(
        f"Total segments after segmentation by parking asset: {len(segments_gdf):,}"
    )

    return segments_gdf


def run_segmentation_by_bus_stops(
    configuration: dict,
    asset_dict: dict[str, gpd.GeoDataFrame],
    clean_curbs: gpd.GeoDataFrame,
    segment_id_cols: list,
) -> gpd.GeoDataFrame:
    """
    Wrapper function to run segmentation by bus stops.

    Args:
        configuration (dict): Dictionary of configuration parameters.
        asset_dict (dict[str, gpd.GeoDataFrame]): Dictionary of asset data.
        clean_curbs (gpd.GeoDataFrame): Cleaned curb GeoDataFrame.
        segment_id_cols (list): List of points_id_cols to be brought to the final df.

    Returns:
        curb_segmentation (gpd.GeoDataFrame):
            Cleaned curb segments after segmentation by fire hydrants.
    """
    logger = get_logger(__name__)
    asset_type = "bus_stop"
    point_id_col = configuration["assets"][asset_type]["new_id_col"]
    curb_id_col = "blockface_id"

    logger.info(f"--> Starting curb segmentation by {asset_type.replace('_', ' ')}...")

    # Get the bus stops file
    bs = asset_dict[asset_type].copy()

    # Snap bus stops to the curbs previously segmented
    snapped_bs, unsnapped_bs = snap_points_to_curbs(
        points_clean=bs,
        points_id_col=point_id_col,
        curbs_clean=clean_curbs,
        curb_id_col=curb_id_col,
        snap_tolerance_ft=configuration["snap_tolerance_ft"],
        proj_crs=configuration["proj_crs"],
    )

    snapped_bs_with_buffers = find_bus_stop_type(
        snapped_bs,
        configuration["assets"][asset_type],
    )

    curb_segments = create_curb_segments_with_bus_stops(
        curbs_clean=clean_curbs,
        curb_id_col=curb_id_col,
        fraction_df=snapped_bs_with_buffers,
        points_id_col=point_id_col,
        seg_prefix="BS",
        point_id_cols=segment_id_cols,
        min_segment_len_ft=configuration["min_segment_len_ft"],
    )

    # Final checks
    raise_if_tuple(curb_segments, point_id_col)
    curb_segments = nan_to_none(curb_segments)

    return curb_segments


def find_bus_stop_type(
    fraction_df: gpd.GeoDataFrame, asset_type_config: dict
) -> gpd.GeoDataFrame:
    """
    Finds the bus stop type based on the fraction of a curb and finds the bus stop end point.

    Args:
        fraction_df (gpd.GeoDataFrame): GeoDataFrame of bus stops snapped to curb.
        asset_type_config (dict): Dictionary of configuration parameters for bus stops.

    Returns:
        gpd.GeoDataFrame: Updated fraction_df with columns for bus stop start/end.
    """
    labels, conditions = [], []
    buffer_multiplier_lu = {}
    for stop_type, definitions in asset_type_config["stop_types"].items():
        low, high = definitions["range"]
        buffer_multiplier_lu[stop_type] = definitions["buffer_multiplier"]
        if definitions["inclusive"]:
            mask = (fraction_df["projected_fraction"] >= low) & (
                fraction_df["projected_fraction"] <= high
            )
        else:
            mask = (fraction_df["projected_fraction"] > low) & (
                fraction_df["projected_fraction"] < high
            )
        conditions.append(mask)
        labels.append(stop_type)

    fraction_df["stop_type"] = None
    for cond, label in zip(conditions, labels, strict=False):
        fraction_df.loc[cond, "stop_type"] = label

    # Gets buffer distance for the stop type
    fraction_df["buffer_multiplier"] = fraction_df["stop_type"].replace(
        buffer_multiplier_lu
    )
    fraction_df["buffer_distance"] = 75 * fraction_df["buffer_multiplier"]

    # Get buffer distances for each bus stop
    fraction_df["point_a"] = (
        fraction_df["projected_fraction"] * fraction_df["segment_length_ft"]
    )
    # Get valid end points
    fraction_df["point_b"] = (
        fraction_df["point_a"] + fraction_df["buffer_distance"]
    ).apply(lambda x: max(0, x))
    fraction_df["point_b"] = fraction_df.apply(
        lambda x: min(x["point_b"], x["segment_length_ft"]), axis=1
    )
    fraction_df["fraction_b"] = (
        fraction_df["point_b"] / fraction_df["segment_length_ft"]
    )
    fraction_df["start_fraction"] = np.where(
        fraction_df["point_a"] > fraction_df["point_b"],
        fraction_df["fraction_b"],
        fraction_df["projected_fraction"],
    )
    fraction_df["end_fraction"] = np.where(
        fraction_df["point_a"] > fraction_df["point_b"],
        fraction_df["projected_fraction"],
        fraction_df["fraction_b"],
    )
    keep_cols = [
        "bs_id",
        "blockface_id",
        "segment_length_ft",
        "start_fraction",
        "end_fraction",
        "geometry",
    ]
    return fraction_df[keep_cols]


def create_curb_segments_with_bus_stops(
    curbs_clean: gpd.GeoDataFrame,
    curb_id_col: str,
    fraction_df: gpd.GeoDataFrame,
    points_id_col: str,
    seg_prefix: str,
    point_id_cols: list,
    min_segment_len_ft: float = 1.0,
) -> gpd.GeoDataFrame | None:
    """
    Create curb segments using fractions for bus stops.

    Args:
        curbs_clean (gpd.GeoDataFrame): Clean curbs.
        curb_id_col (str): Column name of curb ID.
        fraction_df (gpd.GeoDataFrame): GeoDataFrame of snapped parking signs to the curb,
            including the location of the sign on a curb as a fraction of the curb.
        points_id_col (str): Column name of point ID.
        seg_prefix (str): Prefix string for segment name.
        point_id_cols (list): List of points_id_cols to be brought to final df.
        min_segment_len_ft (float, optional): Minimum length of curb segments.

    Returns:
        A geopandas GeoDataFrame containing the curb segments by bus stops.
    """
    logger = get_logger(__name__)

    # Filter curbs to only those in fraction_df
    selected_curb_ids = list(fraction_df[curb_id_col])
    selected_curbs = curbs_clean[curbs_clean[curb_id_col].isin(selected_curb_ids)]
    logger.info(f"Processing {len(selected_curbs):,} curbs with fraction sets...")

    segments_data = []

    stats = {
        "total_segments_created": 0,
        "segments_filtered_out": 0,
        "points_assigned": 0,
        "curbs_processed": 0,
    }

    for _, curb_row in selected_curbs.iterrows():
        curb_id = curb_row[curb_id_col]

        # Get fractions for this curb
        fractions = fraction_df[fraction_df[curb_id_col] == curb_id].copy()

        # Check if any breaks in the original segment
        if len(fractions) < 1:
            continue

        stats["curbs_processed"] += 1
        segment_id_counter = 1

        # Fill in rows with new intervals if needed for consecutive fractions
        boundaries = (
            [0]
            + fractions["start_fraction"].tolist()
            + fractions["end_fraction"].tolist()
            + [1.0]
        )
        boundaries = sorted(boundaries)
        for i in range(len(boundaries) - 1):
            start_frac = boundaries[i]
            end_frac = boundaries[i + 1]
            match = fractions[fractions["start_fraction"] == start_frac]
            if not match.empty:
                bs_id = match[points_id_col].iloc[0]
            else:
                bs_id = None

            if_skip, segment_length_ft, segment_geom = find_segment_length(
                curb_row=curb_row,
                start_frac=start_frac,
                end_frac=end_frac,
                stats=stats,
                min_segment_len_ft=min_segment_len_ft,
                drop_tiny_segments=True,
            )

            if if_skip:
                continue

            # Create segment records
            segment_record = {
                "segment_id": f"{seg_prefix}{segment_id_counter}",
                curb_id_col: curb_id,
                points_id_col: bs_id,
                "start_fraction": start_frac,
                "end_fraction": end_frac,
                "segment_length_ft": segment_length_ft,
                "is_left_side_oneway": curb_row["is_left_side_oneway"],
                "geometry": segment_geom,
            }
            for col in point_id_cols:
                segment_record[col] = curb_row[col]

            segments_data.append(segment_record)

            segment_id_counter += 1
            stats["total_segments_created"] += 1

    # Create outputs
    point_id_cols.append(points_id_col)

    segments_gdf = make_curb_gdf(
        segments_data,
        curbs_clean,
        point_id_cols,
        points_id_col,
        curb_id_col,
        seg_prefix,
        stats,
    )

    logger.info(f"Total segments after segmentation by bus stop: {len(segments_gdf):,}")

    return segments_gdf


def run_segmentation_by_parking_meters(
    configuration: dict,
    asset_dict: dict[str, gpd.GeoDataFrame],
    clean_curbs: gpd.GeoDataFrame,
    segment_id_cols: list,
) -> gpd.GeoDataFrame:
    """
    Wrapper function to run segmentation by parking meters.

    Args:
        configuration (dict): Dictionary of configuration parameters.
        asset_dict (dict[str, gpd.GeoDataFrame]): Dictionary of asset data.
        clean_curbs (gpd.GeoDataFrame): Cleaned curb GeoDataFrame,
            previously segmented by parking signs, fire hydrants, and bus stops.
        segment_id_cols (list): List of points_id_cols to be brought to the final df.

    Returns:
        curb_segmentation (gpd.GeoDataFrame):
            Cleaned curb segments after segmentation by parking meters
    """
    logger = get_logger(__name__)
    asset_type = "parking_meters"
    point_id_col = configuration["assets"][asset_type]["new_id_col"]
    curb_id_col = "blockface_id"

    logger.info(f"--> Starting curb segmentation by {asset_type.replace('_', ' ')}...")

    # Get the parking meters file
    pm = asset_dict[asset_type].copy()

    # Snap parking meters to the curb
    snapped_pm, unsnapped_pm = snap_points_to_curbs(
        points_clean=pm,
        points_id_col=point_id_col,
        curbs_clean=clean_curbs,
        curb_id_col=curb_id_col,
        snap_tolerance_ft=configuration["snap_tolerance_ft"],
        proj_crs=configuration["proj_crs"],
    )

    # Create curb segments
    curb_segments = create_curb_segments_with_parking_asset(
        curbs_clean=clean_curbs,
        curb_id_col=curb_id_col,
        fraction_df=snapped_pm,
        points_id_col=point_id_col,
        seg_prefix="PM",
        point_id_cols=segment_id_cols,
        min_segment_len_ft=configuration["min_segment_len_ft"],
    )
    return curb_segments


def find_segment_length(
    curb_row: pd.Series,
    start_frac: float,
    end_frac: float,
    stats: dict,
    min_segment_len_ft: float = 1.0,
    drop_tiny_segments: bool = False,
) -> tuple[bool, float, LineString | None]:
    """
    Finds segment lengths for each part of a given curb and the geometries of these segments.

    Args:
        curb_row (pd.Series): A row of data from the curbs GeoDataFrame
        start_frac (float): Decimal between 0 and 1 representing the start of the curb segment.
        end_frac (float): Decimal between 0 and 1 representing the start of the curb segment.
        stats (dict): Log of statistics as curbs are processes
        min_segment_len_ft (float, optional): Minimum length of curb segments.
        drop_tiny_segments (bool, optional): Drop segments shorter than min_segment_len_ft.

    Returns:
        tuple[bool, float, MultiLineString]:
            bool: if a segment should be skipped due to being too short
            segment_length_ft (float): length of the segment
            segment_geom (MultiLineString): geometry for the segment
    """
    curb_geom = curb_row["geometry"]
    seg_length_ft = curb_row["segment_length_ft"]
    # Calculate segment length
    segment_length_ft = seg_length_ft * (end_frac - start_frac)

    # Skip zero or very short segments
    if drop_tiny_segments:
        if segment_length_ft < min_segment_len_ft:
            stats["segments_filtered_out"] += 1
            return True, segment_length_ft, None

    # Create segment geometry using substring with normalized coordinates
    segment_geom = convert_point_to_line(
        substring(curb_geom, start_frac, end_frac, normalized=True)
    )

    return False, segment_length_ft, segment_geom


def make_curb_gdf(
    segments_data: list,
    curbs_clean: gpd.GeoDataFrame,
    point_id_cols: list,
    points_id_col: str,
    curb_id_col: str,
    seg_prefix: str,
    stats: dict,
) -> gpd.GeoDataFrame | None:
    """
    Makes a GeoDataFrame from a list of curb segments.
    Adds any curbs not segmented by the current asset type.

    Args:
        segments_data (list): List of dictionaries, where each dict corresponds to one segment.
        curbs_clean (gpd.GeoDataFrame): Clean curbs segmented by previous asset types.
        point_id_cols (list): List of points_id_cols to be brought to the final df.
        points_id_col (str): Column name of point ID.
        curb_id_col (str): Column name of curb ID.
        seg_prefix (str): Prefix string for segment name.
        stats (dict): Log of statistics as curbs are processed.

    Returns:
        gpd.GeoDataFrame | None: GeoDataFrame of curb segments (if any)
    """
    cols_to_keep = [
        curb_id_col,
        "segment_length_ft",
        "is_left_side_oneway",
        "geometry",
    ] + point_id_cols

    if segments_data:
        segments_gdf = gpd.GeoDataFrame(
            segments_data, geometry="geometry", crs=curbs_clean.crs
        )
    else:
        segments_gdf = gpd.GeoDataFrame(
            columns=cols_to_keep, geometry="geometry", crs=curbs_clean.crs
        )

    # Print statistics
    log_segment_process(stats)

    # Merge point information to segments
    if len(segments_gdf) > 0:
        for col in segments_gdf.columns:
            if col not in curbs_clean.columns:
                curbs_clean[col] = None
        segments_gdf = add_curbs_not_segmented_by_point(
            curb_segments=segments_gdf,
            curbs_clean=curbs_clean,
            curb_id_col=curb_id_col,
            points_id_col=points_id_col,
            seg_prefix=seg_prefix,
        )

        seperator = ":"
        segments_gdf[curb_id_col] = (
            segments_gdf[[curb_id_col, "segment_id"]]
            .astype(str)
            .agg(seperator.join, axis=1)
        )
        return segments_gdf[cols_to_keep]
    else:
        return None


def log_segment_process(stats: dict[str, int]) -> None:
    """
    Logs statistics related to the output of curb segmentation.

    Args:
        stats (dict[str, int]): Dictionary of stats related to processing of data.
    """

    logger = get_logger(__name__)
    curbs_processed = stats["curbs_processed"]
    total_segments = stats["total_segments_created"]
    # filtered_segments = stats['segments_filtered_out']
    logger.debug(f"Curbs processed: {curbs_processed:,}")
    logger.debug(f"Segments created: {total_segments:,}")
    logger.debug(
        f"Average segments/curb: {total_segments / max(1, curbs_processed):.1f}",
    )


def format_curb_segments(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Create the final format of curb segments for export.
    """
    # Create `curb_id` and `segment_uid` columns
    gdf = gdf.rename(columns={"blockface_id": "segment_uid"})
    gdf["blockface_id"] = gdf["segment_uid"].str.split(":").str[0]
    gdf["blockface_id"] = gdf["blockface_id"].map(
        lambda x: uuid.UUID(x) if x is not None else None
    )

    # Create column for segment IDs (S1, S2, S3, ..., etc.)
    # Split segment_uid into parts
    parts = gdf["segment_uid"].str.split(":", expand=True)
    parts.columns = ["blockface_str", "bs_str", "fs_str", "ps_str", "pm_str"]

    # Extract numeric values
    gdf["blockface_num"] = parts["blockface_str"]
    gdf["bs_num"] = parts["bs_str"].str.replace("BS", "").astype(int)
    gdf["fs_num"] = parts["fs_str"].str.replace("FS", "").astype(int)
    gdf["ps_num"] = parts["ps_str"].str.replace("PS", "").astype(int)
    gdf["pm_num"] = parts["pm_str"].str.replace("PM", "").astype(int)

    # Sort by all five parts
    gdf = gdf.sort_values(
        ["blockface_num", "bs_num", "fs_num", "ps_num", "pm_num"]
    ).reset_index(drop=True)

    # Create increasing segment sequence 0, 1, 2, ...
    gdf["segment_seq"] = gdf.groupby("blockface_id").cumcount().astype(int)

    # Recalculate the segment length to overwrite the original value. It may not change any values.
    gdf["segment_length_ft"] = gdf.geometry.length

    # Reorder columns
    cols_to_reorder = [
        "blockface_id",
        "is_left_side_oneway",
        "segment_uid",
        "segment_seq",
        "segment_length_ft",
        "bs_id",
        "fh_id",
        "start_ps_id",
        "end_ps_id",
        "start_mp_id",
        "end_mp_id",
        "geometry",
    ]

    return gdf[cols_to_reorder]


def create_curb_segments_table(
    gdf: gpd.GeoDataFrame, output_crs: str = "epsg:4326"
) -> tuple[gpd.GeoDataFrame, uuid.UUID, str]:
    """
    Creates a new GeoDataFrame containing curb segment data derived from an input
    GeoDataFrame. Each curb segment is assigned a unique UUID. The function
    determines upstream and downstream locations using prioritized data sources,
    including parking signs, fire hydrants, and bus stops. The resulting table
    is designed to be compatible with PostgreSQL and formatted with a specific
    CRS (EPSG:4326).

    Sections on parking signs, fire hydrants, and bus stops in the input data
    are considered in order of precedence to define upstream and downstream locations.

    Args:
        gdf (gpd.GeoDataFrame): Input GeoDataFrame containing spatial and attribute
        data for curb segments. It must have a valid CRS defined and includes
        columns "blockface_id", "start_ps_id", "end_ps_id", "fh_id", and "bs_id".
        The function assumes these inputs represent consistent identifiers for
        parking signs, fire hydrants, and bus stops.
        output_crs (str): Coordinate Reference System for the output GeoDataFrame.

    Returns:
        gpd.GeoDataFrame: Output GeoDataFrame containing the calculated segment
        information. Columns include:
        - "segment_id": Unique identifier for each segment (UUID).
        - "blockface_id": Identifier for a blockface, copied from the input
          GeoDataFrame.
        - "upstream_location": Identifier for the upstream location.
        - "downstream_location": Identifier for the downstream location.
        - "geography": Geometry column representing segment geography.
        uuid.UUID: Job ID for the curb segments.
        str: Timestamp string for the curb segment creation job.

    Raises:
        ValueError: If the input GeoDataFrame does not have a CRS defined.
    """

    if gdf.crs is None:
        raise ValueError("Input GeoDataFrame must have a CRS defined")

    gdf = format_curb_segments(gdf)

    # Reproject to EPSG:4326
    gdf_4326 = gdf.to_crs(output_crs)

    # Initialize output GeoDataFrame
    out = gpd.GeoDataFrame(
        geometry=gdf_4326.geometry.rename("geography"),
        crs=output_crs,
        index=gdf_4326.index,
    )

    # Generate new UUID per segment
    out["segment_id"] = [uuid.UUID(uuid.uuid4().hex) for _ in range(len(gdf_4326))]
    out["blockface_id"] = gdf_4326["blockface_id"]
    out["is_left_side_oneway"] = gdf_4326["is_left_side_oneway"]
    out["segment_seq"] = gdf_4326["segment_seq"]

    # Upstream / downstream logic (Prioritized fill: PS > FH > BS)
    fh = gdf_4326["fh_id"]
    bs = gdf_4326["bs_id"]
    start_ps = gdf_4326["start_ps_id"]
    end_ps = gdf_4326["end_ps_id"]

    out["upstream_location"] = (
        gdf_4326["start_mp_id"]
        .combine_first(start_ps)
        .combine_first(fh)
        .combine_first(bs)
    )

    out["downstream_location"] = (
        gdf_4326["end_mp_id"].combine_first(end_ps).combine_first(fh).combine_first(bs)
    )

    # Create job ID and run date
    job_id = uuid.uuid4().hex
    out["job_id"] = uuid.UUID(job_id)
    ts = datetime.now(timezone.utc)
    ts_str = ts.strftime("%Y%m%d-%H%M%S")

    out = out[
        [
            "segment_id",
            "blockface_id",
            "job_id",
            "geometry",
            "upstream_location",
            "downstream_location",
            "is_left_side_oneway",
            "segment_seq",
        ]
    ]

    # Raname geography
    out = out.rename_geometry("geography")

    # There may be some points due to segmentation. Convert them to lines.
    out["geography"] = out["geography"].apply(convert_point_to_line)

    # Fill upstream and downstream locations with None if they are missing
    out = fill_up_down_locations(out)

    return out, uuid.UUID(job_id), ts_str


def fill_up_down_locations(
    gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Fills missing upstream and downstream locations for a given DataFrame.

    This function processes a DataFrame containing blockface entries with upstream and downstream
    location columns. It fills missing upstream and downstream values based on adjacent rows within
    a group defined by the 'blockface_id' column.

    Args:
        gdf (gpd.GeoDataFrame): DataFrame containing blockface entries with upstream and downstream location columns.

    Returns:
        gpd.GeoDataFrame: A copy of the input DataFrame with additional columns.
    """

    # Column names
    block_col: str = "blockface_id"
    upstream_col: str = "upstream_location"
    downstream_col: str = "downstream_location"
    new_up_col: str = "new_upstream_location"
    new_down_col: str = "new_downstream_location"

    # Replace block cells with NaNs
    out = gdf.copy()
    out[upstream_col] = out[upstream_col].replace("", pd.NA)
    out[downstream_col] = out[downstream_col].replace("", pd.NA)

    g = out.groupby(block_col, sort=False)

    # Find the first and last rows in each group
    is_first = g.cumcount().eq(0)
    is_last = g.cumcount(ascending=False).eq(0)

    # Find the previous downstream location and next upstream location for each group
    prev_down = g[downstream_col].shift(1)
    next_up = g[upstream_col].shift(-1)

    # Find if there is a conflict between the previous and next locations
    out["conflict_prev_boundary"] = (
        out[upstream_col].notna()
        & prev_down.notna()
        & (out[upstream_col] != prev_down)
        & ~is_first
    )
    out["conflict_next_boundary"] = (
        out[downstream_col].notna()
        & next_up.notna()
        & (out[downstream_col] != next_up)
        & ~is_last
    )
    out["has_any_boundary_conflict"] = (
        out["conflict_prev_boundary"] | out["conflict_next_boundary"]
    )

    # Create new columns with the filled upstream and downstream locations
    out[new_up_col] = out[upstream_col].combine_first(prev_down)
    out.loc[is_first, new_up_col] = pd.NA

    out[new_down_col] = g[new_up_col].shift(-1)
    out.loc[is_last, new_down_col] = pd.NA

    # Final override: if upstream == downstream (and both present), copy originals
    same_anchor = (
        out[upstream_col].notna()
        & out[downstream_col].notna()
        & (out[upstream_col] == out[downstream_col])
    )
    out.loc[same_anchor, new_up_col] = out.loc[same_anchor, upstream_col]
    out.loc[same_anchor, new_down_col] = out.loc[same_anchor, downstream_col]

    # Protect adjacent segments when the current segment is same-anchor ---
    # Mark same-anchor rows so we can shift within each blockface group
    out["_same_anchor"] = same_anchor

    # If the *next* row is same-anchor, do NOT change this row's downstream if it is already not null
    next_is_same = g["_same_anchor"].shift(-1).fillna(False)
    preserve_prev_down = out[downstream_col].notna() & next_is_same
    out.loc[preserve_prev_down, new_down_col] = out.loc[
        preserve_prev_down, downstream_col
    ]

    # If the *previous* row is same-anchor, do NOT change this row's upstream if it is already not null
    prev_is_same = g["_same_anchor"].shift(1).fillna(False)
    preserve_next_up = out[upstream_col].notna() & prev_is_same
    out.loc[preserve_next_up, new_up_col] = out.loc[preserve_next_up, upstream_col]

    # Create additional QA flags
    out["upstream_was_filled"] = out[upstream_col].isna() & out[new_up_col].notna()
    out["downstream_was_filled"] = (
        out[downstream_col].isna() & out[new_down_col].notna()
    )
    out["any_location_filled"] = (
        out["upstream_was_filled"] | out["downstream_was_filled"]
    )

    out["any_location_changed"] = (
        out[upstream_col].notna() & (out[upstream_col] != out[new_up_col])
    ) | (out[downstream_col].notna() & (out[downstream_col] != out[new_down_col]))

    # Select columns only
    columns_to_keep = [
        "segment_id",
        block_col,
        "job_id",
        "geography",
        new_up_col,
        new_down_col,
        "is_left_side_oneway",
        "segment_seq",
    ]

    out = out[columns_to_keep].rename(
        columns={new_up_col: upstream_col, new_down_col: downstream_col}
    )

    # Replace <pd.NA> with None
    out = nan_to_none(out)

    return out


def _assign_merge_groups_for_blockface(
    seg_length: np.ndarray,
    upstream_asset: np.ndarray,
    length_threshold: float,
) -> np.ndarray:
    """
    Assign merged-group ids for one ordered blockface.

    Rules applied:
      1. Leading tiny segments merge downstream into the first non-tiny segment.
      2. Trailing tiny segments merge upstream into the last non-tiny segment.
      3. Middle tiny runs:
         - if the next non-tiny segment has upstream_asset in {"FH", "BS"},
           the first (n-1) tiny segments merge upstream and the last tiny
           segment merges downstream
         - otherwise all tiny segments merge upstream
      4. If the entire blockface is tiny, merge everything into one group.

    Args:
        seg_length (np.ndarray): Segment lengths for one blockface, already
            ordered by segment_seq.
        upstream_asset (np.ndarray): Upstream asset values for the same ordered
            blockface.
        length_threshold (float): Segments with seg_length < length_threshold
            are considered tiny.

    Returns:
        np.ndarray: Integer merged-group id for each input segment.
    """
    n = len(seg_length)
    is_tiny = seg_length < length_threshold
    group_ids = np.full(n, -1, dtype=np.int64)

    long_idx = np.flatnonzero(~is_tiny)
    if len(long_idx) == 0:
        group_ids[:] = 0
        return group_ids

    # Every non-tiny segment starts its own base group.
    long_to_group = {idx: gid for gid, idx in enumerate(long_idx)}
    for idx, gid in long_to_group.items():
        group_ids[idx] = gid

    first_long = long_idx[0]
    last_long = long_idx[-1]

    # Leading tiny run -> downstream into first non-tiny
    if first_long > 0:
        group_ids[:first_long] = long_to_group[first_long]

    # Trailing tiny run -> upstream into last non-tiny
    if last_long < n - 1:
        group_ids[last_long + 1 :] = long_to_group[last_long]

    # Middle tiny runs
    i = first_long + 1
    while i < last_long:
        if not is_tiny[i]:
            i += 1
            continue

        run_start = i
        while i <= last_long and is_tiny[i]:
            i += 1
        run_end = i - 1  # inclusive
        next_long = i  # first non-tiny after the tiny run
        prev_long = run_start - 1

        prev_group = long_to_group[prev_long]
        next_group = long_to_group[next_long]
        next_asset = upstream_asset[next_long]

        if next_asset in {"FH", "BS"}:
            # First n-1 tiny segments upstream, last tiny segment downstream.
            if run_start < run_end:
                group_ids[run_start:run_end] = prev_group
            group_ids[run_end] = next_group
        else:
            # Entire tiny run upstream.
            group_ids[run_start : run_end + 1] = prev_group

    return group_ids


def _adjust_merge_group_locations_assets(
    df: pd.DataFrame | gpd.GeoDataFrame,
) -> pd.DataFrame | gpd.GeoDataFrame:
    """
    Adjust updated asset and location columns from the merged list columns.

    Args:
        df (pd.DataFrame | gpd.GeoDataFrame): Output table containing
            *_locations and *_assets list columns.

    Returns:
        pd.DataFrame | gpd.GeoDataFrame: DataFrame with updated_* columns set
            from the list columns.
    """

    def first_non_null(values: list) -> object | None:
        for value in values:
            if pd.notna(value):
                return value
        return None

    def last_non_null(values: list) -> object | None:
        for value in reversed(values):
            if pd.notna(value):
                return value
        return None

    def has_non_null(values_set: set) -> bool:
        for value in values_set:
            if pd.notna(value):
                return True
        return False

    def as_list(values: object) -> list:
        if values is None or (isinstance(values, float) and np.isnan(values)):
            return []
        if isinstance(values, list):
            return values
        if isinstance(values, (tuple, set, np.ndarray, pd.Series)):
            return list(values)
        return [values]

    def resolve_row(row: pd.Series) -> pd.Series:
        def dedupe_preserve_order(values: list) -> list:
            seen = set()
            deduped = []
            for value in values:
                if value in seen:
                    continue
                seen.add(value)
                deduped.append(value)
            return deduped

        upstream_locations = dedupe_preserve_order(
            as_list(row.get("upstream_locations"))
        )
        downstream_locations = dedupe_preserve_order(
            as_list(row.get("downstream_locations"))
        )
        upstream_assets = dedupe_preserve_order(as_list(row.get("upstream_assets")))
        downstream_assets = dedupe_preserve_order(as_list(row.get("downstream_assets")))

        row["upstream_locations"] = upstream_locations
        row["downstream_locations"] = downstream_locations
        row["upstream_assets"] = upstream_assets
        row["downstream_assets"] = downstream_assets

        upstream_locations_set = set(upstream_locations)
        downstream_locations_set = set(downstream_locations)
        upstream_assets_set = set(upstream_assets)
        downstream_assets_set = set(downstream_assets)

        row["updated_upstream_location"] = (
            first_non_null(upstream_locations)
            if has_non_null(upstream_locations_set)
            else None
        )
        row["updated_downstream_location"] = (
            last_non_null(downstream_locations)
            if has_non_null(downstream_locations_set)
            else None
        )
        row["updated_upstream_asset"] = (
            first_non_null(upstream_assets)
            if has_non_null(upstream_assets_set)
            else None
        )
        row["updated_downstream_asset"] = (
            last_non_null(downstream_assets)
            if has_non_null(downstream_assets_set)
            else None
        )
        return row

    return df.apply(resolve_row, axis=1)


def _remove_none_from_location_lists(
    df: pd.DataFrame | gpd.GeoDataFrame,
) -> pd.DataFrame | gpd.GeoDataFrame:
    """
    Remove None values from *_locations lists when the list length is > 1.
    """

    def clean_list(values: object) -> object:
        if not isinstance(values, list):
            return values
        if len(values) <= 1:
            return values
        return [value for value in values if value is not None]

    def replace_none_list(values: object) -> object:
        if isinstance(values, list) and len(values) == 1 and values[0] is None:
            return None
        return values

    df = df.copy()
    for col in ("upstream_locations", "downstream_locations"):
        if col in df.columns:
            df[col] = df[col].map(clean_list).map(replace_none_list)

    cols_order = {
        "segment_id": "segment_id",
        "blockface_id": "blockface_id",
        "job_id": "job_id",
        "segment_seq": "segment_seq",
        "is_left_side_oneway": "is_left_side_oneway",
        "geography": "geography",
        "updated_upstream_location": "upstream_location",
        "updated_downstream_location": "downstream_location",
        "upstream_locations": "upstream_loc_list",
        "downstream_locations": "downstream_loc_list",
    }

    df = df[cols_order.keys()]
    df = df.rename(columns=cols_order)

    def to_pg_uuid_array(values: object) -> object:
        if values is None:
            return None
        if not isinstance(values, list):
            return values
        if len(values) == 0:
            return "{}"
        cleaned = [str(value) for value in values if value is not None]
        return "{" + ",".join(cleaned) + "}"

    for col in ("upstream_loc_list", "downstream_loc_list"):
        if col in df.columns:
            df[col] = df[col].map(to_pg_uuid_array)

    return df


def merge_tiny_curb_segments(
    gdf: gpd.GeoDataFrame,
    length_threshold: float = 3.0,
    preserve_extra_columns: bool = True,
    asset_dict: dict | None = None,
) -> gpd.GeoDataFrame:
    """
    Merge short curb segments within each blockface.

    The input must contain one row per original segment and be sortable within
    each blockface using `segment_seq`.

    Merge rules:
      - Segments with seg_length < length_threshold are tiny.
      - Leading tiny segments merge downstream into the first non-tiny segment.
      - Trailing tiny segments merge upstream into the last non-tiny segment.
      - Middle tiny runs:
        * if the next non-tiny segment has upstream_asset in {"FH", "BS"},
          the first (n-1) tiny segments merge upstream and the last tiny
          segment merges downstream
        * otherwise all tiny segments merge upstream
      - If all segments in a blockface are tiny, the whole blockface is merged
        into a single output row.

    Output columns (minimum set):
      - blockface_id
      - segment_seq: new merged sequence starting at 0
      - seg_length: summed merged length
      - updated_upstream_asset
      - updated_downstream_asset
      - updated_upstream_location
      - updated_downstream_location
      - upstream_locations
      - downstream_locations
      - upstream_assets
      - downstream_assets
      - source_segment_ids
      - source_segment_seqs
      - source_segment_count

    Args:
        gdf (gpd.GeoDataFrame): Input segment-level table.
        length_threshold (float): Tiny segment threshold in feet.
        preserve_extra_columns (bool): If True, extra columns not directly used
            in merging are carried from the first row in each merged group,
            except geometry which is merged.
        asset_dict (dict | None): Dictionary with asset locations.

    Returns:
        gpd.GeoDataFrame: One row per merged segment. If `gdf`
            is a GeoDataFrame, merged geometry is also returned.

    """
    logger = get_logger(__name__)
    logger.info(
        f"Starting merge of tiny segments with threshold {length_threshold} ft ..."
    )

    gdf = add_upstream_downstream_assets(gdf, asset_dict)

    required_cols = [
        "segment_id",
        "blockface_id",
        "segment_seq",
        "seg_length",
        "upstream_asset",
        "downstream_asset",
        "upstream_location",
        "downstream_location",
    ]
    missing = [c for c in required_cols if c not in gdf.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Drop blockfaces with a single tiny segment and no upstream/downstream location.
    blockface_sizes = gdf.groupby("blockface_id", sort=False, observed=True)[
        "segment_id"
    ].transform("size")
    drop_mask = (
        blockface_sizes.eq(1)
        & (gdf["seg_length"] < length_threshold)
        & gdf["upstream_location"].isna()
        & gdf["downstream_location"].isna()
    )
    if drop_mask.any():
        gdf = gdf.loc[~drop_mask].copy()

    is_geo = isinstance(gdf, gpd.GeoDataFrame)
    geometry_col = gdf.geometry.name if is_geo else None

    # Stable sort once. Mergesort preserves deterministic behavior.
    df = gdf.sort_values(["blockface_id", "segment_seq"], kind="mergesort").reset_index(
        drop=True
    )

    used_cols = set(required_cols)
    if is_geo:
        used_cols.add(geometry_col)

    extra_cols = (
        [c for c in df.columns if c not in used_cols] if preserve_extra_columns else []
    )

    out_rows = []

    # observed=True avoids unnecessary category combinations when relevant.
    for blockface_id, bf in df.groupby("blockface_id", sort=False, observed=True):
        bf = bf.reset_index(drop=True)

        seg_length = bf["seg_length"].to_numpy(dtype=float, copy=False)
        upstream_asset = bf["upstream_asset"].to_numpy(copy=False)
        is_tiny = seg_length < length_threshold
        group_ids = _assign_merge_groups_for_blockface(
            seg_length=seg_length,
            upstream_asset=upstream_asset,
            length_threshold=length_threshold,
        )

        # Group boundaries from contiguous equal group ids.
        # Group ids are assigned so that identical ids form contiguous runs.
        change = np.empty(len(group_ids), dtype=bool)
        change[0] = True
        change[1:] = group_ids[1:] != group_ids[:-1]
        starts = np.flatnonzero(change)
        ends = np.r_[starts[1:], len(group_ids)]

        for new_seq, (start, end) in enumerate(zip(starts, ends, strict=False)):
            grp = bf.iloc[start:end]
            first = grp.iloc[0]
            last = grp.iloc[-1]
            grp_is_tiny = is_tiny[start:end]
            has_tiny = bool(np.any(grp_is_tiny))
            has_non_tiny = bool(np.any(~grp_is_tiny))
            is_middle_group = start > 0 and end < len(bf)

            if is_middle_group and has_tiny and has_non_tiny:
                if grp_is_tiny[0] and not grp_is_tiny[-1]:
                    # Middle tiny run merged downstream into the next non-tiny.
                    # upstream_locations = grp.loc[grp_is_tiny, "upstream_location"].tolist()
                    upstream_locations = grp["upstream_location"].tolist()
                    downstream_locations = [last["downstream_location"]]
                    # upstream_assets = grp.loc[grp_is_tiny, "upstream_asset"].tolist()
                    upstream_assets = grp["upstream_asset"].tolist()
                    downstream_assets = [last["downstream_asset"]]
                elif not grp_is_tiny[0] and grp_is_tiny[-1]:
                    # Middle tiny run merged upstream into the previous non-tiny.
                    upstream_locations = [first["upstream_location"]]
                    # downstream_locations = grp.loc[grp_is_tiny, "downstream_location"].tolist()
                    downstream_locations = grp["downstream_location"].tolist()
                    upstream_assets = [first["upstream_asset"]]
                    # downstream_assets = grp.loc[grp_is_tiny, "downstream_asset"].tolist()
                    downstream_assets = [first["downstream_asset"]]
                else:
                    upstream_locations = grp["upstream_location"].tolist()
                    downstream_locations = grp["downstream_location"].tolist()
                    upstream_assets = grp["upstream_asset"].tolist()
                    downstream_assets = grp["downstream_asset"].tolist()
            else:
                upstream_locations = grp["upstream_location"].tolist()
                downstream_locations = grp["downstream_location"].tolist()
                upstream_assets = grp["upstream_asset"].tolist()
                downstream_assets = grp["downstream_asset"].tolist()

            row = {
                "blockface_id": blockface_id,
                "segment_seq": new_seq,
                "segment_id": first["segment_id"],
                "seg_length": float(grp["seg_length"].sum()),
                "upstream_locations": upstream_locations,
                "downstream_locations": downstream_locations,
                "upstream_assets": upstream_assets,
                "downstream_assets": downstream_assets,
                "source_segment_ids": grp["segment_id"].tolist(),
                "source_segment_seqs": grp["segment_seq"].tolist(),
                "source_segment_count": int(len(grp)),
            }

            if preserve_extra_columns:
                for col in extra_cols:
                    row[col] = first[col]

            if is_geo:
                row[geometry_col] = _safe_merge_lines(grp[geometry_col].to_list())

            out_rows.append(row)

    if is_geo:
        out = gpd.GeoDataFrame(out_rows, geometry=geometry_col, crs=gdf.crs)
    else:
        out = pd.DataFrame(out_rows)

    out = _adjust_merge_group_locations_assets(out)

    logger.info(f"Tiny segments under {length_threshold} ft were merged")
    logger.info(f"Final segments: {len(out):,}")

    return _remove_none_from_location_lists(out)


def add_merge_group_labels(
    gdf: pd.DataFrame | gpd.GeoDataFrame,
    length_threshold: float = 3.0,
) -> pd.DataFrame | gpd.GeoDataFrame:
    """
    Add a merge-group label to the original segment-level rows.

    This is useful when you want to inspect or debug which original rows will
    be merged together before producing the final merged output.

    Args:
        gdf (pd.DataFrame | gpd.GeoDataFrame): Input segment-level table.
        length_threshold (float): Tiny segment threshold in feet.

    Returns:
        pd.DataFrame | gpd.GeoDataFrame: Copy of the input with two extra
            columns:
            - merge_group_id: merged-group id within each blockface
            - merge_group_seq: dense 0..K-1 sequence within each blockface
    """
    required_cols = ["blockface_id", "segment_seq", "seg_length", "upstream_asset"]
    missing = [c for c in required_cols if c not in gdf.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = gdf.sort_values(["blockface_id", "segment_seq"], kind="mergesort").copy()

    merge_group_id_parts = []

    for _, bf in df.groupby("blockface_id", sort=False, observed=True):
        seg_length = bf["seg_length"].to_numpy(dtype=float, copy=False)
        upstream_asset = bf["upstream_asset"].to_numpy(copy=False)
        group_ids = _assign_merge_groups_for_blockface(
            seg_length=seg_length,
            upstream_asset=upstream_asset,
            length_threshold=length_threshold,
        )
        merge_group_id_parts.append(pd.Series(group_ids, index=bf.index))

    df["merge_group_id"] = pd.concat(merge_group_id_parts).sort_index()

    # Dense sequence within blockface in sorted order.
    df["merge_group_seq"] = df.groupby("blockface_id", sort=False, observed=True)[
        "merge_group_id"
    ].transform(lambda s: pd.factorize(s, sort=False)[0])

    return df


def _safe_merge_lines(geoms: list[BaseGeometry | None]) -> BaseGeometry | None:
    """
    Merge a list of line geometries into one geometry when possible.

    Args:
        geoms (list[BaseGeometry | None]): Sequence of shapely geometries.
            None values are ignored.

    Returns:
        BaseGeometry | None: Merged geometry when possible, otherwise a unioned
            geometry or the first valid geometry. Returns None if all geometries
            are missing.
    """
    valid = [g for g in geoms if g is not None]
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0]

    # Preserve input order by concatenating coordinates in sequence.
    coords: list[tuple[float, float]] = []
    for geom in valid:
        geom_type = getattr(geom, "geom_type", None)
        if geom_type == "LineString":
            parts = [geom]
        elif geom_type == "MultiLineString":
            parts = list(geom.geoms)
        else:
            parts = []

        for part in parts:
            part_coords = list(part.coords)
            if not part_coords:
                continue
            if coords and coords[-1] == part_coords[0]:
                coords.extend(part_coords[1:])
            else:
                coords.extend(part_coords)

    if len(coords) >= 2:
        return LineString(coords)

    try:
        merged = linemerge(unary_union(valid))
        if getattr(merged, "geom_type", None) == "MultiLineString":
            return max(merged.geoms, key=lambda g: g.length, default=merged)
        return merged
    except Exception:
        try:
            unioned = unary_union(valid)
            if getattr(unioned, "geom_type", None) == "MultiLineString":
                return max(unioned.geoms, key=lambda g: g.length, default=unioned)
            return unioned
        except Exception:
            return valid[0]
