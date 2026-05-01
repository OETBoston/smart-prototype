"""Module for updating the public_cds schema and initializing
public_cds_next for the next update."""
from sqlalchemy import text
from curb_utils.db_utils import SmartCurbDB
from curb_utils.logging import get_logger


def read_sql_file(sql_file_path: str) -> str:
    """Reads a SQL file and returns its content as a string."""
    try:
        with open(sql_file_path, 'r', encoding='utf-8') as file:
            sql_script = file.read()
    except Exception as e:
        raise RuntimeError(f"Error reading SQL file: {e}")
    return sql_script


def update_public_cds(
        dbname: str,
        schema: str,
        update_sql: str,
        init_sql: str
) -> None:
    """Rolls over data from public_cds to public_cds_previous and updates
    the public_cds schema. Initializes public_cds_next for the next update."""
    logger = get_logger(__name__)
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        assert db.connection is not None
        db.connection.execute(text(update_sql))
        logger.info("Public CDS schema updated successfully.")
        db.connection.execute(text(init_sql))
        logger.info("public_cds_next schema initialized successfully.")
        db.connection.commit()
        logger.info("Transaction committed successfully.")
