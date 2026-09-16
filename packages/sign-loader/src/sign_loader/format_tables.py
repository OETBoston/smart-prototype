"""
This module contains functions to format the signs geodataframe into tables
for upload to the staging database.
"""

import datetime
import uuid

import geopandas as gpd
import pandas as pd
from curb_utils.logging import get_logger


def add_columns_for_tbls(df: pd.DataFrame, col_lst: list) -> pd.DataFrame:
    """Add any necessary columns to the dataframe for db table format."""
    for col in col_lst:
        if col not in df.columns:
            df[col] = None
    return df[col_lst]


def format_asset_jobs(job_id: str, config: dict) -> pd.DataFrame:
    """Formats data for asset_jobs table."""
    asset_jobs = pd.DataFrame(
        {
            "job_id": [job_id],
            "job_name": [config["job_name"]],
            "job_description": [config["job_description"]],
        }
    )
    return asset_jobs


def format_data_sources(data_source_id: str, config: dict) -> pd.DataFrame:
    """Formats data for data_sources table."""
    data_sources = pd.DataFrame(
        {
            "data_source_id": [data_source_id],
            "source_name": [config["data_source_name"]],
        }
    )
    return data_sources


def format_asset_locations(
    base_signs: gpd.GeoDataFrame, data_source_id: str, job_id: str, config: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Formats data for asset_locations table and returns an asset location
    id lookup dataframe for merging with signs."""
    # Determine SRID for EWKT so inserts match the geometry(point, 4326) column.
    try:
        srid = base_signs.crs.to_epsg() if base_signs.crs else None
    except Exception:
        srid = None
    srid = srid or 4326

    if "source_location_id" in base_signs.columns:
        # Sources (e.g. Survey123) that carry a real location id: one location
        # per geometry, using the provided source location id.
        asset_locations = (
            base_signs.groupby("geometry")["source_location_id"]
            .first()
            .to_frame(name="source_location_id")
            .reset_index()
        )
    else:
        if config["data_source_name"].lower() == "cartegraph":
            sign_id_col = config["cartegraph_required_columns"]["source_sign_id"]
        else:
            sign_id_col = (
                config.get("other_data_source", {})
                .get("optional_columns", {})
                .get("source_sign_id", None)
            )
        if "source_sign_id" in base_signs.columns:
            asset_locations = (
                base_signs.groupby("geometry")["source_sign_id"]
                .apply(
                    lambda x: (
                        f"{sign_id_col}: " + ", ".join(str(v) for v in x if pd.notna(v))
                    )
                )
                .to_frame(name="source_location_id")
                .reset_index()
            )
        else:
            asset_locations = base_signs[["geometry"]].drop_duplicates()
            asset_locations["source_location_id"] = None
    asset_locations["asset_location_id"] = [
        str(uuid.uuid4().hex) for _ in range(len(asset_locations))
    ]
    asset_locations["data_source_id"] = data_source_id
    asset_locations["job_id"] = job_id
    # Convert geometry to WKT for database storage
    asset_locations["location"] = asset_locations["geometry"].apply(
        lambda geom: f"SRID={srid};{geom.wkt}"
    )
    asset_lu = asset_locations[["geometry", "asset_location_id"]]
    asset_locations = asset_locations[
        [
            "asset_location_id",
            "data_source_id",
            "job_id",
            "source_location_id",
            "location",
        ]
    ]
    return asset_locations, asset_lu


def format_signs(
    base_signs: gpd.GeoDataFrame,
    data_source_id: str,
    job_id: str,
    asset_lu: pd.DataFrame,
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Formats data for signs table and returns updated base signs dataframe
    for sign_id in images tables."""
    base_signs["sign_id"] = [str(uuid.uuid4().hex) for _ in range(len(base_signs))]
    base_signs["data_source_id"] = data_source_id
    base_signs["job_id"] = job_id

    if "notes_col" in config and config["notes_col"] in base_signs.columns:
        base_signs["sign_notes"] = base_signs[config["notes_col"]]
    else:
        base_signs["sign_notes"] = None

    signs = base_signs.merge(asset_lu, on="geometry").rename(
        columns={"asset_location_id": "sign_location_id"}
    )
    sign_cols = [
        "sign_id",
        "sign_location_id",
        "data_source_id",
        "job_id",
        "source_sign_id",
        "added_date",
        "sign_removed_date",
        "sign_type_code",
        "sign_notes",
    ]
    signs = add_columns_for_tbls(signs, sign_cols)
    return signs, base_signs


def format_images(base_signs: pd.DataFrame) -> pd.DataFrame:
    """Formats data for images table.

    Supports two shapes of input:
      - an ``attachments`` list column (one dict ``{uri, source_image_id}`` per
        photo), which is exploded to one image row per photo; or
      - a single ``uri`` column (one image per sign), as used by other sources.
    """
    image_cols = [
        "image_id",
        "sign_id",
        "data_source_id",
        "job_id",
        "uri",
        "image_date",
        "source_image_id",
    ]

    if "attachments" in base_signs.columns:
        keep = ["sign_id", "data_source_id", "job_id", "attachments"]
        images = base_signs[keep].explode("attachments")
        images = images[images["attachments"].notna()].copy()
        if not images.empty:
            images["uri"] = images["attachments"].apply(
                lambda a: a.get("uri") if isinstance(a, dict) else a
            )
            images["source_image_id"] = images["attachments"].apply(
                lambda a: a.get("source_image_id") if isinstance(a, dict) else None
            )
        else:
            images["uri"] = None
            images["source_image_id"] = None
    elif "uri" in base_signs.columns:
        images = base_signs[base_signs["uri"].notnull()].copy()
    else:
        images = pd.DataFrame(
            columns=["sign_id", "data_source_id", "job_id", "uri", "source_image_id"]
        )

    images["image_id"] = [str(uuid.uuid4().hex) for _ in range(len(images))]
    images["image_date"] = datetime.datetime.now()
    images = add_columns_for_tbls(images, image_cols)
    return images


def format_sign_tbls(signs_gdf: gpd.GeoDataFrame, config: dict) -> dict:
    """Format signs geodataframe into tables for asset_jobs, data_sources,
    asset_locations, signs, and images. Order of tables created matters.
    """
    logger = get_logger(__name__)
    logger.info("Formatting %d signs into database tables", len(signs_gdf))
    base_signs = signs_gdf.copy()

    # Format for asset_jobs table
    job_id = str(uuid.uuid4().hex)
    asset_jobs = format_asset_jobs(job_id=job_id, config=config)
    logger.info("Sucessfully formatted asset_jobs table")

    # Format for data_sources table
    data_source_id = str(uuid.uuid4().hex)
    data_sources = format_data_sources(data_source_id=data_source_id, config=config)
    logger.info("Sucessfully formatted data_sources table")

    # Format for asset_locations table
    asset_locations, asset_lu = format_asset_locations(
        base_signs=base_signs,
        data_source_id=data_source_id,
        job_id=job_id,
        config=config,
    )

    logger.info("Sucessfully formatted asset_locations table")

    # Format for signs table
    signs, base_signs = format_signs(
        base_signs=base_signs,
        data_source_id=data_source_id,
        job_id=job_id,
        asset_lu=asset_lu,
        config=config,
    )
    logger.info("Sucessfully formatted signs table")

    # Format for images table
    images = format_images(base_signs=base_signs)
    logger.info("Sucessfully formatted images table")

    to_upload_dict = {
        "asset_jobs": asset_jobs,
        "data_sources": data_sources,
        "asset_locations": asset_locations,
        "signs": signs,
        "images": images,
    }
    logger.info("Successfully formatted tables for upload")
    return to_upload_dict
