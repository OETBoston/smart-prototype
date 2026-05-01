from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator

AllSteps = Literal[
    "blockface-creator", "curb-segmenter", "sign-reader", "policy-applier"
]


def validate_path(path: str) -> str:
    if not Path(path).exists():
        raise ValueError(f"Path {path} does not exist.")
    return path


class StepConfig(BaseModel):
    """Configure whether a step should be run and where its config file is located."""

    step_name: AllSteps
    config_path: Annotated[str, BeforeValidator(validate_path)]
    run: bool


class Config(BaseModel):
    """Overall configureation for the pipeline"""

    geometry_creation_cfg: StepConfig
    curb_segmenter_cfg: StepConfig
    sign_reader_cfg: StepConfig
    policy_applier_cfg: StepConfig
