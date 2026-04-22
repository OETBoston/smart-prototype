"""Environment variable management for the Sign Reader."""

import os

from dotenv import load_dotenv

load_dotenv()


def get_api_key() -> str:
    """Return GEMINI_API_KEY from environment."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("Missing GEMINI_API_KEY environment variable.")
    return key


def get_google_cloud_token_path_and_prefix() -> tuple[str, str]:
    token_path = os.getenv("GCS_TOKEN_PATH")
    prefix = os.getenv("GCS_PREFIX")
    if not all([token_path, prefix]):
        raise ValueError("Missing GCS_TOKEN_PATH or GCS_PREFIX in .env file")
    return token_path, prefix
