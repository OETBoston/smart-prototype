import asyncio
from pathlib import Path

from curb_utils.ai_client.clients import call_gemini_client_aoi, init_gemini_client
from curb_utils.ai_client.config import GeminiOptions
from curb_utils.io_tools import load_from_txt
from google import genai

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
DEFAULT_OPTIONS = GeminiOptions(
    model="gemini-3.1-flash-lite-preview",
    temperature=0.1,
    thinking_level=None,
    include_thoughts=False,
)


def add_json_to_prompt(prompt: str, policy_json: str) -> str:
    """Adds Policy JSON (String) to the user prompt for processing"""
    return prompt + "\n" + policy_json


async def generate_description(
    client: genai.Client,
    sem: asyncio.Semaphore,
    prompt: str = default_prompt,
    system_instruction=default_instruction,
    model_opts: GeminiOptions | None = None,
    api_key: str | None = None,
) -> str:
    """
    Generate a Policy Description using Google Gemini.
    Allowing default model configuration and prompting is recommended.

    Args:
        client (genai.Client): Gemini Client
        prompt (str): user prompt to guide description generation.
        config (GeminiModelConfig | None, optional):
            Config object containing options to pass to Gemini. Defaults to None.
        api_key (str | None, optional):
            Valid Gemini API Key. If not provided, will try to load from env.
            Defaults to None.

    Returns:
        str: Policy description string.
    """
    if not model_opts:
        # use the defaults
        model_opts = DEFAULT_OPTIONS

    async with sem:
        contents: genai.types.ContentListUnionDict = [
            genai.types.Content(
                parts=[
                    genai.types.Part.from_text(text=prompt),
                ]
            )
        ]

        response = await call_gemini_client_aoi(
            client=client,
            system_instruction=system_instruction,
            contents=contents,
            response_schema=None,
            response_mime_type="text/plain",
            model_opts=model_opts,
        )

        if not response.text:
            return "NO DESCRIPTION AVAILABLE"
        else:
            return response.text


async def run_examples(api_key) -> None:
    """Provides basic example for running the description"""
    from time import perf_counter

    def read_policy_example(path) -> str:
        import json

        with open(path) as f:
            policy = json.load(f)
        return json.dumps(policy)

    async def process_example(policy_file: Path) -> str:
        sem = asyncio.Semaphore(50)
        print(f"Processing {policy_file}...")
        policy_json = read_policy_example(policy_file)
        outfile = policy_file.with_suffix(".RESULT.txt")
        prompt = add_json_to_prompt(default_prompt, policy_json)
        description = await generate_description(
            client, sem, prompt, model_opts=None, api_key=api_key
        )
        with open(outfile, "w+") as f:
            f.write(description)
        return description

    examples_dir = Path(__file__).parent / "test_data"
    files_to_process = list(examples_dir.glob("*.json"))

    start = perf_counter()

    with init_gemini_client(api_key) as client:
        async with asyncio.TaskGroup() as tg:
            for f in files_to_process:
                tg.create_task(process_example(f))
    end = perf_counter()
    elapsed = round(end - start, 3)
    print(f"Processed {len(files_to_process)} files in {elapsed}s")


if __name__ == "__main__":
    import os

    api_key = os.environ["GEMINI_API_KEY"]
    asyncio.run(run_examples(api_key))
