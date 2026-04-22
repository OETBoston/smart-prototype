"""Environment variable management for the Sign Reader."""

import os

from dotenv import load_dotenv

load_dotenv()


def get_api_key() -> str:
    """Return GEMINI_API_KEY from environment."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("Missing GEMINI_API_KEY in .env file")
    return key


def get_gemini_config() -> tuple[str, str, str]:
    """Return (GEMINI_MODEL, GEMINI_API_KEY, GEMINI_THINKING_LEVEL) from environment."""
    model = os.getenv("GEMINI_MODEL")
    key = os.getenv("GEMINI_API_KEY")
    thinking_level = os.getenv("GEMINI_THINKING_LEVEL")

    missing = []
    if not model:
        missing.append("GEMINI_MODEL")
    if not key:
        missing.append("GEMINI_API_KEY")
    # Only require GEMINI_THINKING_LEVEL for gemini-3* models
    if model and model.startswith("gemini-3") and not thinking_level:
        missing.append("GEMINI_THINKING_LEVEL")

    if missing:
        raise ValueError(f"Missing {', '.join(missing)} in .env file")

    # For non-gemini-3* models, default thinking_level to "minimal" when unset
    if not thinking_level:
        thinking_level = "minimal"

    return model, key, thinking_level


def get_google_cloud_token_path_and_prefix() -> tuple[str, str]:
    token_path = os.getenv("GCS_TOKEN_PATH")
    prefix = os.getenv("GCS_PREFIX")
    if not all([token_path, prefix]):
        raise ValueError("Missing GCS_TOKEN_PATH or GCS_PREFIX in .env file")
    return token_path, prefix
