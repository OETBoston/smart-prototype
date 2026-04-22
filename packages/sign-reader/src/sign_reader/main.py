"""Main entry point for the Sign Reader CLI using Gemini API.

This script loads environment variables, initializes the Gemini client,
reads a list of image URLs from a text file, performs structured sign analysis,
and saves the parsed output into JSON files.

Author:
    Ray Huang
"""

import getpass
import uuid
from pathlib import Path

from sign_reader.client import init_client, read_instruction
from sign_reader.db_connector import (
    append_sign_policies,
    append_sign_reader_jobs,
    read_images,
)
from sign_reader.env_loader import (
    get_gemini_config,
    get_google_cloud_token_path_and_prefix,
)
from sign_reader.io_utils.arguments import parse_args
from sign_reader.io_utils.image_utils import get_image, upload_image
from sign_reader.io_utils.storage import (
    get_storage,
    save_parsed_output,
)
from sign_reader.logging_tools import get_logger
from sign_reader.priority_engine import get_policy_priority
from sign_reader.reader import read_image

BATCH_SIZE = 50


def main() -> None:
    logger = get_logger()
    logger.info("Running Sign Reader Task...")
    args = parse_args()

    temperature = args.temperature
    if not 0.0 <= temperature <= 2.0:
        logger.error(
            f"Invalid temperature: {temperature} "
            f"(Temperature must be within the range [0.0, 2.0])"
        )
        return

    output_dir = Path("parsed_outputs")
    output_dir.mkdir(parents=True, exist_ok=True)  # create dir if not exists

    # 1. Initialize Resources
    logger.info("Initializing Gemini client and storage...")
    gemini_model, gemini_api_key, gemini_thinking_level = get_gemini_config()
    token, prefix = get_google_cloud_token_path_and_prefix()
    storage = get_storage(token)
    system_instruction = read_instruction(
        "./packages/sign-reader/src/sign_reader/instructions/default_instruction.txt"
    )
    user_prompt = read_instruction(
        "./packages/sign-reader/src/sign_reader/instructions/default_user_prompt.txt"
    )

    images_list = []
    job_id = None

    # 2. Data Acquisition & Job Registration
    if args.file:
        # logger.info(f"Reading image list from file: {args.file}")
        # uri_list = read_image_urls(args.file)
        # images_list = [(uri, "") for uri in uri_list]
        raise RuntimeError("File read method not currently available.")
    elif args.db:
        logger.info("Fetching images from database...")
        job_id = append_sign_reader_jobs(getpass.getuser())
        images_list = read_images(
            asset_job_id=uuid.UUID(args.job_id) if args.job_id else None
        )

    # 3. Processing Loop
    logger.info(f"Queueing {len(images_list)} images for processing.")
    records_policies = []

    with init_client(gemini_api_key, use_cache=False) as client:
        for image_uri, sign_id in images_list:
            logger.info(f"Processing Sign ID: {sign_id} | URI: {image_uri}")
            try:
                image_bytes = get_image(image_uri)

                if args.file:
                    upload_image(image_uri, image_bytes, prefix, storage)

                parsed_image = read_image(
                    client,
                    gemini_model,
                    system_instruction,
                    user_prompt,
                    temperature,
                    image_uri,
                    image_bytes,
                    gemini_thinking_level,
                )

                if parsed_image is None or not parsed_image.signs:
                    logger.warning("Detection empty: No signs extracted")
                    continue

                # Save raw AI output to local disk
                stem = Path(image_uri).stem
                if sign_id:
                    image_name = f"{str(sign_id)[:8]}_{stem}"
                else:
                    image_name = stem
                save_parsed_output(parsed_image, output_dir, image_name)

                if args.db:
                    for s in parsed_image.signs:
                        arrow_value = (
                            s.arrow if s.arrow and s.arrow.lower() != "none" else None
                        )

                        s.policy.priority = get_policy_priority(s.policy)

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
                                "ai_confidence_score": int(
                                    getattr(s, "confidence", 0) * 100
                                ),
                            }
                        )
                    if len(records_policies) >= BATCH_SIZE:
                        logger.info(
                            f"Threshold reached ({len(records_policies)})."
                            f" Uploading batch..."
                        )
                        append_sign_policies(records_policies, job_id)
                        records_policies.clear()  # Empty the list for the next batch
                        logger.info("Batch upload successful.")

                logger.debug(f"Successfully parsed {len(parsed_image.signs)} signs.")

            except Exception as e:
                logger.error(f"Failed to process {image_uri}: {e}", exc_info=True)

    # 4. Final Batch Upload
    if args.db and records_policies:
        logger.info(f"Uploading final remaining {len(records_policies)} records...")
        append_sign_policies(records_policies, job_id)
        logger.info("Database upload complete.")


if __name__ == "__main__":
    main()
