import logging

import pandas as pd
from smart_curb_db import SmartCurbDB

logger = logging.getLogger(__name__)


def read_db_tables(
    dbname: str, schema: str, tables: dict[str, str | None]
) -> dict[str, pd.DataFrame]:
    """
    Acquires data from specified database, schema, and tables.
    Args:
        dbname (str): Name of the database to connect to.
        schema (str): Name of the schema to read from.
        tables (dict[str, str | None]): Dictionary of table names and optional filters.
    Returns:
        dict: Dictionary of DataFrames from the specified tables.
    """
    logger.info(f"Connecting to {dbname}.{schema}...")
    data = {}
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        for table, filter in tables.items():
            try:
                data[table] = db.get_data(table, filter=filter)
            except Exception as e:
                logger.error(f"Error reading table {table}: {e}")
                raise

    return data
