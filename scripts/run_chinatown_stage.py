"""Run one explicitly selected Chinatown processing stage and record its job ID."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg2
import yaml
from dotenv import load_dotenv
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs/chinatown"
TABLES = {
    "sign_loader": "asset_jobs",
    "curb_segmenter": "curb_segment_jobs",
    "sign_reader": "sign_reader_jobs",
    "policy_applier": "policy_handling_jobs",
}


def query(statement, params: tuple = ()) -> list:
    """Run a read-only query against the task database."""
    with psycopg2.connect(
        dbname="cds",
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=10,
    ) as connection:
        connection.set_session(readonly=True)
        with connection.cursor() as cur:
            cur.execute(statement, params)
            return cur.fetchall()


def job_ids(table: str, name: str) -> set[str]:
    """Find only jobs with the configured run-specific name."""
    rows = query(
        sql.SQL(
            "SELECT job_id::text FROM chinatown_cds.{} WHERE job_name LIKE %s"
        ).format(sql.Identifier(table)),
        (f"%{name}%",),
    )
    return {row[0] for row in rows}


def pin_config(step: str, field: str, job_id: str) -> None:
    """Pin one downstream input to the exact completed upstream job."""
    path = CONFIG_DIR / f"{step}.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["source_jobs"][field] = job_id
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def load_signs(config: dict, run_dir: Path) -> dict:
    """Download and reconcile all source signs before the append-only import."""
    sys.path.insert(0, str(ROOT / "packages/sign-loader/src/sign_loader"))
    from format_tables import format_sign_tbls
    from main import upload_sign_tbls
    from survey123 import load_survey123

    snapshot = json.loads((run_dir / "survey/survey_preflight.json").read_text())
    for name, digest in snapshot["sha256"].items():
        if (
            hashlib.sha256((run_dir / "survey" / name).read_bytes()).hexdigest()
            != digest
        ):
            raise ValueError(f"Frozen survey artifact changed: {name}")
    signs = load_survey123(config, ROOT / "packages/sign-loader")
    expected = set(json.loads((run_dir / "survey/expected_sign_ids.json").read_text()))
    actual = set(signs["source_sign_id"])
    if expected != actual or len(signs) != len(expected):
        raise ValueError(
            "Survey import does not exactly match the frozen source sign IDs"
        )
    attachments = signs["attachments"].map(len)
    missing_ids = set(signs.loc[attachments.eq(0), "source_sign_id"])
    missing_path = run_dir / "survey/missing_attachments.json"
    confirmed_missing = (
        {
            row["globalid"].strip("{}").lower()
            for row in json.loads(missing_path.read_text())
        }
        if missing_path.exists()
        else set()
    )
    if missing_ids != confirmed_missing:
        raise ValueError("Missing downloads differ from the verified source-photo gaps")
    tables = format_sign_tbls(signs, config)
    tables["signs"].loc[
        tables["signs"]["source_sign_id"].isin(missing_ids), "sign_notes"
    ] = "Survey123 record has no attachment; policy requires review"
    upload_sign_tbls(tables, config["dbname"], config["schema"], debug_mode=False)
    return {
        "source_ids_exact_match": True,
        "signs": len(signs),
        "locations": len(tables["asset_locations"]),
        "images": int(attachments.sum()),
        "missing_attachments": len(missing_ids),
        "missing_attachment_source_ids": sorted(missing_ids),
    }


def main() -> None:
    """Execute one stage and persist its exact lineage for the next stage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=TABLES)
    parser.add_argument(
        "--run-dir", type=Path, default=ROOT / "output/chinatown_run_20260923"
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    run_dir = args.run_dir.resolve()
    migration = json.loads((run_dir / "api_migration.json").read_text())
    if migration["status"] != "committed" or not migration["api_content_unchanged"]:
        raise ValueError(
            "Published API views must be isolated from new staging jobs first"
        )
    manifest_path = run_dir / "run_manifest.json"
    manifest = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists()
        else {
            "project": "smart-grant-460018",
            "instance": "dev",
            "database": "cds",
            "schema": "chinatown_cds",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "survey_preflight": json.loads(
                (run_dir / "survey/survey_preflight.json").read_text()
            ),
            "backup": json.loads((run_dir / "backup.json").read_text()),
            "stages": {},
        }
    )
    if args.stage in manifest["stages"]:
        raise ValueError(
            "This stage already completed; inspect the manifest before repeating"
        )
    config = yaml.safe_load((CONFIG_DIR / f"{args.stage}.yaml").read_text())
    if config.get("db_schema", config.get("schema")) != "chinatown_cds":
        raise ValueError("Only chinatown_cds is supported by this run script")
    if args.stage != "sign_loader" and any(
        value in (None, "auto") for value in config["source_jobs"].values()
    ):
        raise ValueError("Every source job must be pinned before this stage runs")
    before = job_ids(TABLES[args.stage], config["job_name"])
    if before:
        raise ValueError(
            "An unrecorded job already exists for this stage name; inspect its "
            "partial output before choosing a new run name and reprocessing"
        )
    started = datetime.now(UTC).isoformat()
    metrics = {}
    if args.stage == "sign_loader":
        metrics = load_signs(config, run_dir)
    else:
        module = importlib.import_module(args.stage)
        config_class = getattr(
            module,
            {
                "curb_segmenter": "CurbSegmenterConfig",
                "sign_reader": "SignReaderConfig",
                "policy_applier": "PolicyApplierConfig",
            }[args.stage],
        )
        getattr(module, args.stage)(config_class(**config))
    created = job_ids(TABLES[args.stage], config["job_name"]) - before
    if len(created) != 1:
        raise ValueError(f"Expected exactly one new {args.stage} job; found {created}")
    job_id = created.pop()
    if args.stage == "sign_reader":
        # Keep source-photo gaps visible using the reader's existing unusable
        # policy, rather than inventing restrictions from a sign-type label.
        from uuid import UUID, uuid4

        from sign_reader.db_connector import append_sign_policies
        from sign_reader.unusable import unusable_image

        missing_rows = query(
            "SELECT s.sign_id FROM chinatown_cds.signs s "
            "WHERE s.job_id=%s AND NOT EXISTS ("
            "SELECT 1 FROM chinatown_cds.images i WHERE i.sign_id=s.sign_id)",
            (config["source_jobs"]["parking_sign"],),
        )
        if missing_rows:
            policy = unusable_image().signs[0].policy.model_dump_json()
            append_sign_policies(
                "chinatown_cds",
                [
                    {
                        "sign_policy_id": uuid4(),
                        "sign_id": row[0],
                        "policy_json": policy,
                        "policy_arrow": None,
                    }
                    for row in missing_rows
                ],
                UUID(job_id),
            )
        metrics["missing_photo_unusable_policies"] = len(missing_rows)
    manifest["stages"][args.stage] = {
        "job_id": job_id,
        "started_at_utc": started,
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "config": config,
        "metrics": metrics,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    updates = {
        "sign_loader": [
            ("curb_segmenter", "parking_sign"),
            ("sign_reader", "parking_sign"),
        ],
        "curb_segmenter": [
            ("policy_applier", "curb_segmenter"),
            ("api_updater", "curb_segmenter"),
        ],
        "sign_reader": [("policy_applier", "sign_reader")],
        "policy_applier": [("api_updater", "policy_handler")],
    }
    for step, field in updates[args.stage]:
        pin_config(step, field, job_id)
    print(json.dumps({"stage": args.stage, "job_id": job_id, **metrics}, indent=2))


if __name__ == "__main__":
    main()
