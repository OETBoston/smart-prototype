import os
import json
import logging
from policies_ai.clients import init_gemini_client
from policies_ai.policy_descriptions.descriptions import generate_description, add_json_to_prompt, default_prompt


logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def normalize_list_of_dicts(data_list):
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
            if v is None or val_str.lower() in ['nan', 'none', 'null', '']:
                continue
            clean_dict[str(k)] = val_str

        if clean_dict:  # Only add if the rule isn't completely empty
            normalized.append(clean_dict)

    # Sort the list of dicts by their content (deterministic)
    return sorted(normalized, key=lambda x: sorted(x.items()))


def get_policy_json(policies_df, rules_df, spans_df, rates_df):
    """
    Transforms policy-related DataFrames into a list of JSON strings,
    where each string represents a policy with its associated rules, time spans, and rates.
    Args:
        policies_df (pd.DataFrame): DataFrame containing policy IDs.
        rules_df (pd.DataFrame): DataFrame containing policy rules with 'curb_policy_id' as a key.
        spans_df (pd.DataFrame): DataFrame containing policy time spans with 'curb_policy_id' as a key.
        rates_df (pd.DataFrame): DataFrame containing policy rates with 'curb_policy_id' as a key.
    Returns:
        list: A list of JSON strings, each representing a policy and its associated data.
    """

    def prepare_lookup(df, drop_cols):
        # 1. Separate the ID column from the columns we want to stringify
        id_col = 'curb_policy_id'
        other_cols = [c for c in df.columns if c not in drop_cols and c != id_col]

        # 2. Convert only the 'content' columns to string
        df_clean = df[[id_col] + other_cols].copy()
        df_clean[other_cols] = df_clean[other_cols].astype(str)

        # 3. Group by the original type ID
        # This creates { policy_id: [ {rule1}, {rule2} ] }
        return {
            pid: normalize_list_of_dicts(group.drop(columns=['curb_policy_id']).to_dict('records'))
            for pid, group in df_clean.groupby('curb_policy_id')
        }

    # Pre-calculate lookups
    rules_lookup = prepare_lookup(rules_df, ['rule_id', 'name', 'description'])
    spans_lookup = prepare_lookup(spans_df, ['time_span_id'])
    rates_lookup = prepare_lookup(rates_df, ['rate_id'])

    policy_json = []

    # Use a standard loop or list comprehension (faster than .apply for dict lookups)
    for pid in policies_df['curb_policy_id']:
        full_policy = {
            "rules": rules_lookup.get(pid, []),
            "time_spans": spans_lookup.get(pid, []),
            "rates": rates_lookup.get(pid, [])
        }

        policy_json.append(json.dumps(full_policy, sort_keys=True, default=str))

    return policy_json


def get_policy_descriptions(policies_df):
    """Generates natural language descriptions for each policy based on its JSON representation using Gemini.
    Args:
        policies_df (pd.DataFrame): DataFrame containing a 'policy_json' column
    Returns:
        list: A list of natural language descriptions corresponding to each policy.
    """
    descriptions = []
    logger.info("Initializing Gemini client...")
    with init_gemini_client(os.getenv("GEMINI_API_KEY")) as client:
        for idx, json_str in enumerate(policies_df['policy_json']):
            logger.info("Generating description for policy %d/%d", idx + 1, len(policies_df))
            prompt = add_json_to_prompt(default_prompt, json_str)
            descriptions.append(generate_description(client, prompt, model_opts=None))
    return descriptions
