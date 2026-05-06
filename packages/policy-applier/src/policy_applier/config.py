from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PolicyApplierConfig(BaseModel):
    """Configuration for the policy applier step"""

    # Postgres DB export settings
    db_name: str
    db_schema: str
    job_name: str
    job_description: str

    # Source job ids
    class Jobs(BaseModel):
        curb_segmenter: UUID | Literal["auto"] | None = Field(None)

    source_jobs: Jobs

    # Process parameters
    default_parking_anytime: bool
    write_to_csv: bool = False
    csv_file_path: str = "curb_policy_output.csv"
