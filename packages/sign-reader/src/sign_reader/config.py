from uuid import UUID

from curb_utils.ai_client import GeminiOptions
from pydantic import BaseModel, ConfigDict, Field


class SignAssetsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID | None = Field(None)
    re_process: bool = Field(False)


class SignReaderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    debug_mode: bool = Field(False)
    max_images: int | None = Field(None)
    gemini_concurrent_limit: int = Field(1, ge=1)
    gemini_preprocess_settings: GeminiOptions
    gemini_settings: GeminiOptions
    max_retries: int = Field(3)
    db_name: str
    db_schema: str
    sign_assets: SignAssetsConfig
    sr_job_name: str | None = Field(None)
    sr_job_description: str | None = Field(None)
