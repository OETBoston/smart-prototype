from pydantic import BaseModel


class PolicyApplierConfig(BaseModel):
    """Configuration for the policy applier step"""

    # Postgres DB export settings
    db_name: str
    db_schema: str
    job_name: str
    job_description: str

    # Input data settings
    curb_segmenter_job_id: str

    # Process parameters
    default_parking_anytime: bool
    write_to_csv: bool = False
    csv_file_path: str = "curb_policy_output.csv"
