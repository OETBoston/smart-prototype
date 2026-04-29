"""Gemini rapid pre-processor to evaluate sign image suitability"""

import asyncio
import time
from enum import Enum
from logging import Logger
from pathlib import Path
from typing import Annotated, Any, TypeGuard

from curb_utils.ai_client import GeminiOptions, call_gemini_client, init_gemini_client
from curb_utils.io_tools import load_from_txt
from curb_utils.logging import log_list
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field


class YesNo(str, Enum):
    yes = "yes"
    no = "no"


class HasValue(BaseModel):
    value: Any


class YesNoResponse(HasValue):
    value: YesNo


class PositiveIntResponse(HasValue):
    value: Annotated[int, Field(ge=1)]


def is_valid_response(obj: object, schema: type[HasValue]) -> TypeGuard[HasValue]:
    return isinstance(obj, schema)


class PromptInfo(BaseModel):
    prompt: str
    response_schema: type[HasValue] | None = None
    acceptable_response: Any = None
    error_text: str
    run_check: bool = True


async def pre_test_image(
    client: genai.Client,
    system_instruction: str,
    image_bytes: bytes,
    image_uri: str,
    logger: Logger,
    model_opts: GeminiOptions | None = None,
    check_multiple: bool = False,
) -> tuple[bool, str]:
    log_messages = []
    log_messages.append(("debug", f"Pre-testing {image_uri}"))
    prompts = (
        PromptInfo(
            prompt="Answer with yes or no: Does this image contain "
            + "one or more signs?",
            response_schema=YesNoResponse,
            acceptable_response=YesNo.yes,
            error_text="Image does not contain signs",
        ),
        PromptInfo(
            prompt="Answer with yes or no: Is the image high enough quality to "
            + "accurately read ALL information on the sign or signs?  Answer no if the "
            + "image can not be read becuase it is low-resolution, blurry, or "
            + "because signs are obscured.",
            acceptable_response=YesNo.yes,
            response_schema=YesNoResponse,
            error_text="Image is not of high enough quality",
        ),
        PromptInfo(
            prompt="How many complete signs are present in the image? Do not count "
            + "signs that are not street signs or that are only partially in the "
            + "image.",
            response_schema=PositiveIntResponse,
            acceptable_response=1,
            error_text="Image contains more than one sign",
            run_check=check_multiple,
        ),
        PromptInfo(
            prompt="Does at least one sign contain information about parking, "
            + "loading, stopping, or standing regulations?",
            response_schema=YesNoResponse,
            acceptable_response=YesNo.yes,
            error_text="Sign does not contain parking regulation information",
        ),
        PromptInfo(
            prompt="Is the only sign a 'Park Boston' sign with a meter zone number?",
            response_schema=YesNoResponse,
            acceptable_response=YesNo.no,
            error_text="Image is only a Park Boston meter sign",
        ),
    )

    for prompt_obj in [p for p in prompts if p.run_check]:
        contents: genai.types.ContentListUnionDict = [
            genai.types.Content(
                parts=[
                    genai.types.Part.from_bytes(
                        data=image_bytes, mime_type="image/jpeg"
                    ),
                    genai.types.Part.from_text(text=prompt_obj.prompt),
                ]
            )
        ]

        log_messages.append(("debug", prompt_obj.prompt))
        start = time.perf_counter()

        mime = "application/json" if prompt_obj.response_schema else "text/plain"

        response = await call_gemini_client(
            client=client,
            system_instruction=system_instruction,
            contents=contents,
            logger=logger,
            response_schema=prompt_obj.response_schema,
            response_mime_type=mime,
            model_opts=model_opts,
        )

        if prompt_obj.response_schema:
            if is_valid_response(response.parsed, prompt_obj.response_schema):
                result = response.parsed.value
            else:
                result = None
        else:
            result = response.text

        log_messages.append(("debug", result))
        if response.usage_metadata is not None:
            log_messages.append(
                ("debug", f"Used {response.usage_metadata.total_token_count} tokens.")
            )
        log_messages.append(
            ("debug", f"Done in {time.perf_counter() - start:.2f} seconds.")
        )

        if not result:
            log_list(logger, log_messages)
            return (False, "LLM did not produce a valid response")
        if result != prompt_obj.acceptable_response:
            log_messages.append(("debug", f"Image rejected: {prompt_obj.error_text}"))
            log_list(logger, log_messages)
            return (False, prompt_obj.error_text)

    # Indicate success if we're still here

    log_messages.append(("debug", "Image accepted."))

    log_list(logger, log_messages)
    return (True, "")


if __name__ == "__main__":
    from curb_utils.logging import setup_logger

    load_dotenv()
    logger, console = setup_logger(__name__)
    logger.setLevel("DEBUG")
    # Instructions file
    local_path = Path(__file__).resolve().parent
    instruction_file = local_path / "instructions/preprocess_instruction.txt"
    system_instruction = load_from_txt(instruction_file)

    # Test image file
    test_image_path = (
        Path(__file__).parent.parent.parent.parent.parent
        / "tests/sign_reader/test_data/"
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

    test_image = test_image_path / images[0]

    image_bytes = test_image.read_bytes()

    client = init_gemini_client()
    asyncio.run(
        pre_test_image(
            client=client,
            system_instruction=system_instruction,
            image_bytes=image_bytes,
            image_uri=str(test_image),
            logger=logger,
            model_opts=settings,
        )
    )
