"""
Curb generation module for creating curb line geometries from roadway inventory data.
"""  # Packages

# ==============================================================================
import itertools
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import dummylog
import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from curb_utils.db_utils import SmartCurbDB
from shapely.geometry import LineString, MultiLineString, Point, Polygon


# Functions
# ==============================================================================
def get_logger() -> Any:
    """
    Return a logger instance.
    """
    return dummylog.DummyLog(log_name=f"curb-generation-{get_today()}").logger


def get_today(sep: str = "", include_time: bool = False) -> str:
    """
    Get the current date, optionally including time in HHMMSS format.
    """
    now = datetime.today()

    date_part = now.strftime(f"%Y{sep}%m{sep}%d")

    if include_time:
        time_part = now.strftime("%H%M%S")
        return f"{date_part}-{time_part}"

    return date_part


def load_config(config_file_path: str | os.PathLike) -> dict | None:
    """
    Loads a YAML configuration file.
    """
    with open(config_file_path, "r", encoding="utf-8") as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(f"Error loading YAML: {exc}")
            return None


def connect_multilines_to_linestring(
    multiline: MultiLineString | LineString | None,
) -> LineString | None:
    """
    Connects all component LineStrings in a MultiLineString into a single
    continuous LineString by greedily connecting the nearest endpoints.
    """

    if multiline is None:
        return None

    # If already a LineString, return as is
    if isinstance(multiline, LineString):
        return multiline

    # Extract component lines
    lines = list(multiline.geoms)
    if len(lines) == 0:
        return None
    if len(lines) == 1:
        return lines[0]

    # Extract start and end coordinates for each line
    endpoints = []
    for i, line in enumerate(lines):
        start = np.array(line.coords[0])
        end = np.array(line.coords[-1])
        endpoints.append((i, start, end))

    # Start with the longest line (often central) or first
    current_idx = max(range(len(lines)), key=lambda x: lines[x].length)
    used = {current_idx}
    current_coords = list(lines[current_idx].coords)

    while len(used) < len(lines):
        current_start = np.array(current_coords[0])
        current_end = np.array(current_coords[-1])

        # Find closest unused endpoint
        best_dist = float("inf")
        best_i = None
        best_reverse = False
        best_attach_to_end = True

        for i, line in enumerate(lines):
            if i in used:
                continue
            start = np.array(line.coords[0])
            end = np.array(line.coords[-1])

            # four possible connection distances
            d1 = np.linalg.norm(current_end - start)  # attach end → start
            d2 = np.linalg.norm(current_end - end)  # attach end → end
            d3 = np.linalg.norm(current_start - start)  # attach start → start
            d4 = np.linalg.norm(current_start - end)  # attach start → end

            for d, reverse, attach_to_end in [
                (d1, False, True),
                (d2, True, True),
                (d3, True, False),
                (d4, False, False),
            ]:
                if d < best_dist:
                    best_dist = d
                    best_i = i
                    best_reverse = reverse
                    best_attach_to_end = attach_to_end

        # Attach chosen line
        next_line = lines[best_i]
        next_coords = list(next_line.coords)
        if best_reverse:
            next_coords = list(reversed(next_coords))

        if best_attach_to_end:
            # Connect to the current end
            current_coords.extend(next_coords)
        else:
            # Connect to the current start
            current_coords = next_coords + current_coords

        used.add(best_i)

    return LineString(current_coords)


