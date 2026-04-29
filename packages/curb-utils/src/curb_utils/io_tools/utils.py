import json
import os
from pathlib import Path

import yaml


def load_from_yaml(config_file_path: str | os.PathLike) -> dict:
    """Loads the provided yaml file, raising a useful error if not found.

    Args:
        config_file_path (str | os.PathLike): Path to the config file.

    Returns:
        dict: Dictionary of the data loaded from the yaml file
    """
    try:
        with open(config_file_path, "r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Config file not found: {config_file_path}") from e
    except Exception as e:
        raise RuntimeError(f"Error loading config file {config_file_path}") from e


def load_from_txt(path: Path | str) -> str:
    """Load a text file. Useful for reading in prompts and instructions
    Raises FileNotFound if path does not exist."""

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot find path to text file {path}")
    with open(path, "r") as f:
        text = f.read().strip()
    return text


def load_from_json(json_file_path: str | os.PathLike) -> dict:
    """Loads the provided JSON file, raising a useful error if not found.

    Args:
        json_file_path (str | os.PathLike): Path to the JSON file.

    Returns:
        dict: Dictionary of the data loaded from the JSON file
    """
    try:
        with open(json_file_path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"JSON file not found: {json_file_path}") from e
    except Exception as e:
        raise RuntimeError(f"Error loading JSON file {json_file_path}") from e
