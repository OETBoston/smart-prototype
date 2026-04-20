import uuid
import pandas as pd


def add_rule(
        curb_policy_rules: pd.DataFrame,
        curb_policy_id: uuid.UUID,
        rule: dict) -> pd.DataFrame:

    new_row_gdf = pd.DataFrame([
        {
            "rule_id": uuid.uuid4(),
            "curb_policy_id": curb_policy_id,
            "activity": rule.get("activity"),
            "max_stay": rule.get("max_stay"),
            "max_stay_unit": rule.get("max_stay_unit"),
            "no_return": rule.get("no_return"),
            "no_return_unit": rule.get("no_return_unit"),
            "user_classes": rule.get("user_classes"),
            "user_classes_except": rule.get("user_classes_except"),
            "purposes": rule.get("purposes"),
        }
    ])

    curb_policy_rules = pd.concat([curb_policy_rules, new_row_gdf], ignore_index=True)

    return curb_policy_rules


def remove_rule(
        curb_policy_rules: pd.DataFrame,
        curb_policy_id: uuid.UUID
) -> pd.DataFrame:

    mask = curb_policy_rules['curb_policy_id'] == curb_policy_id
    curb_policy_rules = curb_policy_rules.loc[~mask].reset_index(drop=True)

    return curb_policy_rules



def add_time_span(
    curb_policy_time_spans: pd.DataFrame,
    curb_policy_id: uuid.UUID,
    time_span: dict,
) -> pd.DataFrame:

    new_row_gdf = pd.DataFrame([
        {
            "time_span_id": uuid.uuid4(),
            "curb_policy_id": curb_policy_id,
            "start_date": time_span.get("start_date"),
            "end_date": time_span.get("end_date"),
            "days_of_week": time_span.get("days_of_week"),
            "time_of_day_start": time_span.get("time_of_day_start"),
            "time_of_day_end": time_span.get("time_of_day_end"),
        }
    ])

    curb_policy_time_spans = pd.concat([curb_policy_time_spans, new_row_gdf], ignore_index=True)

    return curb_policy_time_spans


def remove_time_span(
        curb_policy_time_spans: pd.DataFrame,
        curb_policy_id: uuid.UUID
) -> pd.DataFrame:

    mask = curb_policy_time_spans['curb_policy_id'] == curb_policy_id
    curb_policy_time_spans = curb_policy_time_spans.loc[~mask].reset_index(drop=True)

    return curb_policy_time_spans



def add_curb_policy(
        curb_policy_id: uuid.UUID,
        curb_policies: pd.DataFrame,
        curb_policy_rules: pd.DataFrame,
        curb_policy_time_spans: pd.DataFrame,
        policy: dict,
        run_date: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:

    new_row_gdf = pd.DataFrame([
        {
            "curb_policy_id": curb_policy_id,
            "published_date": run_date,
            "priority": policy.get("priority"),
        }
    ])
    curb_policies = pd.concat([curb_policies, new_row_gdf])

    for rule in policy.get("rules", []):
        curb_policy_rules = add_rule(
            curb_policy_rules=curb_policy_rules,
            curb_policy_id=curb_policy_id,
            rule=rule
        )

    for ts in policy.get("time_spans", []):
        curb_policy_time_spans = add_time_span(
            curb_policy_time_spans=curb_policy_time_spans,
            curb_policy_id=curb_policy_id,
            time_span=ts
        )

    return curb_policies, curb_policy_rules, curb_policy_time_spans


def remove_curb_policy(
        curb_policies: pd.DataFrame,
        curb_policy_rules: pd.DataFrame,
        curb_policy_time_spans: pd.DataFrame,
        curb_policy_id: uuid.UUID
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:

    mask = curb_policies['curb_policy_id'] == curb_policy_id
    curb_policies = curb_policies.loc[~mask].reset_index(drop=True)

    mask = curb_policy_rules['curb_policy_id'] == curb_policy_id
    curb_policy_rules = curb_policy_rules.loc[~mask].reset_index(drop=True)

    mask = curb_policy_time_spans['curb_policy_id'] == curb_policy_id
    curb_policy_time_spans = curb_policy_time_spans.loc[~mask].reset_index(drop=True)

    return curb_policies, curb_policy_rules, curb_policy_time_spans

