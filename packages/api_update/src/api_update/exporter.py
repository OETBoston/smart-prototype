import logging
from pathlib import Path

import pandas as pd
from curb_utils.db_utils import SmartCurbDB

logger = logging.getLogger(__name__)


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

    for filename, df in processed_dict.items():
        if not isinstance(df, pd.DataFrame):
            logger.warning(f"Skipping {filename}: Expected DataFrame, got {type(df)}.")
            continue

        if df.empty:
            logger.info(f"Skipping {filename}: DataFrame is empty.")
            continue

        file_dest = output_path / f"{filename}.csv"

        try:
            df.to_csv(file_dest, index=False)
            logger.info(f"Successfully exported: {file_dest}")
        except Exception as e:
            logger.error(f"Failed to export {filename}: {e}")


def export_to_db(data_dict: dict[str, pd.DataFrame],
                 api_db_schema: str = "public_cds") -> None:
    """
    Exports processed DataFrames to the database.
    """
    for table_name, table in data_dict.items():
        logger.info(f"Exporting {table_name} to database...")
        with SmartCurbDB(dbname="cds", schema=api_db_schema) as db:
            db.append_data(table_name, table)
        logger.info(f"Successfully exported: {table_name}.")
