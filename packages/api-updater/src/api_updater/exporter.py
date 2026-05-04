from pathlib import Path

import pandas as pd
from curb_utils.db_utils import SmartCurbDB
from curb_utils.logging import get_logger

logger = get_logger(__name__)


def export_to_csv(
    processed_dict: dict[str, pd.DataFrame], out_dir: str | Path = "data"
) -> None:
    """
    Exports processed DataFrames to CSV files in the specified directory.

    Args:
        processed_dict (dict): Dictionary of processed DataFrames.
        out_dir (str | Path): Output directory for CSV files.
    """
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for filename, table_data in processed_dict.items():
        df = table_data["table"]
        if not isinstance(df, pd.DataFrame):
            logger.warning(f"Skipping {filename}: Expected DataFrame, got {type(df)}.")
            continue

        if df.empty:
            logger.info(f"Skipping {filename}: DataFrame is empty.")
            continue

        file_dest = output_path / f"{filename}.csv"

        try:
            df.to_csv(file_dest, index=False)
            logger.info(f"Local export successful: {file_dest}")
        except Exception as e:
            logger.error(f"Failed to export {filename}: {e}")


def export_to_db(
    db_name: str, data_dict: dict[str, pd.DataFrame], api_db_schema: str
) -> None:
    """
    Exports processed DataFrames to the database.
    """
    for table_name, table_data in data_dict.items():
        logger.info(f"Updating {table_name} to database...")

        df = table_data["table"]
        keys = table_data["keys"]

        if not isinstance(df, pd.DataFrame):
            logger.warning(
                f"Skipping {table_name}: Expected DataFrame, got {type(df)}."
            )
            continue

        if df.empty:
            logger.info(f"Skipping {table_name}: DataFrame is empty.")
            continue

        with SmartCurbDB(dbname=db_name, schema=api_db_schema) as db:
            if table_name == "curb_zone_policies_delete":
                db.delete("curb_zone_policies", df, keys)
            elif table_name == "curb_zone_policies":
                db.append_data("curb_zone_policies", df)
            else:
                db.update_or_append(table_name, df, keys)
        logger.info(f"Database export successful: {table_name}.")
