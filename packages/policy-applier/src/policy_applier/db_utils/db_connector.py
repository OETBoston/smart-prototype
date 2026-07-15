import getpass
import uuid
from datetime import datetime

import pandas as pd
from curb_utils.db_utils import SmartCurbDB
from geopandas import GeoDataFrame
from pandas import DataFrame


def append_policy_handling_jobs(
    db_name: str,
    db_schema: str,
    job_name: str | None = None,
    job_description: str | None = None,
) -> str:
    """Registers a new job in the database with contextual naming."""
    user = getpass.getuser()
    job_id = str(uuid.uuid4())
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    job_name = job_name or f"{timestamp} Policy Applier ({user})"
    job_description = (
        job_description
        or f"Policy Applier session initiated by {user} at {now.isoformat()}"
    )

    job_data = {
        "job_id": [job_id],
        "job_name": [job_name],
        "job_description": [job_description],
    }

    with SmartCurbDB(dbname=db_name, schema=db_schema) as db:
        db.append_data("policy_handling_jobs", pd.DataFrame(job_data))

    return job_id


def append_curb_segment_policies(
    records_policies: pd.DataFrame,
    job_id: uuid.UUID | str,
    db_name: str,
    db_schema: str,
) -> None:
    """Appends curb segment policy records to the database."""
    records_policies["job_id"] = str(job_id)
    with SmartCurbDB(dbname=db_name, schema=db_schema) as db:
        db.append_data("curb_segment_policies", records_policies)


def read_policy_applier_tables(
    curb_segment_job_id: uuid.UUID | None, db_name: str, db_schema: str
) -> tuple[
    GeoDataFrame,
    DataFrame,
    GeoDataFrame,
    DataFrame,
    DataFrame,
    DataFrame,
]:
    """Fetches necessary tables for policy application."""
    filter = None
    if curb_segment_job_id:
        filter = f"job_id = '{curb_segment_job_id}'"

    with SmartCurbDB(dbname=db_name, schema=db_schema) as db:
        df_segments = db.get_data(
            "curb_segments",
            geom_col="geography",
            filter=filter,
            columns=[
                "segment_id",
                "blockface_id",
                "geography",
                "is_left_side_oneway",
                "segment_seq",
                "upstream_loc_list",
                "downstream_loc_list",
            ],
        )

        df_signs = db.get_data("signs", columns=["sign_id", "sign_location_id"])

        df_asset_locations = db.get_data("asset_locations", geom_col="location")

        df_sign_policies = db.get_data(
            "sign_policies",
            columns=["sign_policy_id", "sign_id", "policy_json", "policy_arrow"],
        )

        df_meter_policies = db.get_data(
            "meter_policies",
            columns=[
                "meter_policy_id",
                "policy_json",
                "start_asset_location_id",
                "end_asset_location_id",
            ],
        )

        df_nonsign_features = db.get_data(
            "nonsign_features", columns=["feature_location", "feature_type"]
        )

    return (
        df_segments,
        df_signs,
        df_asset_locations,
        df_sign_policies,
        df_meter_policies,
        df_nonsign_features,
    )