def offset_lines(
    gdf: gpd.GeoDataFrame,
    buffer_l_col: str = "buffer_l",
    buffer_r_col: str = "buffer_r",
) -> gpd.GeoDataFrame:
    """
    Given a GeoDataFrame with LineString or MultiLineString geometries,
    and columns specifying left and right buffer distances per geometry,
    create two offset lines (left and right) for each geometry.

    Args:
        gdf (GeoDataFrame): Input GeoDataFrame.
        buffer_l_col (str): Column name for left offset distance.
        buffer_r_col (str): Column name for right offset distance.

    Returns:
        GeoDataFrame: Lines of respective left and right buffers
    """

    def offset_geom(
        geometry: gpd.GeoSeries, dist: int | None, side: str | None
    ) -> gpd.GeoSeries | None:
        """
        Returns a LineString or MultiLineString geometry at a distance
        from the object on its right or its left side.
        """
        if geometry.is_empty or dist == 0 or dist is None:
            return None

        if geometry.geom_type == "LineString":
            return geometry.parallel_offset(dist, side, join_style=2)
        elif geometry.geom_type == "MultiLineString":
            parts = []
            for part in geometry.geoms:
                offset = part.parallel_offset(dist, side, join_style=2)
                if not offset.is_empty:
                    parts.append(offset)
            if len(parts) == 0:
                return None
            elif len(parts) == 1:
                return parts[0]
            else:
                return MultiLineString(parts)
        else:
            return None

    rows = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        buffer_l = row.get(buffer_l_col, None)
        buffer_r = row.get(buffer_r_col, None)

        left = (
            offset_geom(geom, buffer_l, "left") if buffer_l not in [None, 0] else None
        )
        right = (
            offset_geom(geom, buffer_r, "right") if buffer_r not in [None, 0] else None
        )

        if left is not None:
            rows.append(
                {
                    "OBJECTID": row.OBJECTID,
                    "St_Name": row.St_Name,
                    "route_id": row.route_id,
                    "Route_Direction": row.Route_Direction,
                    "F_F_Class": row.F_F_Class,
                    "geometry": left,
                    "side": "left",
                    "original_index": idx,
                    buffer_l_col: buffer_l,
                    buffer_r_col: buffer_r,
                }
            )
        if right is not None:
            rows.append(
                {
                    "OBJECTID": row.OBJECTID,
                    "St_Name": row.St_Name,
                    "route_id": row.route_id,
                    "Route_Direction": row.Route_Direction,
                    "F_F_Class": row.F_F_Class,
                    "geometry": right,
                    "side": "right",
                    "original_index": idx,
                    buffer_l_col: buffer_l,
                    buffer_r_col: buffer_r,
                }
            )
    result = (
        gpd.GeoDataFrame(data=rows, geometry="geometry", crs=gdf.crs)
        .reset_index()
        .rename({"index": "curb_id"}, axis=1)
    )
    result["geometry"] = result["geometry"].apply(connect_multilines_to_linestring)

    return result


def collapse_polygon_z_to_2d(polygon_z: Polygon) -> Polygon:
    """
    Collapses a PolygonZ (3D polygon) to a 2D Polygon by removing the Z-coordinate.

    Args:
        polygon_z (shapely.geometry.Polygon): A 3D Shapely Polygon object.

    Returns:
        shapely.geometry.Polygon: A 2D Shapely Polygon object.
    """
    if polygon_z.has_z:
        # Extract the exterior coordinates and remove the Z-component
        exterior_coords_2d = [(x, y) for x, y, z in polygon_z.exterior.coords]

        # Extract interior ring coordinates and remove the Z-component if present
        interior_coords_2d = []
        for interior_ring in polygon_z.interiors:
            interior_coords_2d.append([(x, y) for x, y, z in interior_ring.coords])

        return Polygon(exterior_coords_2d, interior_coords_2d)
    else:
        # If the polygon already doesn't have Z-coordinates, return it as is
        return polygon_z


def read_roadways(
    roadway_path: str,
    include_filters: dict[str, list[int | str]],
    exclude_filters: dict[str, list[int | str]],
) -> gpd.GeoDataFrame:
    """
    Reads a roadway inventory file, filters out irrelevant roadways.

    Args:
        roadway_path (str): file_path for roadway inventory GeoJSON file.
        include_filters (dict): columns where only the values listed should be included.
        exclude_filters (dict): columns where only the values listed should be excluded.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame of the filtered roadway inventory.
    """
    # Read the file_path into a GeoDataFrame
    if roadway_path.endswith(".parquet"):
        roadway_gdf = gpd.read_parquet(roadway_path)
    elif roadway_path.endswith(".feather"):
        roadway_gdf = gpd.read_feather(roadway_path)
    elif roadway_path.endswith(".geojson") or roadway_path.endswith(".shp"):
        roadway_gdf = gpd.read_file(roadway_path)
    else:
        raise ValueError(f"Invalid file_path: {roadway_path}")

    # Use the "include" filters and "exclude" filters
    # Start with a mask that is all True
    mask = pd.Series([True] * len(roadway_gdf), index=roadway_gdf.index)

    # Iterate through the dictionary and update the mask
    for column, values_to_keep in include_filters.items():
        mask &= roadway_gdf[column].isin(values_to_keep)

    for column, values_to_exclude in exclude_filters.items():
        # Create a mask for the values to be excluded, then negate it
        mask &= ~roadway_gdf[column].isin(values_to_exclude)

    # Apply the final mask to the DataFrame
    roadway_shp = roadway_gdf[mask]

    return roadway_shp


