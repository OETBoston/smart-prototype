from pathlib import Path

from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import get_logger

from smart_prototype.config import Config
from smart_prototype.load_step_configs import load_step_configs
from smart_prototype.logs import log_done, log_start
from smart_prototype.run_steps import run_steps

logger = get_logger(__name__)


def main(config: Config) -> None:
    """This module runs the smart-curb process from end to end. It reads
    configuration options from config.yaml, which itself references
    configuration files for each step"""

    log_start(config)

    # Load steps first so any load errors happen early
    step_configs = load_step_configs(config)

    run_steps(config, step_configs)

    log_done()


if __name__ == "__main__":
    # Load the configuration file into Config model,
    # the pass it in to main
    base_path = Path(__file__).resolve().parent
    config_file = base_path / "config.yaml"
    config = Config(**load_from_yaml(config_file))
    main(config)
