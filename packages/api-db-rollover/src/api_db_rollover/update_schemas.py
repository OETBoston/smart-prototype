"""Module for updating the public_cds schema and initializing
public_cds_next for the next update."""
from sqlalchemy import text
from curb_utils.db_utils import SmartCurbDB
from curb_utils.logging import get_logger


def update_public_cds(
        dbname: str,
        update_sql: str,
        init_sql: str
) -> None:
    """Rolls over data from public_cds to public_cds_previous and updates
    the public_cds schema. Initializes public_cds_next for the next update."""
    logger = get_logger(__name__)
    with SmartCurbDB(dbname=dbname, schema="public") as db:
        if db.connection is None:
            raise RuntimeError("Error accessing the database")
        db.connection.execute(text(update_sql))
        logger.info("Public CDS schema updated successfully.")
        db.connection.execute(text(init_sql))
        logger.info("public_cds_next schema initialized successfully.")
