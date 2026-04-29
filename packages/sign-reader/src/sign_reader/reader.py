"""Gemini content generation and structured image reading logic."""

from logging import Logger

from curb_utils.ai_client import GeminiOptions, call_gemini_client
from curb_utils.logging import log_list
from google import genai
from pydantic import ValidationError

from sign_reader.models import Image


async def get_image_policy(
    client: genai.Client,
    system_instruction: str,
    user_prompt: str,
    image_bytes: bytes,
    image_uri: str,
    logger: Logger,
    model_opts: GeminiOptions | None = None,
    max_retries: int = 3,
) -> Image | None:
    """Send image data to Gemini model for structured JSON output.

    Args:
        client (genai.Client): Initialized Gemini API client.
        system_instruction (str): Instruction string to guide model response.
        user_prompt (str): User prompt string to guide model response.
        image_bytes (bytes): Raw image data in bytes format.
        image_uri (str): Image URI to use.
        model:opts (GeminiOptions | None, optional): Settings for the Gemini run.
        max_retries (int, optional): Maximum number of retries for validation failures
                                     (default=3)

    Returns:
        Image: Parsed structured response mapped to Image schema.
    """

    log_messages = []
    log_messages.append(("info", f"Reading {image_uri}"))

    contents: genai.types.ContentListUnionDict = [
        genai.types.Content(
            parts=[
                genai.types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                genai.types.Part.from_text(text=user_prompt),
            ]
        )
    ]

    attempts = 0

    while attempts <= max_retries:
        # 1. Generate content with the current 'contents' history
        response = await call_gemini_client(
            client=client,
            system_instruction=system_instruction,
            contents=contents,
            logger=logger,
            response_schema=Image,
            response_mime_type="application/json",
            model_opts=model_opts,
        )

        # 2. Top-level validation
        if response is None:
            raise RuntimeError("No response from AI model")

        if response.parsed is not None:
            if attempts > 0:
                log_messages.append(
                    (
                        "info",
                        f"Fixed JSON output for Image {image_uri} "
                        f"after {attempts} attempt(s).",
                    )
                )

            result = response.parsed
            if not isinstance(result, Image):
                raise TypeError("Incorrect data type provided by the AI model.")

            log_messages.append(("info", f"Completed processing image {image_uri}"))
            log_list(logger, log_messages)
            return result

        else:
            attempts += 1
            if attempts > max_retries:
                log_messages.append(
                    (
                        "warning",
                        f" Max retries reached for validating JSON output "
                        f"for image {image_uri} after {max_retries}. Returning None.",
                    )
                )
                log_list(logger, log_messages)
                return None
            log_messages.append(
                (
                    "info",
                    f"Failed to validate JSON output for Image {image_uri}. "
                    f"Attempt {attempts}/{max_retries}.",
                )
            )

            # 3. Extract the raw text Gemini sent to echo it back in the conversation
            if (
                response.candidates is None
                or response.candidates[0].content is None
                or response.candidates[0].content.parts is None
                or response.candidates[0].content.parts[0].text is None
            ):
                # Unlikely resut - if the response can't be parsed

                log_messages.append(
                    (
                        "warning",
                        f"Unable to parse response details to retry analysis "
                        f"of image {image_uri}. Returning None.",
                    )
                )
                log_list(logger, log_messages)
                return None

            bad_response_text = response.candidates[0].content.parts[0].text

            # 4. Collect fine-grained errors
            try:
                Image.model_validate_json(bad_response_text)
            except ValidationError as e:
                error_lines = []
                for err in e.errors():
                    loc = " -> ".join(str(v) for v in err["loc"])
                    msg = err["msg"]
                    actual_value = err.get("input", "Unknown")
                    error_lines.append(
                        f"- FIELD: {loc}\n  ERROR: {msg}\n  VALUE SENT: {actual_value}"
                    )
                error_message = "\n".join(error_lines)

                # 5. CONSTRUCT THE FEEDBACK
                # Turn 1: Add the model's bad answer as a 'model' role
                model_turn = genai.types.Content(
                    role="model",
                    parts=[genai.types.Part.from_text(text=bad_response_text)],
                )

                contents.append(model_turn)

                # Turn 2: Add the correction request as a 'user' role
                feedback = (
                    f"Your previous JSON output had the following validation errors:"
                    f"\n\n{error_message}\n\n"
                    f"Please output the FULL corrected object matching the schema."
                )
                contents.append(genai.types.Part.from_text(text=feedback))

    log_list(logger, log_messages)
    return None
