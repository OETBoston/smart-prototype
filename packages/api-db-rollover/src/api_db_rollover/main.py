""" 
Main module for the API DB Rollover process.
"""
from dotenv import load_dotenv
from curb_utils.io_tools import load_from_yaml, load_from_txt
from curb_utils.logging import get_logger
import update_schemas


def main() -> None:
    """Main function to execute the database rollover process."""
    logger = get_logger(__name__)
    config = load_from_yaml(
        "packages/api-db-rollover/src/api_db_rollover/config.yaml"
    )
    update_sql = load_from_txt(
        "packages/api-db-rollover/src/api_db_rollover/sql/update_public_cds.sql"
    )
    init_sql = load_from_txt(
        "packages/api-db-rollover/src/api_db_rollover/sql/init_db.sql"
    )
    logger.info("Config and SQL files loaded successfully.")
    logger.info(
        "Starting database rollover process on database: %s",
        config["dbname"]
    )
    update_schemas.update_public_cds(
        dbname=config["dbname"],
        update_sql=update_sql,
        init_sql=init_sql
    )
    logger.info("Transaction completed successfully.")


if __name__ == "__main__":
    # Session settings
    load_dotenv()
    logger = get_logger(__name__)
    logger.info("Running API DB Rollover Process...")
    main()
