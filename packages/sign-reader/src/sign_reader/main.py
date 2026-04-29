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

from sign_reader.config import SignReaderConfig
from sign_reader.db_connector import (
    append_sign_policies,
    read_images,
)
from sign_reader.io_utils.image_utils import get_image
from sign_reader.io_utils.storage import (
    save_parsed_output,
)
from sign_reader.logging_tools import get_logger
from sign_reader.models import Activity, Image, Policy, Rule, Sign
from sign_reader.pre_reader import pre_test_image
from sign_reader.priority_engine import get_policy_priority
from sign_reader.reader import read_image

BATCH_SIZE = 50
load_dotenv()


def unusable_image() -> Image:
    # Define the unusable policy
    return Image(
        signs=[
            Sign(
                policy=Policy(
                    priority=98,
                    time_spans=[],
                    rules=[
                        Rule(activity=Activity(value="unusable image"), purposes=None)
                    ],
                )
            )
        ]
    )


async def main() -> None:
    logger = get_logger()
    logger.info("Running Sign Reader Task...")

    # Define external files
    local_path = Path(__file__).resolve().parent
    config_file = local_path / "config.yaml"
    instruction_file = local_path / "instructions/default_instruction.txt"
    pre_instruction_file = local_path / "instructions/preprocess_instruction.txt"
    user_prompt_file = local_path / "instructions/default_user_prompt.txt"

    # Load external data
    config = SignReaderConfig(**load_from_yaml(config_file))
    system_instruction = load_from_txt(instruction_file)
    pre_system_instruction = load_from_txt(pre_instruction_file)
    user_prompt = load_from_txt(user_prompt_file)

    # Gemini Settings
    model_opts = config.gemini_settings
    pre_model_opts = config.gemini_preprocess_settings

    # Set up the semaphore - defaulting to max 1 if not set
    sem = asyncio.Semaphore(config.gemini_concurrent_limit)
    lock = asyncio.Lock()

    # If in debug mode, save the parsed outputs to disk
    output_dir = Path("outputs/sign_reader")
    if config.debug_mode:
        output_dir.mkdir(parents=True, exist_ok=True)  # create dir if not exists
        job_id = uuid.uuid4()  # placeholder job for debug mode
    else:
        logger.info("Registering job...")
        job_id = append_job(
            db_name=config.db_name,
            db_schema=config.db_schema,
            db_table="sign_reader_jobs",
            job_name=config.sr_job_name,
            job_desc=config.sr_job_description,
            model_settings=model_opts.model_dump_json(),
            system_instruction=system_instruction,
            prompt=user_prompt,
        )

    logger.info("Fetching list from database...")
    images_list = read_images(
        asset_job_id=uuid.UUID(config.sign_assets.job_id)
        if config.sign_assets.job_id
        else None,
        re_process=config.sign_assets.re_process,
    )

    # Debug - image limit
    if (
        config.max_images
        and config.max_images > 0
        and config.max_images < len(images_list)
    ):
        START_AT = 0
        images_list = images_list[START_AT : config.max_images + START_AT]

    # Processing Loop
    logger.info(f"Queueing {len(images_list)} images for processing.")
    records_policies = []

    with init_gemini_client() as client:
        async with asyncio.TaskGroup() as tg:
            ### then create tasks using tg.create_task(<<function to run>>)
            for image_uri, sign_id in images_list:
                tg.create_task(
                    process_image(
                        client=client,
                        sem=sem,
                        lock=lock,
                        pre_system_instruction=pre_system_instruction,
                        system_instruction=system_instruction,
                        user_prompt=user_prompt,
                        image_uri=image_uri,
                        sign_id=sign_id,
                        job_id=job_id,
                        debug_mode=config.debug_mode,
                        output_dir=output_dir,
                        logger=logger,
                        records_policies=records_policies,
                        pre_model_opts=pre_model_opts,
                        model_opts=model_opts,
                        max_retries=config.max_retries,
                    )
                )

    # 4. Final Batch Upload
    if records_policies:
        logger.info(f"Uploading final remaining {len(records_policies)} records...")
        append_sign_policies(records_policies, job_id)
        logger.info("Database upload complete.")


async def process_image(
    client: genai.Client,
    sem: asyncio.Semaphore,
    lock: asyncio.Lock,
    pre_system_instruction: str,
    system_instruction: str,
    user_prompt: str,
    image_uri: str,
    sign_id: uuid.UUID,
    job_id: uuid.UUID,
    debug_mode: bool,
    output_dir: Path,
    logger: Logger,
    records_policies: list,
    pre_model_opts: GeminiOptions | None = None,
    model_opts: GeminiOptions | None = None,
    max_retries: int = 3,
) -> None:
    # Running the image download and LLM in async, processing the results
    async with sem:
        logger.info(f"Processing Sign ID: {sign_id} | URI: {image_uri}")
        try:
            image_bytes = get_image(image_uri)
        except Exception:
            logger.warning(f"Failed to load {image_uri}:")
            return

        # Pre-process the image
        try:
            pre_check = await pre_test_image(
                client=client,
                system_instruction=pre_system_instruction,
                image_bytes=image_bytes,
                model_opts=pre_model_opts,
                check_multiple=False,
            )
        except Exception:
            logger.warning(f"Failed to pre-process {image_uri}:")
            return None

        if not pre_check[0]:
            logger.warning(f"Image {image_uri} failed pre-check.")
            logger.warning(pre_check[1])

            parsed_image = unusable_image()

        else:
            try:
                parsed_image = await read_image(
                    client,
                    system_instruction=system_instruction,
                    user_prompt=user_prompt,
                    model_opts=model_opts,
                    image_bytes=image_bytes,
                    image_uri=image_uri,
                    max_retries=max_retries,
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
        ####### LOCK #######
        # This section needs to be locked to prevent race conditions
        async with lock:
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