def create_curbs(
    roadway_shp: gpd.GeoDataFrame,
    ft_crs: str,
    ft_diff: float = 0.0001,
    min_seg_len: float = 1,
) -> gpd.GeoDataFrame:
    """
    Creates and cleans curb lines GeoDataFrame from roadway GeoDataFrame.
    Process specific to MassDOT Roadway Inventory.

    Args:
        roadway_shp (gpd.GeoDataFrame): roadway inventory GeoDataFrame
        ft_crs (str): String of CRS with unit US survey foot
        ft_diff (float): distance in feet to subtract from curb width
                        to create line removal buffer. Default 0.0001.
        min_seg_len (float): Minimum length of a segment in feet

    Returns:
        gpd.GeoDataFrame: GeoDataFrame of the clean curb lines.
    """
    # Original crs to convert back
    original_crs = roadway_shp.crs

    # Create curb lines
    # Create buffer values based on MassDOT roadway inventory attributes
    curb_shp = roadway_shp.copy().to_crs(ft_crs)
    curb_shp["buffer_l"] = (curb_shp["Surface_Wd"] / 2).fillna(0)
    curb_shp["buffer_l"] = (
        curb_shp["buffer_l"]
        .mask(
            curb_shp["ROW_Width"]
            != (
                curb_shp["Surface_Wd"] + curb_shp["Lt_Sidewlk"] + curb_shp["Rt_Sidewlk"]
            ),
            curb_shp["buffer_l"] + curb_shp["Shldr_Lt_W"],
        )
        .fillna(0)
    )
    curb_shp["buffer_r"] = (curb_shp["Surface_Wd"] / 2).fillna(0)
    curb_shp["buffer_r"] = (
        curb_shp["buffer_r"]
        .mask(
            curb_shp["ROW_Width"]
            != (
                curb_shp["Surface_Wd"] + curb_shp["Lt_Sidewlk"] + curb_shp["Rt_Sidewlk"]
            ),
            curb_shp["buffer_r"] + curb_shp["Shldr_Rt_W"],
        )
        .fillna(0)
    )
    # Create all possible curb line datasets using an offset buffer
    gdf_offsets = offset_lines(curb_shp)

    # Clean curb lines
    # Create areas to remove lines from
    removal_buffer_input = curb_shp.copy()
    removal_buffer_input["geometry"] = removal_buffer_input["geometry"].apply(
        connect_multilines_to_linestring
    )
    removal_buffer_input["buffer_l"] = removal_buffer_input["buffer_l"].mask(
        removal_buffer_input["buffer_l"] > 0, removal_buffer_input["buffer_l"] - ft_diff
    )
    removal_buffer_input["buffer_r"] = removal_buffer_input["buffer_r"].mask(
        removal_buffer_input["buffer_r"] > 0, removal_buffer_input["buffer_r"] - ft_diff
    )
    removal_buffer_l = removal_buffer_input.copy()
    removal_buffer_r = removal_buffer_input.copy()
    removal_buffer_l["geometry"] = removal_buffer_l["geometry"].buffer(
        removal_buffer_l["buffer_l"], cap_style="flat", single_sided=True
    )
    removal_buffer_r["geometry"] = removal_buffer_r["geometry"].buffer(
        (removal_buffer_r["buffer_r"]) * (-1), cap_style="flat", single_sided=True
    )
    removal_buffer_l["geometry"] = removal_buffer_l["geometry"].apply(
        collapse_polygon_z_to_2d
    )
    removal_buffer_r["geometry"] = removal_buffer_r["geometry"].apply(
        collapse_polygon_z_to_2d
    )
    removal_buffers = pd.concat([removal_buffer_l, removal_buffer_r])

    # Make sure to convert to GeoDataFrame
    removal_buffers = gpd.GeoDataFrame(
        removal_buffers, geometry=removal_buffers["geometry"]
    )

    curbs = gpd.overlay(gdf_offsets, removal_buffers, how="symmetric_difference")

    # Explode multipart geometries
    curbs = curbs.explode(ignore_index=True)
    curbs["curb_id"] = curbs.index.values

    # Rename columns and set types
    final_cols = {
        "curb_id": ("curb_id", "int64"),
        "OBJECTID_1": ("roadway_id", "int64"),
        "St_Name_1": ("street_name", str),
        "route_id_1": ("route_id", str),
        "Route_Direction_1": ("route_direction", str),
        "F_F_Class_1": ("ff_class", "int16"),
        "side": ("side", str),
        "buffer_l_1": ("buffer_left", "int16"),
        "buffer_r_1": ("buffer_right", "int16"),
        "geometry": ("geometry", str),
    }
    curbs = (
        curbs[list(final_cols.keys())]
        .fillna({"Operation": 0})
        .rename(columns={k: v[0] for k, v in final_cols.items()})
    )
    curbs = curbs.astype(
        {v[0]: v[1] for k, v in final_cols.items() if v[0] != "geometry"}
    )
    curbs = gpd.GeoDataFrame(curbs, geometry="geometry", crs=ft_crs)

    # Add lat and lon for start and end points, and curb lengths
    curbs["start_lon"] = (
        curbs["geometry"].to_crs(original_crs).apply(lambda g: g.coords[0][0])
    )
    curbs["start_lat"] = (
        curbs["geometry"].to_crs(original_crs).apply(lambda g: g.coords[0][1])
    )
    curbs["end_lon"] = (
        curbs["geometry"].to_crs(original_crs).apply(lambda g: g.coords[-1][0])
    )
    curbs["end_lat"] = (
        curbs["geometry"].to_crs(original_crs).apply(lambda g: g.coords[-1][1])
    )
    curbs["curb_length_ft"] = curbs.length

    # Remove short curb segments
    curbs = curbs[curbs["curb_length_ft"] > min_seg_len]

    clean_curbs = merge_adjacent_lines(
        curbs,
        "curb_id",
        ft_crs,
        ["route_id", "route_direction", "side"],
        max_dist=2.5,
    )

    # Merge street operation and oneway direction indicator
    clean_curbs = clean_curbs.merge(
        roadway_shp[["OBJECTID", "Operation", "Oneway"]],
        left_on="roadway_id",
        right_on="OBJECTID",
        how="left",
    )

    # Fill the missing operation and oneway values with default values
    # operation == 1 (oneway)
    # oneway == "FT" (with line digitization direction - forward)
    clean_curbs = (
        clean_curbs.drop(columns=["OBJECTID"])
        .rename(columns={"Operation": "operation", "Oneway": "oneway"})
        .fillna({"operation": 1, "oneway": "FT"})
        .astype({"operation": "int16", "oneway": "str"})
    )

    return clean_curbs.to_crs(original_crs)


