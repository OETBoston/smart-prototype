import math

import geopandas as gpd
import pandas as pd
from shapely import Point
from utils import filter_by_column_values, filter_by_geo
from curb_utils.logging import get_logger

logger = get_logger(__name__)


def load_cartegraph_signs(base_path: str, config: dict) -> pd.DataFrame:
    """Load signs data from Cartegraph export, which is expected to be in a csv file."""
    signs_df = pd.read_csv(f"{base_path}/{config['signs_path']}")
    logger.info("Loaded signs from %s", f"{config['signs_path']}")
    return signs_df


def preprocess_cartegraph_signs(
    signs_df: pd.DataFrame,
    config: dict,
) -> gpd.GeoDataFrame:
    """Preprocess signs data by filtering for parking signs,
    removing duplicates, and grouping nearby signs together."""

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
    signs_df = signs_df.sort_values(
        ["cg_last_modified_field", "attachment_cg_last_modified_field"],
        ascending=False
    ).drop_duplicates(subset=config["sign_id_col"], keep="first")
    logger.info("Removed duplicates: %d unique signs", len(signs_df))

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
    if config.get("geo_filters"):
        signs_gdf = filter_by_geo(signs_gdf, config)
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

    date_cols = ["entry_date_field", "cg_last_modified_field"]
    signs_gdf[date_cols] = signs_gdf[date_cols].apply(pd.to_datetime)
    signs_gdf.drop(columns=["geometry"], inplace=True)
    signs_gdf.set_geometry("truncated_geometry", inplace=True)

    # TODO: Move mappping of column names to a separate function.
    # Should this be an earlier step?
    # We should make all of this configurable
    # and required.
    signs_gdf = signs_gdf.rename(
        columns={
            config["sign_id_col"]: "source_sign_id",
            config["attachment_id_col"]: "source_image_id",
            "mutcd_code_field": "sign_type_code",
            "entry_date_field": "added_date",
            config["uri_col"]: "uri",
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

    logger.info("Preprocessing complete: %d signs processed", len(signs_gdf))
    return signs_gdf[output_cols]
