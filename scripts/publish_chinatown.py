"""Prepare, inspect, publish, and verify the Chinatown API update in distinct steps."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import psycopg2
import requests
import yaml
from api_updater.config import ApiUpdaterConfig
from api_updater.core import prepare_api_update
from api_updater.descriptions import (
    INSTRUCTION_PATH,
    PROMPT_PATH,
    is_missing_description,
)
from api_updater.exporter import export_to_db
from api_updater.extractor import read_db_tables
from api_updater.transformer import fill_missing_policy_descriptions
from api_updater.utils import get_policy_json
from dotenv import load_dotenv
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://smart-curb-api-dev-cln5x3g7hq-uk.a.run.app"
KEYS = {
    "curb_zones": ["curb_zone_id"],
    "curb_policies": ["curb_policy_id"],
    "curb_zone_policies": ["curb_zone_id", "curb_policy_id"],
    "curb_policy_rules": ["rule_id"],
    "curb_policy_time_spans": ["time_span_id"],
    "curb_policy_rates": ["rate_id"],
}


def read_database() -> tuple[dict, pd.DataFrame]:
    """Fingerprint published tables and read existing zone-policy associations."""
    fingerprints = {}
    with psycopg2.connect(
        dbname="cds",
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=10,
    ) as connection:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with connection.cursor() as cur:
            for table, keys in KEYS.items():
                cur.execute(
                    sql.SQL(
                        "SELECT count(*), md5(COALESCE("
                        "jsonb_agg(to_jsonb(t) ORDER BY {})::text, '[]')) "
                        "FROM chinatown_cds.{} t"
                    ).format(
                        sql.SQL(", ").join(sql.Identifier(k) for k in keys),
                        sql.Identifier(table),
                    )
                )
                count, fingerprint = cur.fetchone()
                fingerprints[table] = {"count": count, "fingerprint": fingerprint}
            cur.execute(
                "SELECT curb_zone_id, curb_policy_id "
                "FROM chinatown_cds.curb_zone_policies"
            )
            links = pd.DataFrame(
                cur.fetchall(), columns=["curb_zone_id", "curb_policy_id"]
            )
    return fingerprints, links


def validate_update(data: dict, old_links: pd.DataFrame) -> dict:
    """Validate the full resulting publication, including retained associations."""
    for name, item in data.items():
        frame = item["table"]
        if (
            frame[item["keys"]].isna().any().any()
            or frame.duplicated(item["keys"]).any()
        ):
            raise ValueError(f"Null or duplicate publication keys in {name}")
    zones = data["curb_zones"]["table"]
    policies = data["curb_policies"]["table"]
    active = zones[zones["end_date"].isna()]
    if active.empty or policies.empty:
        raise ValueError("Refusing to publish empty Chinatown output")
    if (
        not active.geometry.is_valid.all()
        or not active.geom_type.eq("LineString").all()
    ):
        raise ValueError("Published zones must have valid LineString geometries")
    removed = data["curb_zone_policies_delete"]["table"]
    columns = ["curb_zone_id", "curb_policy_id"]
    # psycopg2 returns UUID strings here; SmartCurbDB returns UUID objects.
    # Compare canonical values across both readers without changing export types.
    retained = (
        old_links[columns]
        .astype(str)
        .merge(removed[columns].astype(str), on=columns, how="left", indicator=True)
    )
    retained = retained[retained["_merge"] == "left_only"].drop(columns="_merge")
    final_links = pd.concat(
        [retained, data["curb_zone_policies"]["table"][columns].astype(str)],
        ignore_index=True,
    )
    if final_links.duplicated(columns).any():
        raise ValueError("Resulting zone-policy associations contain duplicate keys")
    if not final_links["curb_zone_id"].isin(active["curb_zone_id"].astype(str)).all():
        raise ValueError("Resulting associations reference inactive or missing zones")
    if (
        not final_links["curb_policy_id"]
        .isin(policies["curb_policy_id"].astype(str))
        .all()
    ):
        raise ValueError("Resulting associations reference missing policies")
    if policies["description"].map(is_missing_description).any():
        raise ValueError("Active policies still have missing descriptions")
    return {
        "active_zones": len(active),
        "retired_zones": len(zones) - len(active),
        "active_policies": len(policies),
        "zone_policy_links": len(final_links),
        "missing_descriptions": 0,
        "table_rows": {name: len(item["table"]) for name, item in data.items()},
        "api_expected": expected_api(active, policies, final_links),
    }


def expected_api(
    zones: pd.DataFrame, policies: pd.DataFrame, links: pd.DataFrame
) -> dict:
    """Record the exact active identities, associations and reviewed descriptions."""
    grouped = (
        links.astype(str)
        .groupby("curb_zone_id")["curb_policy_id"]
        .apply(list)
        .to_dict()
    )
    return {
        "zones": {
            str(key): sorted(grouped.get(str(key), [])) for key in zones["curb_zone_id"]
        },
        "policies": {
            str(row.curb_policy_id): row.description for row in policies.itertuples()
        },
    }


def prepare_descriptions(config: ApiUpdaterConfig) -> tuple[dict, pd.DataFrame, dict]:
    """Backfill published active policies independently of the pending photo run."""
    tables = read_db_tables(
        "cds",
        "chinatown_cds",
        {
            table: "end_date IS NULL" if table == "curb_zones" else None
            for table in KEYS
        },
    )
    zones = tables["curb_zones"]
    links = tables["curb_zone_policies"]
    links = links[links["curb_zone_id"].isin(zones["curb_zone_id"])]
    policies = tables["curb_policies"]
    policies = policies[policies["curb_policy_id"].isin(links["curb_policy_id"])].copy()
    policies["policy_json"] = get_policy_json(
        policies,
        tables["curb_policy_rules"],
        tables["curb_policy_time_spans"],
        tables["curb_policy_rates"],
    )
    missing_count = int(policies["description"].map(is_missing_description).sum())
    preview = fill_missing_policy_descriptions(
        policies,
        config.gemini_description_settings,
        config.gemini_concurrent_limit,
    )
    data = {
        "curb_policies": {
            "table": preview.drop(columns="policy_json"),
            "keys": ["curb_policy_id"],
        }
    }
    summary = {
        "active_zones": len(zones),
        "active_policies": len(preview),
        "descriptions_generated": missing_count,
        "missing_descriptions": 0,
        "api_expected": expected_api(zones, preview, links),
    }
    return data, preview, summary


def verify_api(run_dir: Path, expected: dict) -> dict:
    """Confirm the deployed API serves the completed Chinatown publication."""
    results = {}
    for endpoint, id_column in (
        ("zones", "curb_zone_id"),
        ("policies", "curb_policy_id"),
    ):
        response = requests.get(
            f"{API_URL}/curbs/{endpoint}",
            params={"schema": "chinatown_cds"},
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        (run_dir / f"api_{endpoint}_after.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        rows = payload["data"][endpoint]
        ids = {row[id_column] for row in rows}
        if len(ids) != len(rows):
            raise ValueError(f"API {endpoint} contains duplicate IDs")
        desired = expected["api_expected"][endpoint]
        if endpoint == "zones":
            actual = {
                row[id_column]: sorted(row["curb_policy_ids"])
                for row in rows
                if row.get("end_date") is None
            }
            if actual != desired:
                raise ValueError(
                    "API active zones or policy associations differ from review"
                )
        else:
            actual = {
                row[id_column]: row.get("description")
                for row in rows
                if row[id_column] in desired
            }
            if actual != desired or any(
                is_missing_description(d) for d in actual.values()
            ):
                raise ValueError("API active policy descriptions differ from review")
        results[endpoint] = {
            "count": len(rows),
            "active_count": len(actual),
            "http_status": response.status_code,
        }
    return results


def main() -> None:
    """Prepare a review artifact or publish that exact local artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "publish", "verify"])
    parser.add_argument(
        "--run-dir", type=Path, default=ROOT / "output/chinatown_run_20260923"
    )
    parser.add_argument(
        "--descriptions-only",
        action="store_true",
        help="Backfill existing published policies while a refresh is pending",
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    run_dir = args.run_dir.resolve()
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    kind = "description_backfill" if args.descriptions_only else "publication"
    artifact = run_dir / f"{kind}_prepared.pkl"
    review_path = run_dir / f"{kind}_review.json"
    if args.action == "prepare":
        config = ApiUpdaterConfig(
            **yaml.safe_load((ROOT / "configs/chinatown/api_updater.yaml").read_text())
        )
        if (
            config.api_db_schema != "chinatown_cds"
            or config.staging_db_schema != "chinatown_cds"
        ):
            raise ValueError("This publication is restricted to chinatown_cds")
        baseline, old_links = read_database()
        if args.descriptions_only:
            data, policy_preview, summary = prepare_descriptions(config)
        else:
            data = prepare_api_update(config)
            summary = validate_update(data, old_links)
            policy_preview = data["curb_policies"]["table"].copy()
            policy_preview["policy_json"] = get_policy_json(
                policy_preview,
                data["curb_policy_rules"]["table"],
                data["curb_policy_time_spans"]["table"],
                data["curb_policy_rates"]["table"],
            )
        policy_preview.to_csv(run_dir / f"{kind}_descriptions_review.csv", index=False)
        for name, item in data.items():
            item["table"].to_csv(run_dir / f"{kind}_preview_{name}.csv", index=False)
        # Internal, locally generated artifact preserves UUIDs, timestamps and
        # geometry exactly. Publication checks its recorded hash before loading.
        artifact.write_bytes(pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL))
        review = {
            "prepared_at_utc": datetime.now(UTC).isoformat(),
            "summary": summary,
            "baseline": baseline,
            "config": config.model_dump(mode="json"),
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "prompt_sha256": hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest(),
            "instruction_sha256": hashlib.sha256(
                INSTRUCTION_PATH.read_bytes()
            ).hexdigest(),
        }
        review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {k: v for k, v in summary.items() if k != "api_expected"}, indent=2
            )
        )
        return
    review = json.loads(review_path.read_text())
    if args.action == "publish":
        if kind in manifest:
            raise ValueError("This reviewed update was already published")
        baseline, old_links = read_database()
        if baseline != review["baseline"]:
            raise ValueError(
                "Published database changed after preparation; regenerate the review"
            )
        if (
            hashlib.sha256(artifact.read_bytes()).hexdigest()
            != review["artifact_sha256"]
        ):
            raise ValueError("Prepared artifact changed after review")
        data = pickle.loads(artifact.read_bytes())
        if args.descriptions_only:
            if set(data) != {"curb_policies"}:
                raise ValueError("Description backfill may only write the policy table")
            if (
                data["curb_policies"]["table"]["description"]
                .map(is_missing_description)
                .any()
            ):
                raise ValueError("Description backfill is incomplete")
        else:
            validate_update(data, old_links)
        export_to_db("cds", data, "chinatown_cds")
        manifest[kind] = {
            "published_at_utc": datetime.now(UTC).isoformat(),
            "artifact_sha256": review["artifact_sha256"],
            **review["summary"],
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    results = verify_api(run_dir, review["summary"])
    manifest[f"{kind}_api_verification"] = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        **results,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
