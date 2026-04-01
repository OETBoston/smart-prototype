import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from packages.api_update.src.api_update.exporter import export_to_csv

# Internal imports
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


def run_api_update(job_id: str | None = None) -> None:
    """
    Orchestrates curb policy update processing and CSV export.
    Args:
        job_id (str | None, optional): The policy handling job_id to use.
    """
    logger.info("Starting update process.")

    # 1. Acquire Data
    staging_data_dict = read_db_tables(
        dbname="cds",
        schema="staging",
        tables={
            "df_curb_segments": None,
            "df_curb_segment_policies": None
            if job_id is None
            else f"job_id = '{job_id}'",
        },
    )

    if not staging_data_dict:
        logger.error("Error reading staging data. Exiting.")
        raise SystemExit(0)

    # 2. Process Data
    processed = transform_policy_updates(staging_data_dict)

    # 3. Export Data
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export_to_csv(processed, out_dir=OUTPUT_DIR)
    logger.info("Update process completed successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process curb policy updates for a specific Job ID."
    )
    parser.add_argument("--job-id", type=str, help="The policy handling job_id.")
    args = parser.parse_args()

    try:
        run_api_update(job_id=args.job_id)
    except Exception as e:
        logger.error(f"Failed to run update: {e}")
        exit(1)


if __name__ == "__main__":
    main()
