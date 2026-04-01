import logging
from pathlib import Path

import pandas as pd

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
