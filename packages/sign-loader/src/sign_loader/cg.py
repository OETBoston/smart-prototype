import logging
import math

import geopandas as gpd
import pandas as pd
from shapely import Point
from utils import filter_by_column_values, filter_by_geo

logger = logging.getLogger(__name__)


def load_cartegraph_signs(base_path: str, config: dict) -> pd.DataFrame:
    """Load signs data from Cartegraph export, which is expected to be in a csv file."""
    signs_df = pd.read_csv(f"{base_path}{config['signs_path']}")
    logger.info("Loaded signs from %s", f"{base_path}{config['signs_path']}")
    return signs_df


def preprocess_cartegraph_signs(
    signs_df: pd.DataFrame,
    neighborhoods_gdf: gpd.GeoDataFrame,  # TODO: Move out of signature -> filter_by_geo
    config: dict,
) -> gpd.GeoDataFrame:
    """Preprocess signs data by filtering for parking signs,
    removing duplicates, and grouping nearby signs together."""

    logger.info("Starting preprocessing with %d total signs", len(signs_df))

    # filter out signs with missing lat/long
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

    # TODO: Should this be first? - I think I see why not.

    # filter for duplicates by keeping the most recently modified record
    signs_df = signs_df.sort_values(
        ["cg_last_modified_field", "attachment_cg_last_modified_field"], ascending=False
    ).drop_duplicates(subset=config["sign_id_col"], keep="first")
    logger.info("Removed duplicates: %d unique signs", len(signs_df))

    # make gdf
    signs_gdf = gpd.GeoDataFrame(signs_df, geometry="geometry", crs=config["input_crs"])
    if signs_gdf.crs != config["output_crs"]:
        signs_gdf = signs_gdf.to_crs(config["output_crs"])

    # TODO:
    #   Build out geospatial filter function above.
    #   Apply geospatial filter instead.
    #   Update config with geo_filters key:
    #       path to gis data
    #       subset_column (e.g. "neighborhood")
    #       subset_values (e.g. list of neighborhoods to keep)
    #

    # placeholder just to keep the import from being unused.
    filter_by_geo()
    if config["neighborhoods"]:
        spec_neighborhood = neighborhoods_gdf[
            neighborhoods_gdf["name"].isin(config["neighborhoods"])
        ]
        if spec_neighborhood.crs != config["output_crs"]:
            spec_neighborhood = spec_neighborhood.to_crs(config["output_crs"])
        signs_gdf = gpd.sjoin(
            signs_gdf, spec_neighborhood, predicate="within", how="inner"
        )
        logger.info(
            "Filtered by neighborhoods: %d valid signs in %s neighborhoods",
            len(signs_gdf),
            config["neighborhoods"],
        )

    # Reduce geometric precision to better group nearby signs together.
    grouping_distance = config["grouping_distance_ft"]
    signs_gdf["truncated_geometry"] = (
        signs_gdf["geometry"]
        # TODO: This is currently hardcoded for EPSG:2249
        #    (Massachusetts State Plane Mainland), which is in feet.
        #    We should ideally make this a config option.
        .to_crs("epsg:2249")
        .apply(
            lambda p: Point(
                math.floor(p.x / grouping_distance) * grouping_distance,
                math.floor(p.y / grouping_distance) * grouping_distance,
            )
        )
        .to_crs(config["output_crs"])
    )

    signs_gdf["sign_removed_date"] = signs_gdf["cg_last_modified_field"].where(
        signs_gdf["asset_status_field"] == "Removed"
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
