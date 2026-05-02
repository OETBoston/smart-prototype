import importlib

from pydantic import BaseModel

from smart_prototype.config import Config, StepConfig
from smart_prototype.logs import log_step


def run_steps(config: Config, step_configs: dict[str, type[BaseModel]]) -> None:
    for step_name in Config.Steps.model_fields:
        step_config: StepConfig = getattr(config.steps, step_name)
        if step_config.run:
            log_step(step_name)

            # Import and run
            module = importlib.import_module(step_name)
            core_function = getattr(module, step_name)
            core_function(step_configs[step_name])
