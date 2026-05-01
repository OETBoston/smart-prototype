"""
==============================================================================
Main Script for Signs Preprocessing and Loading Pipeline
==============================================================================
This script runs the ETL process for loading parking sign data  from Cartegraph
into the database. Configuration parameters are loaded from `config.yaml` to ensure
consistency and reproducibility across runs.

Usage:
    python main.py

Ensure that all dependencies are installed and configuration paths are correctly
set before running the script.
==============================================================================
"""

import datetime
import logging
import uuid

import geopandas as gpd
import pandas as pd
from cg import load_cartegraph_signs, preprocess_cartegraph_signs
from curb_utils.db_utils import SmartCurbDB
from curb_utils.io_tools import load_config
from dotenv import load_dotenv
from utils import setup_logging


def add_columns_for_tbls(df: pd.DataFrame, col_lst: list) -> pd.DataFrame:
    """Add any necessary columns to the dataframe for db table format."""
    for col in col_lst:
        if col not in df.columns:
            df[col] = None
    return df[col_lst]


def format_sign_tbls(
    signs_gdf: gpd.GeoDataFrame, config: dict, logger: logging.Logger
) -> dict:
    """Format signs geodataframe into tables for asset_jobs, data_sources,
    asset_locations, signs, and images."""
    logger.info("Formatting %d signs into database tables", len(signs_gdf))
    base_signs = signs_gdf.copy()

    # Ensure column names are the same (if these columns exist in the df)
    rename_dict = {}
    col_mapping = {
        "sign_id_col": "source_sign_id",
        "attachment_id_col": "source_image_id",
        "geometry_col": "geometry",
        "uri_col": "uri",
    }
    for config_key, target_name in col_mapping.items():
        if config_key in config and config[config_key] in base_signs.columns:
            rename_dict[config[config_key]] = target_name
    base_signs = base_signs.rename(columns=rename_dict)

    # Format for asset_jobs table
    job_id = str(uuid.uuid4().hex)
    asset_jobs = pd.DataFrame(
        {
            "job_id": [job_id],
            "job_name": [config["job_name"]],
            "job_description": [config["job_description"]],
        }
    )
    logger.info("Sucessfully formatted asset_jobs table")

    # Format for data_sources table
    data_source_id = str(uuid.uuid4().hex)
    data_sources = pd.DataFrame(
        {
            "data_source_id": [data_source_id],
            "source_name": [config["data_source_name"]],
        }
    )
    logger.info("Sucessfully formatted data_sources table")

    # Format for asset_locations table
    if "source_sign_id" in base_signs.columns:
        asset_locations = (
            base_signs.groupby("geometry")["source_sign_id"]
            .apply(
                lambda x: (
                    f"{config['sign_id_col']}: "
                    + ", ".join(str(v) for v in x if pd.notna(v))
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
        lambda geom: geom.wkt
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

    logger.info("Sucessfully formatted asset_locations table")

    # Format for signs table
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
    logger.info("Sucessfully formatted signs table")

    # Format for images table
    images = base_signs[base_signs["uri"].notnull()]
    images["image_id"] = [str(uuid.uuid4().hex) for _ in range(len(images))]
    images["image_date"] = datetime.datetime.now()
    image_cols = [
        "image_id",
        "sign_id",
        "data_source_id",
        "job_id",
        "uri",
        "image_date",
        "source_image_id",
    ]
    images = add_columns_for_tbls(images, image_cols)
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


def upload_sign_tbls(
    upload_dict: dict,
    dbname: str,
    schema: str,
    logger: logging.Logger,
    debug_mode: bool = False,
) -> None:
    """Upload tables to database.
    If debug_mode is True, does not write to DB."""
    logger.info(
        "Starting upload to database %s.%s (debug_mode=%s)", dbname, schema, debug_mode
    )
    load_dotenv()
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        for tbl_name, df in upload_dict.items():
            if not bool(debug_mode):
                db.append_data(tbl_name, df)
                logger.info("Uploaded %d rows to table %s", len(df), tbl_name)
            else:
                logger.info(
                    "[DEBUG MODE] Would upload %d rows to table %s", len(df), tbl_name
                )


def main() -> None:
    """Main function to run the ETL process for loading parking sign data
    into the database."""
    base_path = "./packages/sign-loader"
    logger = setup_logging()
    logger.info("=" * 80)
    logger.info("Starting Signs Uploader Pipeline")
    logger.info("=" * 80)
    try:
        # Read in config & files
        logger.info("Loading configuration and input files...")
        config = load_config(f"{base_path}/config.yaml")
        # TODO: this file is optional
        neighborhoods_gdf = gpd.read_file(
            f"{base_path}/{config['neighborhoods_path']}",
            crs=config["neighborhoods_crs"],
        )[["name", "geometry"]]
        logger.info(
            "Loaded neighborhoods from %s", f"{base_path}{config['neighborhoods_path']}"
        )
        if config["data_source_name"].lower() == "cartegraph":
            # Clean for relevant signs

            cartegraph_df = load_cartegraph_signs(base_path=base_path, config=config)

            signs_gdf = preprocess_cartegraph_signs(
                signs_df=cartegraph_df,
                neighborhoods_gdf=neighborhoods_gdf,
                config=config,
            )
        else:
            # assume formatted geospatial file
            signs_gdf = gpd.read_file(
                f"{base_path}{config['signs_path']}", crs=config["input_crs"]
            )
            if signs_gdf.crs != config["output_crs"]:
                signs_gdf = signs_gdf.to_crs(config["output_crs"])
            logger.info("Loaded signs from %s", f"{base_path}{config['signs_path']}")

        # Format signs for database tbls
        to_upload_dict = format_sign_tbls(
            signs_gdf=signs_gdf, config=config, logger=logger
        )

        # Upload signs to database
        upload_sign_tbls(
            upload_dict=to_upload_dict,
            dbname=config["dbname"],
            schema=config["schema"],
            logger=logger,
            debug_mode=config["debug_mode"],
        )

        logger.info("=" * 80)
        logger.info("Pipeline completed successfully!")
        logger.info("=" * 80)
    except Exception as e:
        logger.error("Pipeline failed with error: %s", str(e), exc_info=True)
        raise


if __name__ == "__main__":
    main()
