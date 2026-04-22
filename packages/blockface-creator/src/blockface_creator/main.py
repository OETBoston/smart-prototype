"""
Run the curb generation algorithm using roadway centerline dataset.
"""

# Packages
import warnings

from curb_utils.io_tools import load_config
from dotenv import load_dotenv

from blockface_creator import curb_generation as cg

# Session settings
load_dotenv()
warnings.filterwarnings("ignore")
logger = cg.get_logger()
logger.info("Running curb generation process...")

if __name__ == "__main__":
    # 0. Load configurations
    config = load_config("packages/blockface-creator/src/blockface_creator/config.yaml")
    logger.info(
        "Configuration loaded. Running on DEBUG_MODE=%s...", config["debug_mode"]
    )

    # 1. Load the roadway centerline dataset
    roadway_shp = cg.read_roadways(
        roadway_path=config["roadway_path"],
        include_filters=config["include_filters"],
        exclude_filters=config["exclude_filters"],
    )
    logger.info("Roadway centerline dataset loaded.")

    # 2. Create curb geometry
    curb_data = cg.create_curbs(
        roadway_shp=roadway_shp, ft_crs=config["ft_crs"], ft_diff=config["ft_diff"]
    )
    logger.info("Curb dataset created with %s curb lines.", f"{len(curb_data):,}")

    # 3. Format and write the curb blockfaces to Postgres
    blockface_job_id, blockface_job, curb_blockfaces, curb_data, timestamp = (
        cg.write_blockfaces_to_db(
            gdf=curb_data,
            dbname=config["dbname"],
            schema=config["schema"],
            job_name=config["job_name"],
            job_description=config["job_description"],
            debug_mode=config["debug_mode"],
            adjust_geom=config["adjust_geometry"],
        )
    )
    logger.info(
        'Updated: "curb_blockfaces" table in "%s" database with "%s" schema.',
        config["dbname"],
        config["schema"],
    )

    # 4. Save the output with UUIDs for QA/mapping
    cg.write_gdf_to_file(
        job_id=blockface_job_id,
        timestamp=timestamp,
        output_gdf=curb_data,
        output_path=config["output_path"],
        file_type=config["output_type"],
        output_crs=config["output_crs"],
    )
    logger.info(
        'Exported: "curb_blockfaces_job_id_%s_%s.%s" to "%s".',
        blockface_job_id,
        timestamp,
        config["output_type"].lower(),
        config["output_path"],
    )
