import asyncio
from pathlib import Path

from curb_utils.ai_client.clients import (
    call_gemini_client_aio,
)
from curb_utils.ai_client.config import GeminiOptions
from curb_utils.io_tools import load_from_txt
from google import genai

# Instruction Paths
INSTRUCTIONS_DIRECTORY = Path(__file__).resolve().parent / "instructions"
INSTRUCTION_PATH = INSTRUCTIONS_DIRECTORY / "default_instructions_descriptions.txt"
PROMPT_PATH = INSTRUCTIONS_DIRECTORY / "default_prompt_descriptions.txt"

# Load prompts and system instruction defaults
system_instruction = load_from_txt(INSTRUCTION_PATH)
prompt = load_from_txt(PROMPT_PATH)


def is_missing_description(value: object) -> bool:
    """Recognize missing text and the placeholders emitted by older runs."""
    return not isinstance(value, str) or value.strip().casefold() in {
        "",
        "no description available",
        "no policy description provided",
        "no policy description provided.",
    }


def add_json_to_prompt(prompt: str, policy_json: str) -> str:
    """Adds Policy JSON (String) to the user prompt for processing"""
    return prompt + "\n" + policy_json


async def generate_description(
    client: genai.Client,
    sem: asyncio.Semaphore,
    prompt: str,
    system_instruction: str,
    model_opts: GeminiOptions | None = None,
) -> str:
    """
    Generate a Policy Description using Google Gemini.

    Args:
        client (genai.Client): Gemini Client
        sem (Semaphore): Semaphore to meter geimi calls
        prompt (str): user prompt to guide description generation.
        system_instruction (str): System instruciton for gemini prompt.
        model_opts (GeminiModelConfig):
            Config object containing options to pass to Gemini. Defaults to None.

    Returns:
        str: Policy description string.
    """
    if not model_opts:
        # use the defaults
        raise ValueError("Required model options not provided.")

    async with sem:
        contents: genai.types.ContentListUnionDict = [
            genai.types.Content(
                parts=[
                    genai.types.Part.from_text(text=prompt),
                ]
            )
        ]

        response = await call_gemini_client_aio(
            client=client,
            system_instruction=system_instruction,
            contents=contents,
            response_schema=None,
            response_mime_type="text/plain",
            model_opts=model_opts,
        )

        if is_missing_description(response.text):
            raise ValueError(
                "Gemini returned an empty or placeholder policy description"
            )
        return response.text.strip()