def chain_curbs(
    df: pd.DataFrame, left_col: str = "curb_id_left", right_col: str = "curb_id_right"
) -> list[list[int]]:
    """
    Given a dataframe with left and right columns for pairs,
    create a list of groups

    Args:
        df (pd.DataFrame): DataFrame with pairs
        left_col (str): Column label for left IDs
        right_col (str): Column label for right IDs

    Returns:
        list[list[int]]: List of IDs in each group"""

    # Drop duplicates
    pairs = df[[left_col, right_col]].drop_duplicates().values.tolist()

    # Build lookup dicts for quick chaining
    right_lookup = {a: b for a, b in pairs}
    left_lookup = {b: a for a, b in pairs}

    # Find starting nodes (those that never appear on the right)
    starts = [a for a, b in pairs if a not in left_lookup]

    chains = []
    for start in starts:
        chain = [start]
        while chain[-1] in right_lookup:
            nxt = right_lookup[chain[-1]]
            if nxt in chain:  # avoid loops
                break
            chain.append(nxt)
        chains.append(chain)

    return list(chains for chains, _ in itertools.groupby(chains))


def merge_adjacent_lines(
    gdf: gpd.GeoDataFrame,
    id_col: str,
    ft_crs: str,
    dissolve_cols: list[str],
    max_dist: float = 2,
) -> gpd.GeoDataFrame:
    """
    Merges adjacent line segments.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame of curb line segments.
        id_col (str): ID column label in gdf
        ft_crs (str): String of CRS with unit US survey foot
        dissolve_cols (list[str]): List of column names to be dissolved on.
                    i.e., Only if adjacent lines have the same value(s)
                    for the listed column(s), then they will be merged.
        max_dist (float): maximum distance for two segments to be
                        candidates to be merged.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame of the cleaned line segments.
    """
    # Create buffers to find adjacent line segments
    start_gdf = gdf.to_crs(ft_crs).copy()
    start_gdf["geometry"] = (
        start_gdf["geometry"]
        .apply(lambda g: Point([g.coords[0][0], g.coords[0][1]]))
        .buffer(max_dist)
    )
    end_gdf = gdf.to_crs(ft_crs).copy()
    end_gdf["geometry"] = (
        end_gdf["geometry"]
        .apply(lambda g: Point([g.coords[-1][0], g.coords[-1][1]]))
        .buffer(max_dist)
    )

    # Spatial join to find overlapping points
    all_candidates = start_gdf.sjoin(end_gdf)

    all_candidates = all_candidates[
        all_candidates[id_col + "_left"] != all_candidates[id_col + "_right"]
    ]
    # Only keep overlapping points of the same specified dissolve_cols
    for col in dissolve_cols:
        all_candidates = all_candidates[
            all_candidates[col + "_left"] == all_candidates[col + "_right"]
        ]

    # Create a list of chains
    chains = chain_curbs(all_candidates)

    merged_lines_gdf = gpd.GeoDataFrame([])
    gdf_copy = gdf.set_index(id_col)

    # Iterate for each chained group and create new geometries
    for group_n in chains:
        merged_line = []
        for item in group_n:
            geom = gdf_copy["geometry"][item].coords[:]
            merged_line = geom + merged_line
        gdf_n = gpd.GeoDataFrame(
            data={id_col: [group_n[0]], "geometry": [LineString(merged_line)]}
        )
        merged_lines_gdf = pd.concat([merged_lines_gdf, gdf_n])

    # Append the remaining columns
    merged_lines_gdf = gdf.drop("geometry", axis=1).merge(
        merged_lines_gdf, on="curb_id"
    )

    # Create new df for output
    no_merge_lines = gdf[
        ~(
            gdf[id_col].isin(all_candidates[id_col + "_left"])
            | (gdf[id_col].isin(all_candidates[id_col + "_right"]))
        )
    ]

    curbs = pd.concat([no_merge_lines, merged_lines_gdf]).to_crs("EPSG:4326")

    # Rewrite lat, lon for start and end points, and curb length
    curbs["start_lon"] = curbs["geometry"].apply(lambda g: g.coords[0][0])
    curbs["start_lat"] = curbs["geometry"].apply(lambda g: g.coords[0][1])
    curbs["end_lon"] = curbs["geometry"].apply(lambda g: g.coords[-1][0])
    curbs["end_lat"] = curbs["geometry"].apply(lambda g: g.coords[-1][1])
    curbs["curb_length_ft"] = curbs.to_crs(ft_crs).length

    return curbs


