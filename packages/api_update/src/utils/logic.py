import json
import hashlib
from .hashing import normalize_list_of_dicts


def check_if_policy_exists(new_policy_dict, existing_signatures):
    # 1. Normalize Rules: Convert values to strings and sort
    str_rules = normalize_list_of_dicts(new_policy_dict.get('rules', []))
    str_timespans = normalize_list_of_dicts(new_policy_dict.get('time_spans', []))

    # 3. Final Normalized Object
    normalized_policy = {
        "priority": str(new_policy_dict.get('priority')) if new_policy_dict.get('priority') is not None else "nan",
        "rules": str_rules,
        "time_spans": str_timespans
    }

    # 4. Generate Hash
    new_json = json.dumps(normalized_policy, sort_keys=True)
    new_sig = hashlib.md5(new_json.encode()).hexdigest()

    # Check against the Series of existing hashes
    return new_sig in existing_signatures.index, new_sig

