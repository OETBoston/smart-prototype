import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add repo root to sys.path so we can import from 'packages'
repo_root = Path(__file__).resolve().parents[4]  # …/smart-prototype
sys.path.append(str(repo_root))

# Internal imports
from packages.api_update.src.api_update.exporter import export_to_csv, export_to_db
from packages.api_update.src.api_update.extractor import read_db_tables
from packages.api_update.src.api_update.transformer import transform_policy_updates

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
    job_id: str | None = None,
    staging_db_schema: str = "staging",
    api_db_schema: str = "public_cds",
) -> None:
    """
    Orchestrates curb policy update processing and CSV export.
    Args:
        job_id (str | None, optional): The policy handling job_id to use.
        schema (str): database schema for inputs and outputs
    """
    logger.info("Starting update process.")

    # 1. Acquire Data
    staging_data_dict = read_db_tables(
        dbname="cds",
        schema=staging_db_schema,
        tables={
            "curb_segments": None,
            "curb_segment_policies": None if job_id is None else f"job_id = '{job_id}'",
        },
    )

    if not staging_data_dict:
        logger.error("Error reading staging data. Exiting.")
        raise SystemExit(0)

    api_data_dict = read_db_tables(
        dbname="cds",
        schema=api_db_schema,
        tables={
            "curb_zones": None,
            "curb_policies": None,
            "curb_zone_policies": None,
            "curb_policy_rules": None,
            "curb_policy_time_spans": None,
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
    export_to_db(processed)
    logger.info("Update process completed successfully.")


def main(
    job_id: str | None = None,
    staging_db_schema: str = "staging",
    api_db_schema: str = "public_cds",
) -> None:
    try:
        run_api_update(job_id, staging_db_schema, api_db_schema)
    except Exception as e:
        logger.error(f"Failed to run update: {e}")
        exit(1)


if __name__ == "__main__":
    job_id = "fd510244-98fe-44a6-9134-1a2a19396573"
    staging_db_schema = "staging_next"
    api_db_schema = "public_cds_next"
    main(
        job_id=job_id, staging_db_schema=staging_db_schema, api_db_schema=api_db_schema
    )
