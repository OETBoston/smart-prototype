"""
Entry point for running blockface-creator as a module.
"""

from pathlib import Path

from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import get_logger, set_log_context

from blockface_creator import BlockfaceCreatorConfig, blockface_creator

logger = get_logger(__name__)
set_log_context("blockface-creator")
local_path = Path(__file__).resolve().parent
config_file = local_path / "config.yaml"
config = BlockfaceCreatorConfig(**load_from_yaml(config_file))

blockface_creator(config)
