"""
Entry point for running api-updater as a module.
"""

import argparse
from pathlib import Path

from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import set_log_context

from api_updater import ApiUpdaterConfig, api_updater


def main(argv: list[str] | None = None) -> None:
    """Run with an optional config path, retaining the package default."""
    parser = argparse.ArgumentParser(description="Run api-updater")
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).resolve().parent / "config.yaml"
    )
    args = parser.parse_args(argv)
    set_log_context("api-updater")
    api_updater(ApiUpdaterConfig(**load_from_yaml(args.config)))


if __name__ == "__main__":
    main()
