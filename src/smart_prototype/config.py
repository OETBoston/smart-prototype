from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator


def validate_path(path: str) -> str:
    if not Path(path).exists():
        raise ValueError(f"Path {path} does not exist.")
    return path


class StepConfig(BaseModel):
    """Configure whether a step should be run and where its config file is located."""

    path: Annotated[str, BeforeValidator(validate_path)]
    run: bool


class Config(BaseModel):
    """Overall configuration for the pipeline"""

    class Steps(BaseModel):
        model_config = {"extra": "forbid"}
        geometry_creation: StepConfig
        curb_segmenter: StepConfig
        sign_reader: StepConfig
        policy_applier: StepConfig

    steps: Steps
