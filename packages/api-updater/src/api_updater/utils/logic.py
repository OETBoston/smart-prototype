import asyncio
import json
from pathlib import Path

import pandas as pd
from curb_utils.ai_client import GeminiOptions
from curb_utils.io_tools import load_from_txt

from api_updater.descriptions import (
    add_json_to_prompt,
    generate_description,
    init_gemini_client,
)


def normalize_list_of_dicts(data_list) -> list[dict]:
    """Normalizes a list of dictionaries by removing key-value pairs with "null" values
    and converting all values to strings.
    Args:"
        data_list (list): A list of dictionaries to be normalized.
    Returns:
        list: A normalized list of dictionaries with non-null values as strings.
    """
    if not data_list:
        return []

    normalized = []
    for d in data_list:
        # 1. Only include key-value pairs where the value is not "null"
        # 2. Force the remaining values to string
        clean_dict = {}
        for k, v in d.items():
            val_str = str(v)
            # Skip if value is logically "null"
            if v is None or val_str.lower() in ["nan", "none", "null", ""]:
                continue
            clean_dict[str(k)] = val_str

        if clean_dict:  # Only add if the rule isn't completely empty
            normalized.append(clean_dict)

    # Sort the list of dicts by their content (deterministic)
    return sorted(normalized, key=lambda x: sorted(x.items()))


def get_policy_json(policies_df, rules_df, spans_df, rates_df) -> list[str]:
    """
    Transforms policy-related DataFrames into a list of JSON strings.
    Each string represents a policy with its associated rules, time spans, and rates.
    Args:
        policies_df (pd.DataFrame): DataFrame containing policy IDs.
        rules_df (pd.DataFrame): DataFrame containing policy rules.
        spans_df (pd.DataFrame): DataFrame containing policy time spans.
        rates_df (pd.DataFrame): DataFrame containing policy rates.
    Returns:
        list: A list of JSON strings, each representing a policy and its data.
    """

    def prepare_lookup(df, drop_cols) -> dict:
        # 1. Separate the ID column from the columns we want to stringify
        id_col = "curb_policy_id"
        other_cols = [c for c in df.columns if c not in drop_cols and c != id_col]

        # 2. Convert only the 'content' columns to string
        df_clean = df[[id_col] + other_cols].copy()
        df_clean[other_cols] = df_clean[other_cols].astype(str)

        # 3. Group by the original type ID
        # This creates { policy_id: [ {rule1}, {rule2} ] }
        return {
            pid: normalize_list_of_dicts(
                group.drop(columns=["curb_policy_id"]).to_dict("records")
            )
            for pid, group in df_clean.groupby("curb_policy_id")
        }

    # Pre-calculate lookups
    rules_lookup = prepare_lookup(rules_df, ["rule_id", "name", "description"])
    spans_lookup = prepare_lookup(spans_df, ["time_span_id"])
    rates_lookup = prepare_lookup(rates_df, ["rate_id"])

    policy_json = []

    # Use a standard loop or list comprehension (faster than .apply for dict lookups)
    for pid, name in zip(
        policies_df["curb_policy_id"], policies_df["name"], strict=False
    ):
        if pd.isna(name):
            full_policy = {
                "rules": rules_lookup.get(pid, []),
                "time_spans": spans_lookup.get(pid, []),
                "rates": rates_lookup.get(pid, []),
            }
        else:
            full_policy = {
                "name": name,
                "rules": rules_lookup.get(pid, []),
                "time_spans": spans_lookup.get(pid, []),
                "rates": rates_lookup.get(pid, []),
            }

        policy_json.append(json.dumps(full_policy, sort_keys=True, default=str))

    return policy_json


async def get_policy_descriptions(
    policies_df: pd.DataFrame,
    gemini_settings: GeminiOptions,
    gemini_concurrent_limit: int,
) -> list[str]:
    """
    Generates natural language descriptions for each policy in a DataFrame.

    Args:
        policies_df (pd.DataFrame): DataFrame containing a 'policy_json' column.
        api_key (str): Your Gemini API Key.

    Returns:
        List[str]: A list of generated descriptions.
    """

    sem = asyncio.Semaphore(gemini_concurrent_limit)

    instruction_directory = Path(__file__).resolve().parent.parent / "instructions"
    instruction_file = instruction_directory / "default_instructions_descriptions.txt"
    prompt_file = instruction_directory / "default_prompt_descriptions.txt"

    system_instruciton = load_from_txt(instruction_file)
    prompt_base = load_from_txt(prompt_file)

    async def process_policy(policy_json: str) -> str:
        policy_str = (
            json.dumps(policy_json) if not isinstance(policy_json, str) else policy_json
        )
        prompt = add_json_to_prompt(prompt_base, policy_str)

        description = await generate_description(
            client=client,
            sem=sem,
            prompt=prompt,
            system_instruction=system_instruciton,
            model_opts=gemini_settings,
        )
        return description

    with init_gemini_client() as client:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(process_policy(policy))
                for policy in policies_df["policy_json"]
            ]

    # Collect results from all description retrievals
    return [t.result() for t in tasks]
