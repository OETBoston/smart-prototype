from typing import Literal
from uuid import UUID

from curb_utils.ai_client import GeminiOptions
from pydantic import BaseModel, ConfigDict, Field


class SignAssetsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    re_process: bool = Field(False)


class SignReaderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Source job ids
    class Jobs(BaseModel):
        parking_sign: UUID | Literal["auto"] | None = Field(None)

    source_jobs: Jobs

    debug_mode: bool = Field(False)
    max_images: int | None = Field(None)
    db_name: str
    db_schema: str
    job_name: str | None = Field(None)
    job_description: str | None = Field(None)
    gemini_concurrent_limit: int = Field(1, ge=1)
    batch_size: int = Field(50, ge=1)
    gemini_preprocess_settings: GeminiOptions
    gemini_settings: GeminiOptions
    max_retries: int = Field(3, ge=0)
    sign_assets: SignAssetsConfig
