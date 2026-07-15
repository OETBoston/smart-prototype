# Tools for working with jobs tables
import getpass
import uuid
from typing import Any

import pandas as pd

from curb_utils.db_utils import SmartCurbDB


def append_job(
    db_name: str,
    db_schema: str,
    db_table: str,
    job_name: str | None = None,
    job_desc: str | None = None,
    **kwargs: Any,
) -> uuid.UUID:
    """Registers a job in the database and returns the job ID.

    Args:
        db_name (str): Name of the database to update
        db_schema (str): Schema in the database to update
        db_table (str): Name of the jobs table to update
        job_name (str | None, optional): User provided job name.
            (Defaults to "Unnamed job.")
        job_desc (str | None, optional): User provided job description.
            (Defaults to "No description provided.")
        **kwargs: Arbitrary keyword arguments. Must be compatible with database schema.

    Returns:
        uuid.UUID: Job ID entered into the database.
    """
    job_id = uuid.uuid4()
    user = getpass.getuser()

    # Determine context dynamically
    job_data = {
        "job_id": [job_id],
        "job_name": [(job_name or "Unnamed job.") + f" ({user})"],
        "job_description": [job_desc or "No description provided."],
        **kwargs,
    }

    with SmartCurbDB(dbname=db_name, schema=db_schema) as db:
        db.append_data(db_table, pd.DataFrame(job_data))

    return job_id
