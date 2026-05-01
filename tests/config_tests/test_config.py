import os
from pathlib import Path

import pytest

from smart_prototype.config import StepConfig

# may be of use later
TEST_CONFIGS_DIR = Path(__file__).parent / "test_configs"


def test_step_config_valid_path(tmp_path) -> None:
    """Load a StepConfig without Error"""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("dummy config content")
    cfg_contents = {
        "step_name": "blockface-creator",
        "config_path": str(yaml_file),
        "run": True,
    }
    try:
        StepConfig(**cfg_contents)
    except Exception as e:
        pytest.fail(f"StepConfig validation failed with error: {e}")

    assert os.path.exists(yaml_file)


def test_step_config_invalid_path() -> None:
    """Load a StepConfig with an invalid path and expect a ValueError"""
    cfg_contents = {
        "step_name": "blockface-creator",
        "config_path": "/non/existent/path/config.yaml",
        "run": True,
    }
    with pytest.raises(
        ValueError, match="Path /non/existent/path/config.yaml does not exist."
    ):
        StepConfig(**cfg_contents)
