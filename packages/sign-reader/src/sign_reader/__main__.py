"""
Entry point for running sign-reader as a module.
"""

from pathlib import Path

from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import set_log_context

from sign_reader import SignReaderConfig, sign_reader

set_log_context("sign-reader")
local_path = Path(__file__).resolve().parent
config_file = local_path / "config.yaml"
config = SignReaderConfig(**load_from_yaml(config_file))

sign_reader(config)