def format_curb_blockfaces_for_postgres(
    curb_blockfaces: gpd.GeoDataFrame,
    job_id: uuid.UUID,
    adjust_geom: bool = True,
) -> tuple[gpd.GeoDataFrame, dict[str, dict[str | int, str | uuid.UUID]]] | None:
    """
    Formats the curb blockfaces GeoDataFrame to be compatible with
    the PostgreSQL "curb_blockfaces" table by ensuring the active
    geometry column is named "geography".

    If the input is not a GeoDataFrame or does not contain an active
    geometry column, an appropriate error is raised.
    The function
    returns the formatted GeoDataFrame or None if any adjustments
    lead to an invalid state.

    Args:
        curb_blockfaces (gpd.GeoDataFrame): Expected GeoDataFrame that contains an
            active geometry column.
        job_id (uuid.UUID): Unique identifier for the job that generated the curb
            blockfaces.
        adjust_geom (bool): If True, then the blockface geometries will be adjusted
            based on the direction of flow.

    Returns:
        GeoDataFrame: Returns a GeoDataFrame with the geometry column renamed
            (if needed) to "geography".
        Dict: Returns a dictionary mapping curb IDs to blockface UUIDs and job UUID.

        Returns None if no valid formatted DataFrame is produced.

    Raises:
        TypeError: If the input is not of type geopandas.GeoDataFrame.
        ValueError: If the GeoDataFrame contains no active geometry column.
    """

    # Check the input type
    if not isinstance(curb_blockfaces, gpd.GeoDataFrame):
        raise TypeError(
            "Curb blockfaces must be in a gpd.GeoDataFrame for Postgres table."
        )

    # Identify active geometry column
    geom_col = curb_blockfaces["geometry"].name
    if geom_col is None:
        raise ValueError(
            "No active geometry column found in curb blockfaces geoDataFrame."
        )

    # Rename the geometry column if needed
    if geom_col != "geography":
        curb_blockfaces = curb_blockfaces.rename(columns={geom_col: "geography"})
        curb_blockfaces = curb_blockfaces.set_geometry("geography")

    # Create UUID for each curb blockface
    curb_blockfaces["blockface_id"] = [
        uuid.UUID(uuid.uuid4().hex) for _ in range(len(curb_blockfaces))
    ]
    curb_blockfaces["job_id"] = job_id

    # Determine the direction of traffic flow with respect to the digitization direction
    curb_blockfaces["direction_of_flow"] = determine_direction_of_flow(curb_blockfaces)

    # Adjust geometries if needed
    # (adjust the geometries of blockfaces based on the direction of flow)
    if adjust_geom:
        curb_blockfaces = apply_flow_direction(curb_blockfaces)

    # Determine if the curb line is on the left side of a one-way street with
    # respect to the direction of travel
    curb_blockfaces = add_is_left_side_oneway(curb_blockfaces)

    # Create a mapping dictionary
    mapping_dict = {}
    for col in ["blockface_id", "job_id", "is_left_side_oneway", "geography"]:
        mapping_dict[col] = dict(
            zip(curb_blockfaces["curb_id"], curb_blockfaces[col], strict=False)
        )

    # Create a formatted geoDataFrame
    final_columns = ["blockface_id", "job_id", "geography", "is_left_side_oneway"]

    return curb_blockfaces[final_columns].reset_index(drop=True), mapping_dict


