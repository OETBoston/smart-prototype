import json
import hashlib
import pandas as pd


def normalize_list_of_dicts(data_list):
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


def get_policy_signature(policy_row, rules_df, timespans_df):
    """
    Creates a unique hash for a policy based on its rules and timespans
    """
    pid = policy_row['curb_policy_id']

    # 1. Get Rules
    rules = rules_df[rules_df['curb_policy_id'] == pid].copy()
    rules = rules.drop(columns=['rule_id', 'curb_policy_id'], errors='ignore')
    rules = rules.astype(str)
    rules_list = normalize_list_of_dicts(rules.to_dict('records'))

    # 2. Get Timespans
    timespans = timespans_df[timespans_df['curb_policy_id'] == pid].copy()
    timespans = timespans.drop(columns=['time_span_id', 'curb_policy_id'], errors='ignore')
    timespans = timespans.astype(str)
    ts_list = normalize_list_of_dicts(timespans.to_dict('records'))


    # 3. Combine into a single structure
    full_policy = {
        "priority": str(int(float(policy_row['priority']))) if pd.notna(policy_row['priority']) else "nan",
        "rules": rules_list,
        "time_spans": ts_list
    }

    # 4. Hash the result
    policy_json = json.dumps(full_policy, sort_keys=True, default=str)
    return hashlib.md5(policy_json.encode()).hexdigest()