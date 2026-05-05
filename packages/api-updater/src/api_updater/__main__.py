"""
Entry point for running api-updater as a module.
"""

from pathlib import Path

from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import set_log_context

from api_updater import ApiUpdaterConfig, api_updater

set_log_context("api-updater")
local_path = Path(__file__).resolve().parent
config_file = local_path / "config.yaml"
config = ApiUpdaterConfig(**load_from_yaml(config_file))

api_updater(config)
