import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from smart_prototype.config import Config, StepConfig

# may be of use later
TEST_CONFIGS_DIR = Path(__file__).parent / "test_configs"


@pytest.fixture
def global_config_contents_valid(tmp_path) -> dict:
    """Helper function to create a valid Config instance for testing"""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("dummy config content")
    cfg_contents = {
        "geometry_creation_cfg": {
            "step_name": "blockface-creator",
            "config_path": str(yaml_file),
            "run": True,
        },
        "curb_segmenter_cfg": {
            "step_name": "curb-segmenter",
            "config_path": str(yaml_file),
            "run": True,
        },
        "sign_reader_cfg": {
            "step_name": "sign-reader",
            "config_path": str(yaml_file),
            "run": True,
        },
        "policy_applier_cfg": {
            "step_name": "policy-applier",
            "config_path": str(yaml_file),
            "run": True,
        },
    }
    return cfg_contents


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


def test_step_config_invalid_step_name(tmp_path) -> None:
    """Load a StepConfig with an invalid step name and expect a ValueError"""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("dummy config content")
    cfg_contents = {
        "step_name": "invalid-step-name",
        "config_path": str(yaml_file),
        "run": True,
    }
    with pytest.raises(ValidationError):
        StepConfig(**cfg_contents)


def test_global_config_valid(global_config_contents_valid) -> None:
    """Test loading a valid Config"""
    cfg_contents = global_config_contents_valid
    try:
        Config(**cfg_contents)
    except Exception as e:
        pytest.fail(f"Config validation failed with error: {e}")


def test_global_config_missing_required_step(global_config_contents_valid) -> None:
    """Test loading a Config missing a required step and expect a ValidationError"""
    cfg_contents = global_config_contents_valid
    del cfg_contents["curb_segmenter_cfg"]  # Remove a required step
    with pytest.raises(ValidationError):
        Config(**cfg_contents)
