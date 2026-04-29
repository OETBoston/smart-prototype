import json
import logging
from pathlib import Path
from typing import Dict, Generator

import pytest
from curb_utils.ai_client import GeminiOptions
from google import genai
from sign_reader.models import Image
from sign_reader.reader import get_image_policy

TEST_DATA_DIR = Path(__file__).parent / "test_data"


class SignImagePolicy:
    """Data structure for loading images and associated JSON.
    Test JSON files should have the same stem as the image files
    """

    def __init__(self, image_file) -> None:
        self.image_path = TEST_DATA_DIR / image_file
        self.json_path = self.image_path.with_suffix(".json")
        self.image_bytes = self.load_image()
        self.policy_json = self.load_json()

    def load_image(self) -> bytes:
        image_bytes = self.image_path.read_bytes()
        return image_bytes

    def load_json(self) -> dict:
        with open(self.json_path, "r") as f:
            json_data = json.load(f)
        return json_data


async def run_gemini(client, config, image_path, image_bytes) -> Dict[str, str]:
    logger = logging.getLogger(__name__)
    parsed_image = await get_image_policy(
        client=client,
        system_instruction=config["instruction"],
        user_prompt=config["user_prompt"],
        image_bytes=image_bytes,
        image_uri=image_path,
        logger=logger,
        model_opts=GeminiOptions(**config["gemini_settings"]),
    )

    result_json = json.loads(Image.model_validate(parsed_image).model_dump_json())

    # write results for further inspection
    out_path = Path(TEST_DATA_DIR / image_path).with_suffix(".RESULT.json")
    with open(out_path, "w+") as f:
        json.dump(result_json, f, indent=2)

    return result_json


@pytest.fixture(scope="session")
def gemini_config() -> Dict[str, str]:
    from curb_utils.io_tools import load_from_txt, load_from_yaml

    # Define external files
    local_path = Path("./packages/sign-reader/src/sign_reader")
    config_file = local_path / "config.yaml"
    instructions_file = local_path / "instructions/default_instruction.txt"
    user_prompt_file = local_path / "instructions/default_user_prompt.txt"

    # Load external data
    config = load_from_yaml(config_file)
    system_instructions = load_from_txt(instructions_file)
    user_prompt = load_from_txt(user_prompt_file)

    return {
        "gemini_settings": config["gemini_settings"],
        "instruction": system_instructions,
        "user_prompt": user_prompt,
    }


@pytest.fixture(scope="session")
def gemini_client(
    gemini_config: Dict[str, str],
) -> Generator[genai.Client, None, None]:
    from curb_utils.ai_client import init_gemini_client

    with init_gemini_client() as client:
        yield client


@pytest.mark.asyncio
async def test_01_limit_2h_times_none(gemini_client, gemini_config) -> None:
    image_file = "01-limit2hr-1600.0000-none.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_02_limit_30m_anytime_left(gemini_client, gemini_config) -> None:
    image_file = "02-limit30min-anytime-left.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_03_stclean_times_days_none(gemini_client, gemini_config) -> None:
    image_file = "03-stclean.0200-0600.tues.thur-none.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_04_no_stopping_anytime_left(gemini_client, gemini_config) -> None:
    image_file = "04-no_stopping-anytime-left.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_05_no_stopping_anytime_right(gemini_client, gemini_config) -> None:
    image_file = "05-no_stopping-anytime-right.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_06_cv_times_days_right(gemini_client, gemini_config) -> None:
    image_file = "06-cv-limit30min-0700.1900-except.sun-right.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_07_pudo_10min_anytime_left(gemini_client, gemini_config) -> None:
    image_file = "07-pudo-10min-anytime-left.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_08_limit2h_except_resident_left(gemini_client, gemini_config) -> None:
    image_file = "08-limit2hr-except.resident-0800.1600-left.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_09_accessible_except_sunday_left(gemini_client, gemini_config) -> None:
    image_file = "09-accessible-except.sun-left.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_10_stclean_weeks_months_none(gemini_client, gemini_config) -> None:
    image_file = "10-stlclean-0600.0800-2nd.4th.weds-apr.nov.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_11_valet_15m_times_right(gemini_client, gemini_config) -> None:
    image_file = "11-valet-limit15m-1700.2400-right.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy


@pytest.mark.asyncio
async def test_12_combo_cv_2h_diff_days_right(gemini_client, gemini_config) -> None:
    image_file = "12-combo-cv-limit30m-except.sat.sun.-limit2h-sat.jpg"
    test_struct = SignImagePolicy(image_file=image_file)
    test_policy = test_struct.policy_json
    result_policy = await run_gemini(
        gemini_client,
        gemini_config,
        image_file,
        test_struct.image_bytes,
    )
    assert test_policy == result_policy
