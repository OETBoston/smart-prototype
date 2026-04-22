import os

from google import genai


def init_gemini_client(api_key: str | None = None) -> genai.Client:
    """
    Initialize a Gemini Client. If no API key is provided,
    will attempt to load from the environment variable "GEMINI_API_KEY".

    Typically, should be passed to callables querying Gemini as the first argument
    to allow reuse of client across multiple API calls.

    Usage:
        with init_gemini_client(MY_KEY) as client:
            response = func(client, ...)

    Args:
        api_key (str, optional): Valid Google Gemini API Key.

    Returns:
        Gemini API Cient

    Raises:
        RuntimeError: if no API key is provided via args or environment.
    """
    if not api_key:
        try:
            os.environ["GEMINI_API_KEY"]
        except KeyError as exc:
            raise RuntimeError(
                "Must suply a valid Gemini API key either as an arg "
                "or have set GEMINI_API_KEY as an environment variable."
            ) from exc
    client = genai.Client(api_key=api_key)
    return client