def determine_direction_of_flow(gdf: gpd.GeoDataFrame) -> pd.Series:
    """Determine the direction of flow for each curb blockface
    based on the operation, side, and oneway direction of the roadway.
    """
    direction = np.select(
        condlist=[
            gdf["operation"].isin([1, 3]) & (gdf["oneway"] == "FT"),
            gdf["operation"].isin([1, 3]) & (gdf["oneway"] == "TF"),
            (gdf["operation"] == 2) & (gdf["side"] == "right"),
            (gdf["operation"] == 2) & (gdf["side"] == "left"),
        ],
        choicelist=[
            "forward",
            "reverse",
            "forward",
            "reverse",
        ],
        default=None,
    )
    return pd.Series(direction)


def apply_flow_direction(
    gdf: gpd.GeoDataFrame,
    direction_col: str = "direction_of_flow",
) -> gpd.GeoDataFrame:
    """
    Reverse line geometry when direction_of_flow is 'reverse'
    and set direction_of_flow to 'forward'.

    Args:
        gdf (gpd.GeoDataFrame): Input GeoDataFrame with curb line geometries.
        direction_col (str): Column indicating the flow direction
            ('forward' or 'reverse').

    Returns:
        gpd.GeoDataFrame: GeoDataFrame with corrected line directions and updated
            flow flag.
    """

    def reverse_geometry(geom) -> LineString | MultiLineString | None:
        if geom is None:
            return geom

        if isinstance(geom, LineString):
            return LineString(list(geom.coords)[::-1])

        if isinstance(geom, MultiLineString):
            return MultiLineString(
                [LineString(list(line.coords)[::-1]) for line in geom.geoms]
            )

        return geom

    gdf = gdf.copy()

    mask = gdf[direction_col] == "reverse"

    gdf.loc[mask, gdf.geometry.name] = gdf.loc[mask, gdf.geometry.name].apply(
        reverse_geometry
    )
    gdf.loc[mask, direction_col] = "forward"

    return gdf


