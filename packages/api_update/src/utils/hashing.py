import hashlib


def get_policy_signatures(policies_df):
    """
    Generates a unique hash signature for each policy based on its JSON representation.
    Args:
        policies_df (pd.DataFrame): DataFrame containing a 'policy_json' column with JSON strings of policies.
    Returns:
        list: A list of hash signatures corresponding to each policy.
    """

    signatures = []
    for json_str in policies_df['policy_json']:
        signature = hashlib.md5(json_str.encode()).hexdigest()
        signatures.append(signature)
    return signatures
