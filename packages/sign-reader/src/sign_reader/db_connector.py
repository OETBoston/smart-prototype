import uuid

import pandas as pd
from curb_utils.db_utils import SmartCurbDB

DB_SCHEMA = "staging_demo"


def get_image_list(
    re_process: bool = False, asset_job_id: uuid.UUID | None = None
) -> list[tuple[str, uuid.UUID]]:
    """
    Fetches image URIs and their corresponding sign IDs.

    Args:
        re_process: If True, includes images that already have records
                    in the sign_policies table. Defaults to False.
        asset_job_id: If provided, filters images by the specified sign asset job ID.

    Returns:
        A list of tuples where each tuple contains:
            - str: The image URI (e.g., Google Cloud Storage path).
            - uuid.UUID: The unique identifier for the sign (sign_id).
    """
    filter = None
    if asset_job_id:
        filter = f"job_id = '{asset_job_id}'"

    with SmartCurbDB(dbname="cds", schema=DB_SCHEMA) as db:
        df_images = db.get_data("images", columns=["uri", "sign_id"], filter=filter)

        if not re_process:
            df_sign_policies = db.get_data("sign_policies", columns=["sign_id"])
            processed_ids = df_sign_policies["sign_id"].unique()
            df_images = df_images[~df_images["sign_id"].isin(processed_ids)]

    if df_images.empty:
        return []

    return list(zip(df_images["uri"], df_images["sign_id"], strict=True))


def append_sign_policies(records: list[dict], job_id: uuid.UUID) -> None:
    """Appends sign policy records to the database."""
    records_policies = pd.DataFrame(records)
    records_policies["job_id"] = str(job_id)
    with SmartCurbDB(dbname="cds", schema=DB_SCHEMA) as db:
        db.append_data("sign_policies", records_policies)
