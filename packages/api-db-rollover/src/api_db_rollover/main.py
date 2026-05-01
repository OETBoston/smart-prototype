from dotenv import load_dotenv
from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import get_logger
import update_schemas

# Session settings
load_dotenv()
logger = get_logger(__name__)
logger.info("Running API DB Rollover Process...")


def main() -> None:
    """Main function to execute the database rollover process."""
    config = load_from_yaml(
        "packages/api-db-rollover/src/api_db_rollover/config.yaml"
    )
    update_sql = update_schemas.read_sql_file(
        "packages/api-db-rollover/src/api_db_rollover/sql/update_public_cds.sql"
    )
    init_sql = update_schemas.read_sql_file(
        "packages/api-db-rollover/src/api_db_rollover/sql/init_db.sql"
    )
    logger.info("Config and SQL files loaded successfully.")
    update_schemas.update_public_cds(
        dbname=config["dbname"],
        schema=config["schema"],
        update_sql=update_sql,
        init_sql=init_sql
    )


if __name__ == "__main__":
    main()
