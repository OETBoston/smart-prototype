"""Environment variable management for the Sign Reader."""

import os

from dotenv import load_dotenv

load_dotenv()


def get_google_cloud_token_path_and_prefix() -> tuple[str, str]:
    token_path = os.getenv("GCS_TOKEN_PATH")
    prefix = os.getenv("GCS_PREFIX")
    if not all([token_path, prefix]):
        raise ValueError("Missing GCS_TOKEN_PATH or GCS_PREFIX in .env file")
    return token_path, prefix
