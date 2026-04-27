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
import math
import os
import uuid
from dotenv import load_dotenv
import geopandas as gpd
import pandas as pd
from shapely import Point

from curb_utils.io_tools import load_config
from curb_utils.db_utils import SmartCurbDB


def setup_logging() -> logging.Logger:
    """Configure logging to write to both console and file."""
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(f"logs/cartegraph_loader_{timestamp}.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def preprocess_signs(
        signs_df: pd.DataFrame,
        neighborhoods_gdf: gpd.GeoDataFrame,
        config: dict,
        logger: logging.Logger
    ) -> gpd.GeoDataFrame:
    """Preprocess signs data by filtering for parking signs,
        removing duplicates, and grouping nearby signs together."""
    logger.info("Starting preprocessing with %d total signs", len(signs_df))
    # filter out signs with missing lat/long
    no_nulls = signs_df[
        (signs_df["longitude"].notnull()) & \
                signs_df["latitude"].notnull() & \
                (signs_df["mutcd_code_field"].notnull())
    ]
    no_nulls["geometry"] = pd.Series([
        Point(xy) for xy in zip(no_nulls["longitude"], no_nulls["latitude"])
    ], index=no_nulls.index)

    # filter for known parking signs
    sign_filter = "|".join(
        f"{code.lower()}*" for code in config["parking_mutcd_codes"]
    )

    parking_df = no_nulls[
        no_nulls["mutcd_code_field"].str.lower().str.match(sign_filter)
    ]
    logger.info("Filtered to %d parking signs", len(parking_df))

    # filter for duplicates by keeping the most recently modified record
    no_dupes = parking_df.sort_values(
        ["cg_last_modified_field", "attachment_cg_last_modified_field"],
        ascending=False
    ).drop_duplicates(subset="oid", keep="first")
    logger.info("Removed duplicates: %d unique signs", len(no_dupes))

    # filter out based on status
    valid_signs = no_dupes[
        ~no_dupes["asset_status_field"].isin(config["status_filters"])
    ]
    logger.info("Filtered by status: %d valid signs", len(valid_signs))

    # make gdf
    signs_gdf = gpd.GeoDataFrame(
        valid_signs,
        geometry="geometry",
        crs="EPSG:4326"
    )

    # filter for specific neighboorhood if specified
    if config["neighborhoods"]:
        spec_neighborhood = neighborhoods_gdf[
            neighborhoods_gdf["name"].isin(config["neighborhoods"])
        ]
        signs_gdf = gpd.sjoin(
            signs_gdf,
            spec_neighborhood,
            predicate="within",
            how="inner"
        )
        logger.info(
            "Filtered by neighborhoods: %d valid signs in %s neighborhoods",
            len(signs_gdf),
            config["neighborhoods"]
        )

    # group nearby signs together by truncating lat/long to the nearest grouping distance
    grouping_distance = config["grouping_distance_ft"]
    signs_gdf["truncated_geometry"] = signs_gdf["geometry"]. \
        to_crs("epsg:2249").apply(
            lambda p: Point(
                math.floor(p.x / grouping_distance) * grouping_distance,
                math.floor(p.y / grouping_distance) * grouping_distance,
            )
    ).to_crs(config["output_crs"])

    date_cols = ["entry_date_field", "cg_last_modified_field"]
    signs_gdf[date_cols] = signs_gdf[date_cols].apply(pd.to_datetime)
    signs_gdf.set_geometry("truncated_geometry", inplace=True)

    output_cols = [
        "oid",
        "entry_date_field",
        "mutcd_code_field",
        "asset_status_field",
        "attachment_public_url",
        "cg_last_modified_field",
        "truncated_geometry",
        "attachment_oid"
    ]
    logger.info("Preprocessing complete: %d signs processed", len(signs_gdf))
    return signs_gdf[output_cols]


