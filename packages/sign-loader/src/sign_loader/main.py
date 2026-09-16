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

from pathlib import Path

import geopandas as gpd
from curb_utils.db_utils import SmartCurbDB
from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import get_logger
from dotenv import load_dotenv
from format_tables import format_sign_tbls
from preprocess import (
    load_cartegraph_signs,
    preprocess_cartegraph_signs,
    preprocess_other_signs,
)
from survey123 import load_survey123, load_survey_shapefile
from utils import check_required_input_columns


def upload_sign_tbls(
    upload_dict: dict,
    dbname: str,
    schema: str,
    debug_mode: bool = False,
) -> None:
    """Upload tables to database.
    If debug_mode is True, does not write to DB."""
    logger = get_logger(__name__)
    logger.info(
        "Starting upload to database %s.%s (debug_mode=%s)", dbname, schema, debug_mode
    )

    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        for tbl_name, df in upload_dict.items():
            if not debug_mode:
                db.append_data(tbl_name, df)
                logger.info("Uploaded %d rows to table %s", len(df), tbl_name)
            else:
                logger.info(
                    "[DEBUG MODE] Would upload %d rows to table %s", len(df), tbl_name
                )


def main() -> None:
    """Main function to run the ETL process for loading parking sign data
    into the database."""
    base_path = Path(__file__).resolve().parent.parent.parent
    logger = get_logger(__name__)
    logger.info("=" * 80)
    logger.info("Starting Signs Uploader Pipeline")
    logger.info("=" * 80)
    try:
        # Read in config & files
        logger.info("Loading configuration and input files...")

        config = load_from_yaml(base_path / "config.yaml")
        logger.info("Loaded config from %s", f"{base_path / 'config.yaml'}")
        if config["data_source_name"].lower() == "cartegraph":
            # Clean for relevant signs

            cartegraph_df = load_cartegraph_signs(base_path=base_path, config=config)
            check_required_input_columns(
                config["cartegraph_required_columns"], cartegraph_df
            )
            signs_gdf = preprocess_cartegraph_signs(
                signs_df=cartegraph_df, config=config, base_path=base_path
            )

        elif config["data_source_name"].lower() in ("survey123", "arcgis"):
            survey_cfg = config.get("survey123", {})
            if survey_cfg.get("use_shapefile_fallback"):
                logger.info("Loading survey data from local shapefile export...")
                signs_gdf = load_survey_shapefile(config=config, base_path=base_path)
            else:
                logger.info("Loading survey data from ArcGIS feature service...")
                signs_gdf = load_survey123(config=config, base_path=base_path)
            logger.info("Loaded %d survey sign records", len(signs_gdf))

        else:
            # assume formatted geospatial file
            signs_gdf = gpd.read_file(
                base_path / config["signs_path"], crs=config["input_crs"]
            )

            check_required_input_columns(
                config["other_data_source"]["required_columns"], signs_gdf
            )
            signs_gdf = preprocess_other_signs(signs_gdf=signs_gdf, config=config)
            logger.info("Loaded signs from %s", f"{base_path / config['signs_path']}")

        # Format signs for database tbls
        to_upload_dict = format_sign_tbls(signs_gdf=signs_gdf, config=config)

        # Upload signs to database
        upload_sign_tbls(
            upload_dict=to_upload_dict,
            dbname=config["dbname"],
            schema=config["schema"],
            debug_mode=config["debug_mode"],
        )

        logger.info("=" * 80)
        logger.info("Pipeline completed successfully!")
        logger.info("=" * 80)
    except Exception as e:
        logger.error("Pipeline failed with error: %s", str(e), exc_info=True)
        raise


if __name__ == "__main__":
    logger = get_logger(__name__)
    logger.info("Running Sign Loader Pipeline Process...")
    load_dotenv()
    main()
