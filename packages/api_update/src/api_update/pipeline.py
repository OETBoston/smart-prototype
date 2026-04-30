import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add repo root to sys.path so we can import from 'packages'
repo_root = Path(__file__).resolve().parents[4]  # …/smart-prototype
sys.path.append(str(repo_root))

# Internal imports
from exporter import export_to_csv, export_to_db
from extractor import read_db_tables
from transformer import transform_policy_updates

from curb_utils.io_tools import load_from_yaml

# Load environment variables
load_dotenv()

# Logging Configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants/Config
OUTPUT_DIR = Path("data")


def run_api_update(
        curb_segments_job: str | None = None,
        policy_handling_job: str | None = None,
        staging_db_schema: str = "staging",
        api_db_schema: str = "public_cds",
) -> None:
    """
    Orchestrates curb policy update processing and CSV export.
    Args:
        curb_segments_job (str | None, optional): The curb segments job_id to use.
        policy_handling_job (str | None, optional): The policy handling job_id to use.
        staging_db_schema (str): database schema for staging inputs
        api_db_schema (str): database schema for API inputs and outputs
    """
    logger.info("Starting update process.")

    # 1. Acquire Data
    staging_data_dict = read_db_tables(
        dbname="cds",
        schema=staging_db_schema,
        tables={
            "curb_segments": None if curb_segments_job is None else f"job_id = '{curb_segments_job}'",
            "curb_segment_policies": None if policy_handling_job is None else f"job_id = '{policy_handling_job}'",
        },
    )

    if not staging_data_dict:
        logger.error("Error reading staging data. Exiting.")
        raise SystemExit(0)

    api_data_dict = read_db_tables(
        dbname="cds",
        schema=api_db_schema,
        tables={
            "curb_zones": f"end_date IS NULL",
            "curb_policies": None,
            "curb_zone_policies": None,
            "curb_policy_rules": None,
            "curb_policy_time_spans": None,
            "curb_policy_rates": None
        },
    )

    if not api_data_dict:
        logger.error("Error reading API data. Exiting.")
        raise SystemExit(0)

    # 2. Process Data
    processed = transform_policy_updates(staging_data_dict, api_data_dict)

    # 3. Export Data
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export_to_csv(processed, out_dir=OUTPUT_DIR)
    export_to_db(processed, api_db_schema=api_db_schema)
    logger.info("Update process completed successfully.")


def main(
        curb_segments_job: str | None = None,
        policy_handling_job: str | None = None,
        staging_db_schema: str = "staging",
        api_db_schema: str = "public_cds",
) -> None:
    try:
        run_api_update(curb_segments_job, policy_handling_job, staging_db_schema, api_db_schema)
    except Exception as e:
        logger.error(f"Failed to run update: {e}")
        exit(1)


if __name__ == "__main__":
    # Define external files
    local_path = Path(__file__).resolve().parent
    config_file = local_path / "config.yaml"

    # Load external data
    config = load_from_yaml(config_file)

    staging_db_schema = config["staging_db"]["schema"]
    api_db_schema = config["api_db"]["schema"]

    curb_segments_job = config["staging_db"]["curb_segments_job"]
    policy_handling_job = config["staging_db"]["policy_handling_job"]

    main(
        curb_segments_job=curb_segments_job,
        policy_handling_job=policy_handling_job,
        staging_db_schema=staging_db_schema,
        api_db_schema=api_db_schema
    )
