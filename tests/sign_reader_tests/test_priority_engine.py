import json
import os

import pytest
from core.priority_engine import get_policy_priority
from models import Policy

# Load the JSON test cases
TEST_FILE_PATH = os.path.join(
    os.path.dirname(__file__), "test_data", "priority_test_cases.json"
)

with open(TEST_FILE_PATH, "r") as f:
    TEST_CASES = json.load(f)


def modify_timespans_for_start_date(policy, original_json) -> Policy:
    time_spans_json = original_json.get("time_spans", [])
    if policy.time_spans:
        for p_span, j_span in zip(policy.time_spans, time_spans_json, strict=False):
            if "start_date" in j_span:
                p_span.__dict__["start_date"] = j_span["start_date"]
            if "end_date" in j_span:
                p_span.__dict__["end_date"] = j_span["end_date"]
    return policy


@pytest.mark.parametrize("case", TEST_CASES, ids=lambda c: c["description"])
def test_priority(case) -> None:
    policy = Policy.model_validate(case["policy"])

    policy = modify_timespans_for_start_date(policy, case["policy"])

    expected_priority = case["expected_priority"]

    assert get_policy_priority(policy) == expected_priority
