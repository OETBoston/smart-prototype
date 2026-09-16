from __future__ import annotations

import sys
from pathlib import Path

import pytest

SIGN_LOADER_SRC = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "sign-loader"
    / "src"
    / "sign_loader"
)
sys.path.insert(0, str(SIGN_LOADER_SRC))

import survey123  # noqa: E402
from arcgis_client import ArcGISClient  # noqa: E402

PARENT_A = "11111111-1111-4111-8111-111111111111"
PARENT_B = "22222222-2222-4222-8222-222222222222"
SIGN_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SIGN_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _write_allowlist(repo_root: Path, rows: list[str]) -> dict:
    path = repo_root / "inputs" / "parents.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("GlobalID\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return {
        "parent_allowlist": {
            "csv_path": "inputs/parents.csv",
            "csv_column": "globalid",
        }
    }


def test_normalize_guid_accepts_braces_and_rejects_invalid() -> None:
    assert survey123._normalize_guid("{AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA}") == SIGN_A
    assert survey123._normalize_guid("not-a-guid") is None
    assert survey123._normalize_guid("") is None


def test_allowlist_parsing_normalizes_and_warns_on_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_allowlist(tmp_path, [f"{{{PARENT_A.upper()}}}", PARENT_A])
    warnings: list[tuple] = []
    monkeypatch.setattr(
        survey123.logger, "warning", lambda *args: warnings.append(args)
    )

    result = survey123._load_parent_allowlist(config, tmp_path)

    assert result == {PARENT_A}
    assert warnings and "duplicate UUID" in warnings[0][0]


def test_allowlist_rejects_invalid_and_empty_files(tmp_path: Path) -> None:
    config = _write_allowlist(tmp_path, ["bad-id"])
    with pytest.raises(ValueError, match="Invalid or empty UUID"):
        survey123._load_parent_allowlist(config, tmp_path)

    config = _write_allowlist(tmp_path, [])
    with pytest.raises(ValueError, match="contains no UUIDs"):
        survey123._load_parent_allowlist(config, tmp_path)


def test_feature_queries_use_post(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ArcGISClient("https://example.test/FeatureServer", token="token")
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(method: str, url: str, params=None, data=None) -> dict:
        calls.append((method, url, data))
        if data and data.get("returnCountOnly") == "true":
            return {"count": 2}
        return {"features": [], "exceededTransferLimit": False}

    monkeypatch.setattr(client, "_request", fake_request)

    client.query_layer(1, where="globalid IN ('a')")
    assert client.query_count(1, where="globalid IN ('a')") == 2
    assert [call[0] for call in calls] == ["POST", "POST"]
    assert all(call[2]["where"] == "globalid IN ('a')" for call in calls)


class _FakeClient:
    def __init__(
        self, parent_features: list[dict], repeat_features: list[dict]
    ) -> None:
        self.parent_features = parent_features
        self.repeat_features = repeat_features
        self.queries: list[tuple[int, str]] = []

    def layer_info(self, layer_id: int) -> dict:
        if layer_id == 0:
            return {
                "fields": [
                    {"name": "globalid", "type": "esriFieldTypeGlobalID"},
                    {"name": "objectid", "type": "esriFieldTypeOID"},
                ]
            }
        return {
            "fields": [
                {"name": "globalid", "type": "esriFieldTypeGlobalID"},
                {"name": "parentglobalid", "type": "esriFieldTypeGUID"},
                {"name": "sign_type", "type": "esriFieldTypeString"},
                {"name": "objectid", "type": "esriFieldTypeOID"},
            ]
        }

    def query_layer(self, layer_id: int, where: str, return_geometry: bool) -> dict:
        self.queries.append((layer_id, where))
        if layer_id == 0:
            return {
                "objectIdFieldName": "objectid",
                "features": self.parent_features,
            }
        return {
            "objectIdFieldName": "objectid",
            "globalIdFieldName": "globalid",
            "features": self.repeat_features,
        }


def _config(repo_root: Path, parent_ids: list[str]) -> tuple[dict, Path]:
    survey_config = _write_allowlist(repo_root, parent_ids)
    survey_config.update(
        {
            "service_url": "https://example.test/FeatureServer",
            "parent_layer_id": 0,
            "repeat_layer_id": 1,
            "where": "1=1",
            "repeat_where": "1=1",
            "exclude_sign_types": ["driveway"],
            "attachments": {"link_level": "repeat"},
            "image_storage": {
                "backend": "local",
                "local_dir": "inputs/test-images",
            },
            "field_map": {
                "sign_type": "sign_type",
                "added_date": "CreationDate",
                "repeat_parent_field": "parentglobalid",
            },
        }
    )
    return (
        {"survey123": survey_config, "output_crs": "EPSG:4326"},
        repo_root / "packages" / "sign-loader",
    )


def _parent(global_id: str, object_id: int, x: float = -71.05) -> dict:
    return {
        "attributes": {"globalid": global_id, "objectid": object_id},
        "geometry": {"x": x, "y": 42.35},
    }


def _repeat(global_id: str, parent_id: str, object_id: int, sign_type: str) -> dict:
    return {
        "attributes": {
            "globalid": global_id,
            "parentglobalid": parent_id,
            "objectid": object_id,
            "sign_type": sign_type,
            "CreationDate": 1_700_000_000_000,
        }
    }


def _patch_loader(monkeypatch: pytest.MonkeyPatch, fake_client: _FakeClient) -> None:
    monkeypatch.setattr(survey123, "_build_client", lambda _config: fake_client)
    monkeypatch.setattr(
        survey123,
        "_attach_images",
        lambda _client, signs, *_args: signs.__setitem__(
            "attachments", [[]] * len(signs)
        ),
    )


def test_parent_repeat_join_and_defensive_driveway_exclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client = _FakeClient(
        [_parent(PARENT_A, 1), _parent(PARENT_B, 2, -71.04)],
        [
            _repeat(SIGN_A, PARENT_A, 10, "metered"),
            # Returned despite the server filter to prove the local guard works.
            _repeat(SIGN_B, PARENT_B, 11, "DriveWay"),
        ],
    )
    _patch_loader(monkeypatch, fake_client)
    config, base_path = _config(tmp_path, [PARENT_A, PARENT_B])

    result = survey123.load_survey123(config, base_path)

    assert result["source_sign_id"].tolist() == [SIGN_A]
    assert result["source_location_id"].tolist() == [PARENT_A]
    assert "parentglobalid IN" in fake_client.queries[1][1]
    assert "sign_type NOT IN ('driveway')" in fake_client.queries[1][1]


def test_missing_allowlisted_parent_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client = _FakeClient([_parent(PARENT_A, 1)], [])
    _patch_loader(monkeypatch, fake_client)
    config, base_path = _config(tmp_path, [PARENT_A, PARENT_B])

    with pytest.raises(ValueError, match="do not exactly match"):
        survey123.load_survey123(config, base_path)


def test_empty_parent_result_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client = _FakeClient([], [])
    _patch_loader(monkeypatch, fake_client)
    config, base_path = _config(tmp_path, [PARENT_A])

    with pytest.raises(ValueError, match="No parent records"):
        survey123.load_survey123(config, base_path)


def test_empty_repeat_result_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client = _FakeClient([_parent(PARENT_A, 1)], [])
    _patch_loader(monkeypatch, fake_client)
    config, base_path = _config(tmp_path, [PARENT_A])

    with pytest.raises(ValueError, match="No sign records"):
        survey123.load_survey123(config, base_path)
