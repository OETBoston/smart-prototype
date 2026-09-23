import pandas as pd
from curb_utils.db_utils import SmartCurbDB
from curb_utils.logging import get_logger

logger = get_logger(__name__)


def export_to_db(
    db_name: str, data_dict: dict[str, pd.DataFrame], api_db_schema: str
) -> None:
    """
    Exports processed DataFrames to the database.
    """
    # SmartCurbDB commits on successful context exit and rolls back on error.
    # All related tables must share that transaction.
    with SmartCurbDB(dbname=db_name, schema=api_db_schema) as db:
        # Replaced zones may retain some policy IDs. Remove old links before
        # reinserting their complete replacement set.
        ordered_tables = sorted(
            data_dict.items(), key=lambda item: item[0] != "curb_zone_policies_delete"
        )
        for table_name, table_data in ordered_tables:
            logger.info(f"Updating {table_name} to database...")
            df = table_data["table"]
            keys = table_data["keys"]
            if not isinstance(df, pd.DataFrame):
                raise TypeError(f"Expected DataFrame for {table_name}, got {type(df)}")
            if df.empty:
                continue
            if table_name == "curb_zone_policies_delete":
                db.delete("curb_zone_policies", df, keys)
            elif table_name == "curb_zone_policies":
                db.append_data("curb_zone_policies", df)
            else:
                db.update_or_append(table_name, df, keys)
    logger.info("API export transaction committed successfully.")
