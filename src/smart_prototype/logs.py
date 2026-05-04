from curb_utils.logging import get_logger, set_log_context

from smart_prototype.config import Config, StepConfig

logger = get_logger(__name__)


def log_start(config: Config) -> None:
    title = "Starting Pipeline"
    set_log_context("main")
    logger.info(f"\n\n{title:=^80}\n")

    for step_name in Config.Steps.model_fields:
        step_config: StepConfig = getattr(config.steps, step_name)
        logger.info(f"  Step: {step_name}")
        logger.info(f"    Enabled: {step_config.run}")
        if step_config.run:
            logger.info(f"    Config file: {step_config.path}")


def log_step(step_name) -> None:
    set_log_context(step_name)
    title = f"Running {step_name}"
    logger.info(f"\n\n{title:=^50}\n")


def log_done() -> None:
    title = "Pipeline Complete"
    logger.info(f"\n\n{title:=^80}\n")
