"""Exercise backfill after deduplication and active-policy filtering."""

from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import uuid4

import pandas as pd
import pytest
from api_updater import transformer
from curb_utils.ai_client import GeminiOptions
from shapely.geometry import LineString


@pytest.mark.parametrize(
    "value", [["school days"], '["school days"]', "['school days']"]
)
def test_designated_period_retains_array_contract(value) -> None:
    assert transformer.normalize_designated_period(value) == ["school days"]


def sample_tables(existing: bool) -> tuple[dict, dict, object, object]:
    """A no-parking curb, with an optional identical published policy and zone."""
    zone, policy, segment = uuid4(), uuid4(), uuid4()
    line = LineString([(-71.06, 42.35), (-71.061, 42.35)])
    staging = {
        "curb_segments": pd.DataFrame(
            [
                {
                    "segment_id": segment,
                    "blockface_id": uuid4(),
                    "segment_seq": 0,
                    "geography": line.wkb_hex,
                }
            ]
        ),
        "curb_segment_policies": pd.DataFrame(
            [
                {
                    "segment_id": segment,
                    "policy_list": [
                        {"rules": [{"activity": "no parking"}], "priority": 1}
                    ],
                }
            ]
        ),
    }
    api = {
        "curb_zones": pd.DataFrame(
            [[zone, line, None]] if existing else [],
            columns=["curb_zone_id", "geometry", "end_date"],
        ),
        "curb_policies": pd.DataFrame(
            [[policy, None, None, 1]] if existing else [],
            columns=["curb_policy_id", "name", "description", "priority"],
        ),
        "curb_zone_policies": pd.DataFrame(
            [[zone, policy]] if existing else [],
            columns=["curb_zone_id", "curb_policy_id"],
        ),
        "curb_policy_rules": pd.DataFrame(
            [[uuid4(), policy, "no parking"]] if existing else [],
            columns=["rule_id", "curb_policy_id", "activity"],
        ),
        "curb_policy_time_spans": pd.DataFrame(
            columns=["time_span_id", "curb_policy_id", "designated_period"]
        ),
        "curb_policy_rates": pd.DataFrame(columns=["rate_id", "curb_policy_id"]),
    }
    return staging, api, zone, policy


@pytest.mark.parametrize("existing", [False, True])
def test_description_generation_after_deduplication(monkeypatch, existing) -> None:
    staging, api, zone, policy = sample_tables(existing)
    generate = AsyncMock(return_value=["No Parking"])
    monkeypatch.setattr(transformer, "get_policy_descriptions", generate)
    result = transformer.transform_policy_updates(
        deepcopy(staging), api, GeminiOptions(), 1
    )
    policies = result["curb_policies"]["table"]
    assert len(policies) == 1
    assert policies.iloc[0]["description"] == "No Parking"
    assert len(result["curb_policy_rules"]["table"]) == 1
    assert result["curb_policy_rates"]["table"].empty
    if existing:
        assert policies.iloc[0]["curb_policy_id"] == policy
        assert result["curb_zones"]["table"].iloc[0]["curb_zone_id"] == zone
        assert result["curb_zone_policies"]["table"].empty
        assert result["curb_zone_policies_delete"]["table"].empty
        api["curb_policies"] = policies
        transformer.transform_policy_updates(deepcopy(staging), api, GeminiOptions(), 1)
        assert generate.await_count == 1


def test_inactive_unrelated_policy_is_not_backfilled(monkeypatch) -> None:
    staging, api, _, _ = sample_tables(True)
    api["curb_policies"].loc[1] = [uuid4(), "Inactive", None, 93]
    generate = AsyncMock(return_value=["No Parking"])
    monkeypatch.setattr(transformer, "get_policy_descriptions", generate)
    transformer.transform_policy_updates(staging, api, GeminiOptions(), 1)
    assert len(generate.await_args.args[0]) == 1


def test_changed_zone_keeps_existing_policy_in_replacement_links(monkeypatch) -> None:
    staging, api, zone, policy = sample_tables(True)
    staging["curb_segment_policies"].iloc[0]["policy_list"].append(
        {"priority": 2, "rules": [{"activity": "no stopping"}]}
    )
    generate = AsyncMock(return_value=["No Stopping", "No Parking"])
    monkeypatch.setattr(transformer, "get_policy_descriptions", generate)
    result = transformer.transform_policy_updates(staging, api, GeminiOptions(), 1)
    links = result["curb_zone_policies"]["table"]
    removed = result["curb_zone_policies_delete"]["table"]
    assert len(links) == 2
    assert set(links["curb_zone_id"]) == {zone}
    assert policy in set(links["curb_policy_id"])
    assert removed.iloc[0]["curb_policy_id"] == policy


def test_rounding_drift_preserves_equivalent_zone_identity(monkeypatch) -> None:
    staging, api, zone, policy = sample_tables(True)
    api["curb_zones"].at[0, "geometry"] = LineString(
        [(-71.06, 42.35 + 1e-12), (-71.061, 42.35 + 1e-12)]
    )
    monkeypatch.setattr(
        transformer, "get_policy_descriptions", AsyncMock(return_value=["No parking"])
    )
    result = transformer.transform_policy_updates(staging, api, GeminiOptions(), 1)
    active = result["curb_zones"]["table"].query("end_date.isna()")
    assert list(active.curb_zone_id) == [zone]
    assert result["curb_zone_policies"]["table"].empty
    assert result["curb_zone_policies_delete"]["table"].empty
    assert list(result["curb_policies"]["table"].curb_policy_id) == [policy]


def test_split_with_rounding_expires_old_zone_but_keeps_touching_neighbor(
    monkeypatch,
) -> None:
    staging, api, old_zone, policy = sample_tables(True)
    blockface = staging["curb_segments"].iloc[0].blockface_id
    second = uuid4()
    staging["curb_segments"].at[0, "geography"] = LineString(
        [(-71.06, 42.35 + 1e-12), (-71.0605, 42.35 + 1e-12)]
    ).wkb_hex
    staging["curb_segments"].loc[1] = [
        second,
        blockface,
        1,
        LineString([(-71.0605, 42.35 + 1e-12), (-71.061, 42.35 + 1e-12)]).wkb_hex,
    ]
    staging["curb_segment_policies"].loc[1] = [
        second,
        [{"priority": 2, "rules": [{"activity": "no stopping"}]}],
    ]
    neighbor = uuid4()
    api["curb_zones"].loc[1] = [
        neighbor,
        LineString([(-71.061, 42.35), (-71.062, 42.35)]),
        None,
    ]
    api["curb_zone_policies"].loc[1] = [neighbor, policy]
    monkeypatch.setattr(
        transformer,
        "get_policy_descriptions",
        AsyncMock(return_value=["No stopping", "No parking"]),
    )
    result = transformer.transform_policy_updates(staging, api, GeminiOptions(), 1)
    zones = result["curb_zones"]["table"]
    assert set(zones.loc[zones.end_date.notna(), "curb_zone_id"]) == {old_zone}
    active_ids = set(zones.loc[zones.end_date.isna(), "curb_zone_id"])
    assert neighbor in active_ids
    assert len(active_ids) == 3
    removed = result["curb_zone_policies_delete"]["table"]
    assert set(removed.curb_zone_id) == {old_zone}
