"""Gemini rapid pre-processor to evaluate sign image suitability"""

import asyncio
import time
from enum import Enum
from pathlib import Path
from typing import Annotated

from curb_utils.ai_client import GeminiOptions, call_gemini_client, init_gemini_client
from curb_utils.io_tools import load_from_txt
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field


class YesNo(str, Enum):
    yes = "yes"
    no = "no"


class Quantity(str, Enum):
    one = "one"
    two = "two"
    three = "three"
    four_plus = "four or more"


class YesNoResponse(BaseModel):
    value: YesNo


class QuantityResponse(BaseModel):
    value: Quantity


class PositiveIntResponse(BaseModel):
    value: Annotated[int, Field(ge=1)]


async def pre_test_image(
    client: genai.Client,
    system_instruction: str,
    image_bytes: bytes,
    model_opts: GeminiOptions | None = None,
) -> None:
    prompts = (
        (
            "Answer with yes or no: Does this image contain one or more signs?",
            YesNoResponse,
        ),
        (
            "Answer with yes or no: Is the image high enough quality to accurately "
            + "read ALL information on the sign or signs? Answer no if the image is "
            + "difficult to read becuase it is low-resolution, blurry, or because "
            + "signs are obscured.",
            YesNoResponse,
            # None,
        ),
        ("How many complete signs are present in the image?", PositiveIntResponse),
        # ("How many complete signs are present in the image?", QuantityResponse),
        (
            "Does at least one sign contain information about parking, "
            + "loading, stopping, or standing regulations?",
            YesNoResponse,
        ),
        (
            "Is the only sign a 'Park Boston' sign with a meter zone number?",
            YesNoResponse,
        ),
    )

    for user_prompt, response_schema in prompts:
        contents: genai.types.ContentListUnionDict = [
            genai.types.Content(
                parts=[
                    genai.types.Part.from_bytes(
                        data=image_bytes, mime_type="image/jpeg"
                    ),
                    genai.types.Part.from_text(text=user_prompt),
                ]
            )
        ]

        print("-----------------------------------")
        print(user_prompt)
        start = time.perf_counter()

        mime = "application/json" if response_schema else "text/plain"

        response = await call_gemini_client(
            client=client,
            system_instruction=system_instruction,
            contents=contents,
            response_schema=response_schema,
            response_mime_type=mime,
            model_opts=model_opts,
        )

        if response_schema:
            print(response.parsed.value)
        else:
            print(response.text)

        print(f"Used {response.usage_metadata.total_token_count} tokens.")
        print(f"Done in {time.perf_counter() - start:.2f} seconds.")


if __name__ == "__main__":
    load_dotenv()
    # Instructions file
    local_path = Path(__file__).resolve().parent
    instruction_file = local_path / "instructions/preprocess_instruction.txt"
    system_instruction = load_from_txt(instruction_file)

    # Test image file
    test_image_path = Path(
        "/home/smcatee/github/smart-prototype/tests/sign_reader/test_data/"
    )
    images = [
        "01-limit2hr-1600.0000-none.jpg",
        "101-back-of-a-van.jpg",
        "102-signs-in-a-tree.jpg",
        "103-brick-wall.jpg",
        "104-single-blurry.jpg",
        "105-crossing.jpg",
    ]

    settings = GeminiOptions(
        model="gemini-3.1-flash-lite-preview",
        thinking_level=genai.types.ThinkingLevel.MINIMAL,
        temperature=0,  # Must be from 0 to 2 (inclusive)
        mock_ai=False,
    )  # For debugging, mock the AI call instead of running it

    test_image = test_image_path / images[4]

    image_bytes = test_image.read_bytes()

    client = init_gemini_client()
    asyncio.run(
        pre_test_image(
            client=client,
            system_instruction=system_instruction,
            image_bytes=image_bytes,
            model_opts=settings,
        )
    )
