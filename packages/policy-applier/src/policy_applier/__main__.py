"""
Entry point for running policy-applier as a module.
"""

from pathlib import Path

from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import set_log_context

from policy_applier import PolicyApplierConfig, policy_applier

set_log_context("policy-applier")
local_path = Path(__file__).resolve().parent
config_file = local_path / "config.yaml"
config = PolicyApplierConfig(**load_from_yaml(config_file))

policy_applier(config)
