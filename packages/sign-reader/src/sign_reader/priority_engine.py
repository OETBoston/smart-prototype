from sign_reader.models import Activity, Policy, Rule


def get_neg_offset(rules: list[Rule]) -> int:
    if any(r.activity == Activity.no_stopping for r in rules):
        return 1
    if any(r.activity == Activity.no_loading for r in rules):
        return 2
    if any(r.activity == Activity.no_parking for r in rules):
        return 3
    return 0


def get_policy_priority(policy: Policy) -> int:
    rules = policy.rules
    spans = policy.time_spans or []

    if not rules:
        return 99

    has_neg = any(r.activity.value.startswith("no ") for r in rules)
    has_pos = any(not r.activity.value.startswith("no ") for r in rules)

    is_user_specific = any(
        bool(r.user_classes) or bool(r.user_classes_except) or bool(r.purposes)
        for r in rules
    )
    is_time_specific = bool(spans)

    has_start_stop_date = any(
        getattr(ts, "start_date", None) is not None
        or getattr(ts, "end_date", None) is not None
        for ts in spans
    )

    dp_strings = [(ts.designated_period or []) for ts in spans]
    has_designated_period = any(bool(dp) for dp in dp_strings)

    # 1-9 Blanket Prohibitions
    if has_neg and not is_user_specific and not is_time_specific:
        offset = get_neg_offset(rules)
        return offset if offset > 0 else 9

    # 10-19 Temporary Allowances
    if has_pos and has_start_stop_date:
        return 10

    # 20-29 Temporary Prohibitions
    if has_neg and has_start_stop_date:
        return 20 + get_neg_offset(rules)

    # 30-39 Time-specific General Prohibitions
    if has_neg and not is_user_specific and is_time_specific:
        baseline = 30 if has_designated_period else 35
        return baseline + get_neg_offset(rules)

    # 40-49 User- and time-specific allowances
    if has_pos and is_user_specific and is_time_specific:
        return 40

    # 50-59 User- and time-specific prohibitions
    if has_neg and is_user_specific and is_time_specific:
        return 50 + get_neg_offset(rules)

    # 60-69 User-specific allowances
    if has_pos and is_user_specific and not is_time_specific:
        return 60

    # 70-79 User-specific prohibitions
    if has_neg and is_user_specific and not is_time_specific:
        return 70 + get_neg_offset(rules)

    # 80-89 Time-specific General Allowances
    if has_pos and not is_user_specific and is_time_specific:
        return 80

    # 90-99 Blanket Allowances
    if has_pos and not is_user_specific and not is_time_specific:
        if any(r.activity == Activity.parking for r in rules):
            return 99
        return 90

    return 99  # Default if no conditions matched
