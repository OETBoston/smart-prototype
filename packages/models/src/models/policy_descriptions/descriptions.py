from pathlib import Path

from google import genai

from models.clients import init_gemini_client
from models.config import GeminiOptions
from models.utils import load_from_txt

# Instruction Paths
INSTRUCTIONS_DIRECTORY = Path(__file__).parents[3] / "instructions"
DEFAULT_INSTRUCTION_PATH = (
    INSTRUCTIONS_DIRECTORY / "default_instructions_descriptions.txt"
)
DEFAULT_PROMPT_PATH = INSTRUCTIONS_DIRECTORY / "default_prompt_descriptions.txt"

# Load prompts and system instruction defaults
default_instruction = load_from_txt(DEFAULT_INSTRUCTION_PATH)
default_prompt = load_from_txt(DEFAULT_PROMPT_PATH)

# Default configuration options
DEFAULT_CONFIG = GeminiOptions(
    model="gemini-3.1-flash-lite-preview",
    temperature=0.1,
    thinking_level=None,
    include_thoughts=False,
)


def add_json_to_prompt(prompt: str, policy_json: str) -> str:
    """Adds Policy JSON (String) to the user prompt for processing"""
    return prompt + "\n" + policy_json


def generate_description(
    prompt: str = default_prompt,
    system_instruction=default_instruction,
    config: GeminiOptions | None = None,
    api_key: str | None = None,
) -> str:
    """
    Generate a Policy Description using Google Gemini.
    Allowing default model configuration and prompting is recommended.

    Args:
        prompt (str): user prompt to guide description generation.
        config (GeminiModelConfig | None, optional):
            Config object containing options to pass to Gemini. Defaults to None.
        api_key (str | None, optional):
            Valid Gemini API Key. If not provided, will try to load from env.
            Defaults to None.

    Returns:
        str: Policy description string.
    """
    if not config:
        # use the defaults
        config = DEFAULT_CONFIG

    config_gemini_typed = genai.types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="text/plain",
        temperature=config.temperature,
        thinking_config=genai.types.ThinkingConfig(
            include_thoughts=config.include_thoughts,
            thinking_level=config.thinking_level,  # type: ignore
        ),
    )

    with init_gemini_client(api_key) as client:
        contents = [genai.types.Part.from_text(text=prompt)]
        response = client.models.generate_content(
            model=config.model, contents=contents, config=config_gemini_typed
        )

        if not response.text:
            return "NO DESCRIPTION AVAILABLE"

    return response.text


def run_examples(api_key) -> None:
    """Provides basic example for running the description"""
    from time import perf_counter

    def read_policy_example(path) -> str:
        import json

        with open(path) as f:
            policy = json.load(f)
        return json.dumps(policy)

    examples_dir = Path(__file__).parent / "test_data"

    for p in examples_dir.glob("*.json"):
        print(f"Generating Description for {p}")
        start = perf_counter()
        outfile = p.with_suffix(".RESULT.txt")
        p_json = read_policy_example(p)
        prompt = add_json_to_prompt(default_prompt, p_json)
        description = generate_description(prompt, config=None, api_key=api_key)
        with open(outfile, "w+") as f:
            f.write(description)
        end = perf_counter()
        elapsed = round(end - start, 3)
        print(f"Processed file in {elapsed}s")
        print("=" * 20)


if __name__ == "__main__":
    import os

    api_key = os.environ["GEMINI_API_KEY"]
    run_examples(api_key)
