import uuid
from datetime import datetime

import pandas as pd
from curb_utils.db_utils import SmartCurbDB

DB_SCHEMA = "staging_next"


def append_sign_reader_jobs(user: str, is_batch: bool = True) -> uuid.UUID:
    """Registers a new job in the database with contextual naming."""
    job_id = uuid.uuid4()
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    # Determine context dynamically
    job_type = "Batch" if is_batch else "App (Streamlit)"

    job_data = {
        "job_id": [job_id],
        "job_name": [f"{timestamp} Sign Reader {job_type} ({user})"],
        "job_description": [
            f"{job_type} session initiated by {user} at {now.isoformat()}"
        ],
    }

    with SmartCurbDB(dbname="cds", schema=DB_SCHEMA) as db:
        db.append_data("sign_reader_jobs", pd.DataFrame(job_data))

    return job_id


def read_images(
    not_processed: bool = False, asset_job_id: uuid.UUID = None
) -> list[tuple[str, uuid.UUID]]:
    """
    Fetches image URIs and their corresponding sign IDs.

    Args:
        not_processed: If True, only returns images that do not have
                       associated records in the sign_policies table.
        asset_job_id: If provided, filters images by the specified asset job ID.

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

        if not_processed:
            df_sign_policies = db.get_data("sign_policies", columns=["sign_id"])
            processed_ids = df_sign_policies["sign_id"].unique()
            df_images = df_images[~df_images["sign_id"].isin(processed_ids)]

    if df_images.empty:
        return []

    return list(zip(df_images["uri"], df_images["sign_id"], strict=True))


def append_sign_policies(records: list[dict], job_id: uuid.UUID) -> None:
    """Appends sign policy records to the database."""
    records_policies = pd.DataFrame(records)
    records_policies["job_id"] = job_id
    with SmartCurbDB(dbname="cds", schema=DB_SCHEMA) as db:
        db.append_data("sign_policies", records_policies)
