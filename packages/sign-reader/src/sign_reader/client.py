"""Client utilities for initializing and configuring Gemini API."""

import sys
from pathlib import Path

from google import genai


def _create_client(api_key: str) -> genai.Client:
    """Create and return a Gemini API client.

    Args:
        api_key (str): The Gemini API key.

    Returns:
        genai.Client: Configured Gemini API client instance.
    """
    return genai.Client(api_key=api_key)


def init_client(api_key: str, use_cache: bool = False) -> genai.Client:
    """Initialize Gemini client, optionally caching if Streamlit context."""
    if use_cache:
        # Streamlit app currently disabled
        # import streamlit as st  # lazy import so main.py never loads Streamlit

        # @st.cache_resource
        # def _cached_client(api_key: str) -> genai.Client:
        #     return _create_client(api_key)

        # return _cached_client(api_key)

        ### WARNING - cached mode currently not available ###
        raise RuntimeError("Cached client mode not currently available")

        return _create_client(api_key)
    else:
        return _create_client(api_key)


def read_instruction(file_path: str) -> str:
    """Read initial instruction/prompt for Gemini model."""
    path = Path(file_path)
    if not path.exists():
        print(f"❌ Instruction file not found: {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        instruction = f.read().strip()

    return instruction
