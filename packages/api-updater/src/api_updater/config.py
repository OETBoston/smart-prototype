from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiUpdaterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    db_name: str
    staging_db_schema: str
    api_db_schema: str

    class Jobs(BaseModel):
        curb_segmenter: UUID | None = Field(None)
        policy_handler: UUID | None = Field(None)

    source_jobs: Jobs