def add_is_left_side_oneway(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Add is_left_side_oneway flag based on operation, oneway, and side.
    """
    gdf = gdf.copy()

    mask = gdf["operation"].isin([1]) & (
        ((gdf["oneway"] == "FT") & (gdf["side"] == "left"))
        | ((gdf["oneway"] == "TF") & (gdf["side"] == "right"))
    )
    gdf["is_left_side_oneway"] = mask

    return gdf


def write_blockfaces_to_db(
    gdf: gpd.GeoDataFrame,
    dbname: str,
    schema: str,
    job_name: str,
    job_description: str,
    debug_mode: bool = True,
    adjust_geom: bool = True,
) -> tuple[uuid.UUID, pd.DataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame, str]:
    """
    Writes blockface data to a database and creates a blockface job record for the data.

    This function processes a GeoDataFrame containing blockface data and stores it in a
        specified database schema.
    Additionally, it creates a corresponding record for this data in the
        `blockface_jobs` table, which tracks metadata such as job name and description,
        and generates a unique job ID.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame object containing the blockface data to
            be processed and stored in the database.
        dbname (str): Name of the database where the data will be stored.
        schema (str): Name of the database schema where the data will be saved.
        job_name (str): Name of the blockface job to add as metadata in the
            `blockface_jobs` table.
        job_description (str): A description of the blockface job, providing additional
            context about the data being stored.
        debug_mode (bool): If True, then it will not write the blockface data to
            the database.
        adjust_geom (bool): If True, then the blockface geometries will be adjusted
            based on the direction of flow.

    Returns:
        pd.DataFrame: The processed blockface job metadata as a pandas DataFrame
        gpd.GeoDataFrame: The formatted blockface data as a GeoDataFrame for further
            insertion into the database.
        gpd.DataFrame: The main blockface data as a GeoDataFrame for local storage
        str: The timestamp of the blockface job creation.
    """

    # Add a record to the table blockface_jobs
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        job_id = uuid.uuid4().hex
        timestamp = get_today(include_time=True)
        blockface_job = pd.DataFrame(
            {
                "job_id": [uuid.UUID(job_id)],
                "job_name": [f"[{timestamp}] {job_name}"],
                "job_description": [f"[{timestamp}] {job_description}"],
                "job_timestamp": [datetime.strptime(timestamp, "%Y%m%d-%H%M%S")],
            }
        )

        curb_bf, mapping_dict = format_curb_blockfaces_for_postgres(
            gdf, uuid.UUID(job_id), adjust_geom
        )

        if not bool(debug_mode):
            db.append_data("blockface_jobs", blockface_job)
            db.append_data("curb_blockfaces", curb_bf)

        # Add UUIDs and other information to a local version of curb blockfaces
        local_geometry_name = gdf.geometry.name
        if adjust_geom:
            gdf = gdf.drop(columns=[local_geometry_name])

        for col, d in mapping_dict.items():
            gdf[col] = gdf["curb_id"].map(d)

        gdf = gpd.GeoDataFrame(gdf, geometry=curb_bf.geometry.name)

        if gdf.geometry.name != "geometry":
            gdf = gdf.rename(columns={gdf.geometry.name: "geometry"})
            gdf = gdf.set_geometry("geometry")

        return uuid.UUID(job_id), blockface_job, curb_bf, gdf, timestamp


def write_gdf_to_file(
    job_id: uuid.UUID,
    timestamp: str,
    output_gdf: gpd.GeoDataFrame,
    output_path: str | os.PathLike,
    file_type: str = "GeoJSON",
    output_crs: str = "epsg:4326",
) -> None:
    """
    Write the curb GeoDataFrame to a file in a specified format.

    Args:
        job_id (UUID): UUID of the blockface job that generated the curb blockfaces.
        timestamp (str): Timestamp of the blockface job creation.
        output_gdf (gpd.GeoDataFrame): GeoDataFrame to write
        output_path (str): Location to write file
        file_type (str): Output format
        output_crs (str): Output CRS

    Returns:
        None

    Raises:
        ValueError: If File Type specified is not either `GeoJSON` or `Parquet`
    """
    # Ensure appropriate CRS is set
    try:
        if output_gdf.crs:
            output_gdf = output_gdf.to_crs(output_crs)
        else:
            output_gdf = output_gdf.set_crs(output_crs)
    except ValueError:
        raise ValueError("Output CRS was incorrect or unsupported.") from None

    # Export
    output_file_base = os.path.join(
        output_path, f"curb_blockfaces_job_id_{job_id}_{timestamp}"
    )
    if file_type.lower() == "geojson":
        output_gdf.to_file(Path(f"{output_file_base}.geojson"), driver=file_type)
    elif file_type.lower() == "parquet":
        output_gdf.to_parquet(Path(f"{output_file_base}.parquet"))
    else:
        raise ValueError("File Type must be GeoJSON or Parquet")
