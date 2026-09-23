"""API verification must check identities, associations and reviewed text."""

from types import SimpleNamespace
from uuid import uuid4

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString

from scripts import publish_chinatown as publication


@pytest.mark.parametrize(
    "fault", [None, "missing_description", "wrong_link", "duplicate"]
)
def test_api_verification_checks_active_records(monkeypatch, tmp_path, fault) -> None:
    zones = [{"curb_zone_id": "zone", "end_date": None, "curb_policy_ids": ["policy"]}]
    policies = [
        {"curb_policy_id": "policy", "description": "No parking"},
        {"curb_policy_id": "historical", "description": None},
    ]
    if fault == "missing_description":
        policies[0]["description"] = None
    elif fault == "wrong_link":
        zones[0]["curb_policy_ids"] = ["historical"]
    elif fault == "duplicate":
        zones.append(zones[0].copy())

    def get(url, **kwargs: object) -> SimpleNamespace:
        endpoint = url.rsplit("/", 1)[-1]
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {
                "data": {endpoint: zones if endpoint == "zones" else policies}
            },
        )

    monkeypatch.setattr(publication.requests, "get", get)
    expected = {
        "api_expected": {
            "zones": {"zone": ["policy"]},
            "policies": {"policy": "No parking"},
        }
    }
    if fault:
        with pytest.raises(ValueError):
            publication.verify_api(tmp_path, expected)
    else:
        result = publication.verify_api(tmp_path, expected)
        assert result["policies"]["active_count"] == 1
        assert result["zones"]["count"] == 1


@pytest.mark.parametrize("missing_zone", [False, True])
def test_update_validation_matches_uuid_objects_to_database_strings(
    missing_zone,
) -> None:
    zone, policy = uuid4(), uuid4()
    zones = gpd.GeoDataFrame(
        {"curb_zone_id": [zone], "end_date": [None]},
        geometry=[LineString([(-71.06, 42.35), (-71.061, 42.35)])],
        crs="EPSG:4326",
    )
    columns = ["curb_zone_id", "curb_policy_id"]
    data = {
        "curb_zones": {"table": zones, "keys": ["curb_zone_id"]},
        "curb_policies": {
            "table": pd.DataFrame(
                {"curb_policy_id": [policy], "description": ["No parking"]}
            ),
            "keys": ["curb_policy_id"],
        },
        "curb_zone_policies": {"table": pd.DataFrame(columns=columns), "keys": columns},
        "curb_zone_policies_delete": {
            "table": pd.DataFrame(columns=columns),
            "keys": columns,
        },
    }
    old_links = pd.DataFrame(
        [[str(uuid4() if missing_zone else zone), str(policy)]], columns=columns
    )
    if missing_zone:
        with pytest.raises(ValueError, match="inactive or missing zones"):
            publication.validate_update(data, old_links)
    else:
        result = publication.validate_update(data, old_links)
        assert result["api_expected"]["zones"] == {str(zone): [str(policy)]}
        # The same relationship may be deleted and replaced as UUID objects.
        replacement = pd.DataFrame([[zone, policy]], columns=columns)
        data["curb_zone_policies"]["table"] = replacement
        data["curb_zone_policies_delete"]["table"] = replacement
        assert publication.validate_update(data, old_links)["zone_policy_links"] == 1
