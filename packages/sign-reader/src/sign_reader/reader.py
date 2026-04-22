"""Gemini content generation and structured image reading logic."""

from google import genai
from pydantic import ValidationError

from sign_reader.models import Image


def read_image(
    client: genai.Client,
    gemini_model: str,
    system_instruction: str,
    user_prompt: str,
    temperature: float,
    image_url: str,
    image_bytes: bytes,
    thinking_level: str = "minimal",
    max_retries: int = 3,
) -> Image | None:
    """Send image data to Gemini model for structured JSON output.

    Args:
        client (genai.Client): Initialized Gemini API client.
        gemini_model (str): Gemini model name.
        system_instruction (str): Instruction string to guide model response.
        user_prompt (str): User prompt string to guide model response.
        temperature (float): Model temperature. Higher values increase creativity.
        image_url (str): Image URL to use.
        image_bytes (bytes): Raw image data in bytes format.
        thinking_level (str): Thinking level to use.
        max_retries (int): Maximum number of retries for validation failures.

    Returns:
        Image: Parsed structured response mapped to Image schema.
    """

    contents = [
        genai.types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        genai.types.Part.from_text(text=user_prompt),
    ]

    attempts = 0

    if gemini_model.startswith("gemini-3"):
        thinking_cfg = genai.types.ThinkingConfig(
            include_thoughts=False,
            thinking_level=thinking_level,
        )
    else:
        thinking_cfg = genai.types.ThinkingConfig(
            include_thoughts=False,
        )

    while attempts <= max_retries:
        # 1. Generate content with the current 'contents' history
        response = client.models.generate_content(
            model=gemini_model,
            contents=contents,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=Image,
                temperature=temperature,
                thinking_config=thinking_cfg,
            ),
        )

        # 2. Top-level validation
        if response.parsed is not None:
            if attempts > 0:
                print(
                    f"✅ Fixed JSON output for Image {image_url} "
                    f"after {attempts} attempt(s)."
                )
            return response.parsed
        else:
            attempts += 1
            if attempts > max_retries:
                print(
                    f"❌ Max retries reached for validating JSON output "
                    f"for image {image_url} after {max_retries}. Returning None."
                )
                return None
            print(
                f"⚠️ Failed to validate JSON output for Image {image_url}. "
                f"Attempt {attempts}/{max_retries}."
            )

            # 3. Extract the raw text Gemini sent to echo it back in the conversation
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

    return None
