from pydantic import BaseModel


class PolicyApplierConfig(BaseModel):
    """Configuration for the policy applier step"""

    # Postgres DB export settings
    db_name: str
    db_schema: str

    # Input data settings
    curb_segmenter_job_id: str

    # Process parameters
    write_to_csv: bool = False