def format_sign_tbls(
        signs_gdf: gpd.GeoDataFrame,
        config: dict,
        logger: logging.Logger
    ) -> dict:
    """Format signs geodataframe into tables for asset_jobs, data_sources,
        asset_locations, signs, and images."""
    logger.info("Formatting %d signs into database tables", len(signs_gdf))
    base_signs = signs_gdf.copy()

    # Format for asset_jobs table
    job_id = str(uuid.uuid4().hex)
    asset_jobs = pd.DataFrame(
        {
            "job_id": [job_id],
            "job_name": [config["job_name"]],
            "job_description": [config["job_description"]]
        }
    )
    logger.info("Sucessfully formatted asset_jobs table")

    # Format for data_sources table
    data_source_id = str(uuid.uuid4().hex)
    data_sources = pd.DataFrame(
        {
            "data_source_id": [data_source_id],
            "source_name": [config["data_source_name"]]
        }
    )
    logger.info("Sucessfully formatted data_sources table")

    # Format for asset_locations table
    asset_locations = base_signs.groupby(
        'truncated_geometry'
    )['oid'].apply(
        lambda x: "oid: " + ', '.join(str(v) for v in x if pd.notna(v))
    ).to_frame(name='source_location_id').reset_index()
    asset_locations["asset_location_id"] = [
        str(uuid.uuid4().hex) for _ in range(len(asset_locations))
    ]
    asset_locations["data_source_id"] = data_source_id
    asset_locations["job_id"] = job_id
    asset_locations = asset_locations.rename(
        columns={
            "truncated_geometry": "location"
        },
    )[
        [
            "asset_location_id",
            "data_source_id",
            "job_id",
            "source_location_id",
            "location"
        ]
    ]
    logger.info("Sucessfully formatted asset_locations table")

    # Format for signs table
    base_signs["sign_id"] = [
        str(uuid.uuid4().hex) for _ in range(len(base_signs))
    ]
    base_signs["data_source_id"] = data_source_id
    base_signs["job_id"] = job_id
    base_signs["sign_notes"] = None
    base_signs["sign_removed_date"] = base_signs["cg_last_modified_field"]. \
        where(
            base_signs["asset_status_field"] == "Removed"
        )
    signs = base_signs.merge(
        asset_locations[['location', 'asset_location_id']],
        left_on='truncated_geometry',
        right_on='location'
    ).rename(
        columns={
            "oid": "source_sign_id",
            "mutcd_code_field": "sign_type_code",
            "entry_date_field": "date_added",
            "asset_location_id": "sign_location_id"
        }
    )[
        [
            'sign_id',
            'sign_location_id',
            'data_source_id',
            'job_id',
            'source_sign_id',
            'date_added',
            'sign_removed_date',
            'sign_type_code',
            'sign_notes'
        ]
    ]
    logger.info("Sucessfully formatted signs table")

    # Format for images table
    images = base_signs[base_signs["attachment_public_url"].notnull()]
    images["image_id"] = [str(uuid.uuid4().hex) for _ in range(len(images))]
    images["image_date"] = datetime.datetime.now()
    images = images.rename(
        columns={
            'attachment_public_url': 'uri',
            'attachment_oid': 'source_image_id'
        }
    )[
        [
            'image_id',
            'sign_id',
            'data_source_id',
            'job_id',
            'uri',
            'image_date',
            'source_image_id'
        ]
    ]
    logger.info("Sucessfully formatted images table")

    to_upload_dict = {
        "asset_jobs": asset_jobs,
        "data_sources": data_sources,
        "asset_locations": asset_locations,
        "signs": signs,
        "images": images
    }
    logger.info("Successfully formatted tables for upload")
    return to_upload_dict


def upload_sign_tbls(
        upload_dict: dict,
        dbname: str,
        schema: str,
        logger: logging.Logger,
        debug_mode: bool = False
) -> None:
    """Upload tables to database.
        If debug_mode is True, does not write to DB."""
    logger.info(
        "Starting upload to database %s.%s (debug_mode=%s)",
        dbname,
        schema,
        debug_mode
    )
    load_dotenv()
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        for tbl_name, df in upload_dict.items():
            if not bool(debug_mode):
                db.append_data(tbl_name, df)
                logger.info("Uploaded %d rows to table %s", len(df), tbl_name)
            else:
                logger.info(
                    "[DEBUG MODE] Would upload %d rows to table %s",
                    len(df),
                    tbl_name
                )


def main():
    """Main function to run the ETL process for loading parking sign data
        into the database."""
    base_path = "packages/cartegraph-loader/src/cartegraph_loader"
    logger = setup_logging()
    logger.info("="*80)
    logger.info("Starting Cartegraph Signs ETL Pipeline")
    logger.info("="*80)
    try:
        # Read in config & files
        logger.info("Loading configuration and input files...")
        config = load_config(
            f"{base_path}/config.yaml"
        )
        signs_df = pd.read_csv(f"{base_path}/{config['signs_path']}")
        logger.info(
            "Loaded %d signs from %s",
            len(signs_df),
            f"{base_path}/{config['signs_path']}"
        )

        neighborhoods_gdf = gpd.read_file(
            f"{base_path}/{config['neighborhoods_path']}",
            crs="EPSG:4326"
        )[["name", "geometry"]]
        logger.info(
            "Loaded neighborhoods from %s",
            f"{base_path}/{config['neighborhoods_path']}"
        )

        # Clean for relevant signs
        cleaned_signs_gdf = preprocess_signs(
            signs_df=signs_df,
            neighborhoods_gdf=neighborhoods_gdf,
            config=config,
            logger=logger,
        )

        # Format signs for database tbls
        to_upload_dict = format_sign_tbls(
            signs_gdf=cleaned_signs_gdf,
            config=config,
            logger=logger
        )

        # Upload signs to database
        upload_sign_tbls(
            upload_dict=to_upload_dict,
            dbname=config["dbname"],
            schema=config["schema"],
            logger=logger,
            debug_mode=config["debug_mode"]
        )

        logger.info("="*80)
        logger.info("ETL Pipeline completed successfully!")
        logger.info("="*80)
    except Exception as e:
        logger.error(
            "ETL Pipeline failed with error: %s",
            str(e),
            exc_info=True
        )
        raise


if __name__ == "__main__":
    main()
