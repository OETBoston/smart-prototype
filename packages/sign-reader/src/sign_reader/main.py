"""Main entry point for the Sign Reader CLI using Gemini API.

This script loads environment variables, initializes the Gemini client,
reads a list of image URLs from a text file, performs structured sign analysis,
and saves the parsed output into JSON files.

Author:
    Ray Huang
"""

import asyncio
import uuid
from logging import Logger
from pathlib import Path

from curb_utils.ai_client import GeminiOptions, init_gemini_client
from curb_utils.db_utils import append_job
from curb_utils.io_tools import load_from_txt, load_from_yaml
from dotenv import load_dotenv
from google import genai

from sign_reader.db_connector import (
    append_sign_policies,
    read_images,
)
from sign_reader.io_utils.image_utils import get_image
from sign_reader.io_utils.storage import (
    save_parsed_output,
)
from sign_reader.logging_tools import get_logger
from sign_reader.priority_engine import get_policy_priority
from sign_reader.reader import read_image

BATCH_SIZE = 50
load_dotenv()


async def main() -> None:
    logger = get_logger()
    logger.info("Running Sign Reader Task...")

    # Define external files
    local_path = Path(__file__).resolve().parent
    config_file = local_path / "config.yaml"
    instruction_file = local_path / "instructions/default_instruction.txt"
    user_prompt_file = local_path / "instructions/default_user_prompt.txt"

    # Load external data
    config = load_from_yaml(config_file)
    system_instruction = load_from_txt(instruction_file)
    user_prompt = load_from_txt(user_prompt_file)

    # Gemini Settings
    gemini_settings = GeminiOptions(**config["gemini_settings"])

    # Database Settings
    db_name = config["db_name"]
    db_schema = config["db_schema"]

    # Sign Settings
    sign_job_id = config["sign_assets"]["job_id"]
    sign_re_process = config["sign_assets"]["re_process"]

    # Other settings
    debug_mode = config["debug_mode"]
    max_images = config["max_images"]
    job_name = config.get("sr_job_name")
    job_desc = config.get("sr_job_description")

    # async settings
    # sem_limit: int = config.get("gemini_concurrent_limit", 1)

    # Set up the semaphore - defaulting to max 1 if not set
    # sem = asyncio.Semaphore(sem_limit)

    # If in debug mode, save the parsed outputs to disk
    output_dir = Path("outputs/sign_reader")
    if debug_mode:
        output_dir.mkdir(parents=True, exist_ok=True)  # create dir if not exists
        job_id = uuid.uuid4()  # placeholder job for debug mode
    else:
        logger.info("Registering job...")
        job_id = append_job(
            db_name=db_name,
            db_schema=db_schema,
            db_table="sign_reader_jobs",
            job_name=job_name,
            job_desc=job_desc,
        )

    logger.info("Fetching images from database...")
    images_list = read_images(
        asset_job_id=uuid.UUID(sign_job_id) if sign_job_id else None,
        re_process=sign_re_process,
    )

    # Debug - image limit
    if max_images and max_images > 0 and max_images < len(images_list):
        START_AT = 0
        images_list = images_list[START_AT : max_images + START_AT]

    # Processing Loop
    logger.info(f"Queueing {len(images_list)} images for processing.")
    records_policies = []

    with init_gemini_client() as client:
        ### Put in asyncio.TaskGroup() as tg: -->
        ### then create tasks using tg.create_task(<<function to run>>)
        for image_uri, sign_id in images_list:
            logger.info(f"Processing Sign ID: {sign_id} | URI: {image_uri}")

            await process_image(
                client=client,
                system_instruction=system_instruction,
                user_prompt=user_prompt,
                image_uri=image_uri,
                sign_id=sign_id,
                job_id=job_id,
                debug_mode=debug_mode,
                output_dir=output_dir,
                logger=logger,
                records_policies=records_policies,
                model_opts=gemini_settings,
                max_retries=max_images,
            )

    # 4. Final Batch Upload
    if records_policies:
        logger.info(f"Uploading final remaining {len(records_policies)} records...")
        append_sign_policies(records_policies, job_id)
        logger.info("Database upload complete.")


async def process_image(
    client: genai.Client,
    system_instruction: str,
    user_prompt: str,
    image_uri: str,
    sign_id: uuid.UUID,
    job_id: uuid.UUID,
    debug_mode: bool,
    output_dir: Path,
    logger: Logger,
    records_policies: list,
    model_opts: GeminiOptions | None = None,
    max_retries: int = 3,
) -> None:
    try:
        image_bytes = get_image(image_uri)
    except Exception as e:
        logger.warning(f"Failed to load {image_uri}: {e}", exc_info=True)
        return

    try:
        parsed_image = read_image(
            client,
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            model_opts=model_opts,
            image_bytes=image_bytes,
            image_uri=image_uri,
        )
    except Exception as e:
        logger.warning(f"Failed to parse {image_uri}: {e}", exc_info=True)
        return

    if parsed_image is None or not parsed_image.signs:
        # TODO: Return a policy indicating an issue with this sign/image
        logger.warning("Detection empty: No signs extracted")
        return

    # Save raw AI output to local disk - debug mode only
    if debug_mode:
        save_parsed_output(parsed_image, output_dir, image_uri, str(sign_id))
    else:  # Only write to the database if not indebug mode
        for s in parsed_image.signs:
            arrow_value = s.arrow if s.arrow and s.arrow.lower() != "none" else None

            s.policy.priority = get_policy_priority(s.policy)

            # TODO: Remove AI Confidence Score, or do a bit of cleanup here if
            # we are keeping it
            records_policies.append(
                {
                    "sign_policy_id": uuid.uuid4(),
                    "sign_id": sign_id,
                    "policy_json": s.policy.model_dump_json(
                        indent=4,
                        exclude={
                            "rules": {"__all__": {"confidence"}},
                            "time_spans": {"__all__": {"confidence"}},
                        },
                    ),
                    "policy_arrow": arrow_value,
                    "ai_confidence_score": int(getattr(s, "confidence", 0) * 100),
                }
            )
        if len(records_policies) >= BATCH_SIZE:
            logger.info(
                f"Threshold reached ({len(records_policies)}). Uploading batch..."
            )
            append_sign_policies(records_policies, job_id)
            records_policies.clear()  # Empty the list for the next batch
            logger.info("Batch upload successful.")

    logger.debug(f"Successfully parsed {len(parsed_image.signs)} signs.")


if __name__ == "__main__":
    asyncio.run(main())
