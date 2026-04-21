import os

import yaml


def load_config(config_file_path: str | os.PathLike) -> dict:
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
