import importlib

from curb_utils.logging import get_logger, set_log_context
from pydantic import BaseModel

from smart_prototype.config import Config, StepConfig

logger = get_logger(__name__)


def run_steps(config: Config, step_configs: dict[str, type[BaseModel]]) -> None:
    for step_name in Config.Steps.model_fields:
        step_config: StepConfig = getattr(config.steps, step_name)
        if step_config.run:
            logger.info(f"Running step: {step_name}")
            set_log_context(step_name)

            # Import and run
            module = importlib.import_module(step_name)
            core_function = getattr(module, step_name)
            core_function(step_configs[step_name])
