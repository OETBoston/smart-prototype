import os
from pathlib import Path

import pytest
from curb_utils.io_tools import load_from_yaml
from pydantic import ValidationError

from smart_prototype.config import Config, StepConfig

# may be of use later
TEST_CONFIGS_DIR = Path(__file__).parent / "configs"


def test_step_config_valid_path(tmp_path) -> None:
    """Load a StepConfig without Error"""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("dummy config content")
    config_contents = {
        "path": str(yaml_file),
        "run": True,
    }
    try:
        StepConfig(**config_contents)
    except Exception as e:
        pytest.fail(f"StepConfig validation failed with error: {e}")

    assert os.path.exists(yaml_file)


def test_step_config_invalid_path() -> None:
    """Load a StepConfig with an invalid path and expect a ValueError"""
    config_contents = {
        "path": "/non/existent/path/config.yaml",
        "run": True,
    }
    with pytest.raises(
        ValueError, match="Path /non/existent/path/config.yaml does not exist."
    ):
        StepConfig(**config_contents)


def test_global_config_valid() -> None:
    """Test loading a valid Config"""
    config_file = TEST_CONFIGS_DIR / "good_config.yaml"
    config_contents = load_from_yaml(config_file)
    try:
        Config(**config_contents)
    except Exception as e:
        pytest.fail(f"Config validation failed with error: {e}")


def test_global_config_missing_required_step() -> None:
    """Test loading a Config missing a required step and expect a ValidationError"""
    config_file = TEST_CONFIGS_DIR / "good_config.yaml"
    config_contents = load_from_yaml(config_file)
    del config_contents["steps"]["curb_segmenter"]  # Remove a required step
    with pytest.raises(ValidationError):
        Config(**config_contents)


def test_global_config_extra_step() -> None:
    """Test loading a Config missing a required step and expect a ValidationError"""
    config_file = TEST_CONFIGS_DIR / "good_config.yaml"
    config_contents = load_from_yaml(config_file)
    # Add an extra step
    config_contents["steps"]["extra_step"] = {
        "path": str(TEST_CONFIGS_DIR / "empty_config.yaml"),
        "run": True,
    }
    with pytest.raises(ValidationError):
        Config(**config_contents)
