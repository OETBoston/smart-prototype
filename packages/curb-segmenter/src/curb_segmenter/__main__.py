"""
Entry point for running curb-segmenter as a module.
"""

from pathlib import Path

from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import set_log_context

from curb_segmenter import curb_segmenter
from curb_segmenter.config import CurbSegmenterConfig

set_log_context("curb-segmenter")
local_path = Path(__file__).resolve().parent
config_file = local_path / "config.yaml"
config = CurbSegmenterConfig(**load_from_yaml(config_file))

curb_segmenter(config)
