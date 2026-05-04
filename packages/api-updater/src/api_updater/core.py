from pathlib import Path

from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import get_logger, set_log_context
from dotenv import load_dotenv

from api_updater.config import ApiUpdaterConfig

# Internal imports
from api_updater.exporter import export_to_csv, export_to_db
from api_updater.extractor import read_db_tables
from api_updater.transformer import transform_policy_updates

# Load environment variables
load_dotenv()

# Logging Configuration
logger = get_logger(__name__)

# Constants/Config
OUTPUT_DIR = Path(__file__).parents[2] / "output"


def api_updater(config: ApiUpdaterConfig) -> None:
    """
    Runs curb policy update processing.
    Args:
        config (Config): config object as defined in config.py
    """
    logger.info("Starting update process.")

    # 1. Acquire Data
    jobs = config.source_jobs
    if isinstance(jobs.curb_segmenter, str) or isinstance(jobs.policy_handler, str):
        raise ValueError(
            'Job IDs must be specified as UUID or None. "'
            '"auto" is only allowed when running in automated pipeline mode.'
        )
    segments_filter = (
        None if not jobs.curb_segmenter else f"job_id = {jobs.curb_segmenter}"
    )
    policies_filter = (
        None if not jobs.policy_handler else f"job_id = {jobs.policy_handler}"
    )
    staging_data_dict = read_db_tables(
        dbname=config.db_name,
        schema=config.staging_db_schema,
        tables={
            "curb_segments": segments_filter,
            "curb_segment_policies": policies_filter,
        },
    )

    if not staging_data_dict:
        raise RuntimeError("Error reading staging data.")

    api_data_dict = read_db_tables(
        dbname=config.db_name,
        schema=config.api_db_schema,
        tables={
            "curb_zones": "end_date IS NULL",
            "curb_policies": None,
            "curb_zone_policies": None,
            "curb_policy_rules": None,
            "curb_policy_time_spans": None,
            "curb_policy_rates": None,
        },
    )

    if not api_data_dict:
        raise RuntimeError("Error reading API data.")

    # 2. Process Data
    processed = transform_policy_updates(staging_data_dict, api_data_dict)

    # 3. Export Data
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export_to_csv(processed, out_dir=OUTPUT_DIR)
    export_to_db(
        db_name=config.db_name, data_dict=processed, api_db_schema=config.api_db_schema
    )
    logger.info("Update process completed successfully.")


if __name__ == "__main__":
    set_log_context("api-updater")
    local_path = Path(__file__).resolve().parent
    config_file = local_path / "config.yaml"
    config = ApiUpdaterConfig(**load_from_yaml(config_file))

    api_updater(config)
