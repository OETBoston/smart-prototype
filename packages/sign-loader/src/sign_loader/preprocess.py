import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
from curb_utils.logging import get_logger
from shapely import Point
from utils import filter_by_column_values, filter_by_geo, read_and_reproject_gdf


def load_cartegraph_signs(base_path: Path, config: dict) -> pd.DataFrame:
    """Load signs data from Cartegraph export, which is expected to be in a csv file."""
    logger = get_logger(__name__)
    signs_df = pd.read_csv(base_path / config["signs_path"])
    logger.info("Loaded signs from %s", f"{base_path / config['signs_path']}")
    return signs_df


def update_column_names(signs_gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """Update column names to match expected names for database upload."""
    signs_gdf = signs_gdf.rename(
        columns={
            config["source_sign_id"]: "source_sign_id",
            config["source_image_id"]: "source_image_id",
            config["uri"]: "uri",
            config["sign_type_code"]: "sign_type_code",
            config["added_date"]: "added_date",
            "truncated_geometry": "geometry",
        }
    )
    output_cols = [
        "source_sign_id",
        "source_image_id",
        "sign_type_code",
        "added_date",
        "sign_removed_date",
        "uri",
        "geometry",
    ]
    return signs_gdf[output_cols]


def preprocess_cartegraph_signs(
    signs_df: pd.DataFrame, config: dict, base_path: Path
) -> gpd.GeoDataFrame:
    """Preprocess signs data by filtering for parking signs,
    removing duplicates, and grouping nearby signs together."""
    logger = get_logger(__name__)
    logger.info("Starting preprocessing with %d total signs", len(signs_df))

    # Filter out signs with missing lat/long
    signs_df = signs_df[
        (signs_df["longitude"].notnull())
        & signs_df["latitude"].notnull()
        & (signs_df["mutcd_code_field"].notnull())
    ]
    signs_df["geometry"] = pd.Series(
        [
            Point(xy)
            for xy in zip(signs_df["longitude"], signs_df["latitude"], strict=True)
        ],
        index=signs_df.index,
    )

    # Filter for duplicates by keeping the most recently modified record
    config_req_cols = config["cartegraph_required_columns"]
    sign_date_col = config_req_cols["date_columns"]["sign_modified_date"]
    image_date_col = config_req_cols["date_columns"]["attachment_modified_date"]
    signs_df = signs_df.sort_values(
        [sign_date_col, image_date_col], ascending=False
    ).drop_duplicates(subset=config_req_cols["source_sign_id"], keep="first")
    logger.info("Removed duplicates: %d unique signs", len(signs_df))

    if config.get("column_filters"):
        for column_filter in config["column_filters"]:
            signs_df = filter_by_column_values(
                signs_df,
                column=column_filter["column"],
                values=column_filter["values"],
                mode=column_filter["mode"],
            )
            logger.info(
                "Applied column filter on %s with mode %s: %d signs remaining",
                column_filter["column"],
                column_filter["mode"],
                len(signs_df),
            )

    # Make gdf
    signs_gdf = gpd.GeoDataFrame(signs_df, geometry="geometry", crs=config["input_crs"])
    if signs_gdf.crs != config["output_crs"]:
        signs_gdf = signs_gdf.to_crs(config["output_crs"])

    # Filter for geographic subset if specified in config
    if config.get("geo_filter"):
        polygon_gdf = read_and_reproject_gdf(
            path=base_path / config["geo_filter"]["path"],
            output_crs=config["output_crs"],
        )

        # get optional selectors for filtering the polygons
        subset_column = config["geo_filter"].get("subset_column")
        subset_values = config["geo_filter"].get("subset_values")

        signs_gdf = filter_by_geo(
            gdf_points=signs_gdf,
            gdf_polygons=polygon_gdf,
            subset_column=subset_column,
            subset_values=subset_values,
        )
        logger.info(
            "Applied neighborhoods filter: %d signs remaining",
            len(signs_gdf),
        )

    # Reduce geometric precision to better group nearby signs together.
    grouping_distance = config["grouping_parameters"]["grouping_distance_ft"]
    grouping_crs = config["grouping_parameters"]["grouping_crs"]
    signs_gdf["truncated_geometry"] = (
        signs_gdf["geometry"]
        .to_crs(grouping_crs)
        .apply(
            lambda p: Point(
                math.floor(p.x / grouping_distance) * grouping_distance,
                math.floor(p.y / grouping_distance) * grouping_distance,
            )
        )
        .to_crs(config["output_crs"])
    )

    # Create sign_removed_date column if marked as removed
    signs_gdf["sign_removed_date"] = signs_gdf["cg_last_modified_field"].where(
        signs_gdf["asset_status_field"] == "Removed"
    )

    date_cols = [sign_date_col, image_date_col]
    signs_gdf[date_cols] = signs_gdf[date_cols].apply(pd.to_datetime)
    signs_gdf.drop(columns=["geometry"], inplace=True)
    signs_gdf.set_geometry("truncated_geometry", inplace=True)

    signs_gdf = update_column_names(signs_gdf, config_req_cols)
    logger.info("Preprocessing complete: %d signs processed", len(signs_gdf))
    return signs_gdf


def preprocess_other_signs(
    signs_gdf: gpd.GeoDataFrame, config: dict
) -> gpd.GeoDataFrame:
    """Preprocess signs data from other sources by renaming columns and
    updating CRS (if needed)."""
    # Reproject to output crs if needed
    if signs_gdf.crs != config["output_crs"]:
        signs_gdf = signs_gdf.to_crs(config["output_crs"])

    # Ensure column names are the same (if these columns exist in the df)
    other_data_source_config = config["other_data_source"]
    rename_dict = {}
    for col_typ in ["required_columns", "optional_columns"]:
        for clean_col, og_col in other_data_source_config[col_typ].items():
            if og_col in signs_gdf.columns:
                rename_dict[og_col] = clean_col
    signs_gdf = signs_gdf.rename(columns=rename_dict)
    return signs_gdf
