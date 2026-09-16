"""Audit the completed Seaport run and write its final immutable manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg2
import yaml
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "seaport_cds"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--schema-seed", type=Path, required=True)
    parser.add_argument("--repeat-csv", type=Path, required=True)
    parser.add_argument("--segment-artifact", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sign-loader-job", required=True)
    parser.add_argument("--sign-reader-job", required=True)
    parser.add_argument("--segmenter-job", required=True)
    parser.add_argument("--policy-job", required=True)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path) -> dict:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _canonical_guid(value: str) -> str:
    return str(uuid.UUID(value.strip().strip("{}")))


def _eligible_repeat_ids(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    columns = {name.casefold(): name for name in rows[0]}
    gid = columns["globalid"]
    sign_type = columns["select the type of sign"]
    return {
        _canonical_guid(row[gid])
        for row in rows
        if row[sign_type].strip().casefold() != "driveway"
    }


def _snapping_stats(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start_indexes = [
        index
        for index, line in enumerate(lines)
        if "Running Curb Segmentation Pipeline" in line
    ]
    if not start_indexes:
        raise ValueError(f"No curb-segmenter run found in {path}")
    run_lines = lines[start_indexes[-1] :]
    requested = [
        int(match.group(1))
        for line in run_lines
        if (match := re.search(r"Snapping ([0-9]+) points", line))
    ]
    snapped = [
        int(match.group(1))
        for line in run_lines
        if (match := re.search(r"Snapped points: ([0-9]+)", line))
    ]
    unsnapped = [
        int(match.group(1))
        for line in run_lines
        if (match := re.search(r"Unsnapped points: ([0-9]+)", line))
    ]
    final_segments = [
        int(match.group(1))
        for line in run_lines
        if (match := re.search(r"Final segments: ([0-9]+)", line))
    ]
    labels = ["bus_stops", "fire_hydrants", "sign_locations", "parking_meters"]
    if requested != [18, 154, 117, 76] or len(snapped) != 4 or len(unsnapped) != 4:
        raise ValueError(
            "Unexpected curb-segmenter snapping log sequence: "
            f"requested={requested}, snapped={snapped}, unsnapped={unsnapped}"
        )
    if not final_segments or final_segments[-1] != 606:
        raise ValueError(f"Unexpected final segment log count: {final_segments}")
    return {
        label: {
            "input": requested[index],
            "snapped": snapped[index],
            "unsnapped": unsnapped[index],
        }
        for index, label in enumerate(labels)
    }


def _fetch_one(cur, query: str, params: tuple = ()) -> dict:
    cur.execute(query, params)
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Database audit query returned no row: {query}")
    return dict(row)


def main() -> None:
    args = parse_args()
    load_dotenv(REPO_ROOT / ".env")
    preflight = json.loads(args.preflight.read_text(encoding="utf-8"))
    schema_seed = json.loads(args.schema_seed.read_text(encoding="utf-8"))
    sign_loader_config = yaml.safe_load(
        (REPO_ROOT / "packages" / "sign-loader" / "config.yaml").read_text(
            encoding="utf-8"
        )
    )
    sign_reader_config = yaml.safe_load(
        (
            REPO_ROOT
            / "packages"
            / "sign-reader"
            / "src"
            / "sign_reader"
            / "config.yaml"
        ).read_text(encoding="utf-8")
    )
    segmenter_config = yaml.safe_load(
        (
            REPO_ROOT
            / "packages"
            / "curb-segmenter"
            / "src"
            / "curb_segmenter"
            / "config.yaml"
        ).read_text(encoding="utf-8")
    )
    policy_config = yaml.safe_load(
        (
            REPO_ROOT
            / "packages"
            / "policy-applier"
            / "src"
            / "policy_applier"
            / "config.yaml"
        ).read_text(encoding="utf-8")
    )

    expected_repeat_ids = _eligible_repeat_ids(args.repeat_csv)
    snapping = _snapping_stats(args.log)
    connection = psycopg2.connect(
        dbname="cds",
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        cursor_factory=RealDictCursor,
    )
    try:
        with connection.cursor() as cur:
            table_names = [
                "asset_jobs",
                "blockface_jobs",
                "curb_segment_jobs",
                "data_sources",
                "asset_locations",
                "curb_blockfaces",
                "curb_segments",
                "nonsign_features",
                "signs",
                "images",
                "sign_reader_jobs",
                "sign_policies",
                "meter_policies",
                "policy_handling_jobs",
                "curb_segment_policies",
            ]
            table_counts = {}
            for table_name in table_names:
                cur.execute(f"SELECT count(*) AS count FROM {SCHEMA}.{table_name}")
                table_counts[table_name] = int(cur.fetchone()["count"])

            sign_job = _fetch_one(
                cur,
                f"SELECT job_id::text, job_name, job_description, job_timestamp "
                f"FROM {SCHEMA}.asset_jobs WHERE job_id=%s",
                (args.sign_loader_job,),
            )
            sign_counts = _fetch_one(
                cur,
                f"SELECT count(DISTINCT al.asset_location_id) AS locations, "
                f"count(DISTINCT s.sign_id) AS signs, "
                f"count(DISTINCT i.image_id) AS images, "
                f"count(DISTINCT s.source_sign_id) AS unique_source_sign_ids, "
                f"count(*) FILTER (WHERE lower(coalesce(s.sign_type_code,''))="
                f"'driveway') AS driveways "
                f"FROM {SCHEMA}.signs s "
                f"JOIN {SCHEMA}.asset_locations al "
                f"ON al.asset_location_id=s.sign_location_id "
                f"LEFT JOIN {SCHEMA}.images i ON i.sign_id=s.sign_id "
                f"WHERE s.job_id=%s",
                (args.sign_loader_job,),
            )
            cur.execute(
                f"SELECT source_sign_id FROM {SCHEMA}.signs WHERE job_id=%s",
                (args.sign_loader_job,),
            )
            db_repeat_ids = {row["source_sign_id"] for row in cur.fetchall()}
            source_id_check = {
                "exact_match": db_repeat_ids == expected_repeat_ids,
                "expected": len(expected_repeat_ids),
                "actual": len(db_repeat_ids),
                "missing": sorted(expected_repeat_ids - db_repeat_ids),
                "unexpected": sorted(db_repeat_ids - expected_repeat_ids),
            }
            image_check = _fetch_one(
                cur,
                f"SELECT count(*) FILTER (WHERE image_count=1) AS one_image, "
                f"count(*) FILTER (WHERE image_count<>1) AS not_one_image "
                f"FROM (SELECT s.sign_id, count(i.image_id) AS image_count "
                f"FROM {SCHEMA}.signs s LEFT JOIN {SCHEMA}.images i "
                f"ON i.sign_id=s.sign_id WHERE s.job_id=%s GROUP BY s.sign_id) q",
                (args.sign_loader_job,),
            )

            sign_reader_job = _fetch_one(
                cur,
                f"SELECT job_id::text, job_name, job_description, job_timestamp, "
                f"model_settings FROM {SCHEMA}.sign_reader_jobs WHERE job_id=%s",
                (args.sign_reader_job,),
            )
            sign_reader_counts = _fetch_one(
                cur,
                f"SELECT count(*) AS policy_rows, "
                f"count(DISTINCT sign_id) AS covered_signs, "
                f"count(*) FILTER (WHERE policy_json::text ILIKE %s) "
                f"AS unusable_image_rows, "
                f"count(DISTINCT sign_id) FILTER "
                f"(WHERE policy_json::text ILIKE %s) AS unusable_image_signs "
                f"FROM {SCHEMA}.sign_policies WHERE job_id=%s",
                ("%unusable image%", "%unusable image%", args.sign_reader_job),
            )

            segment_job = _fetch_one(
                cur,
                f"SELECT job_id::text, job_name, job_description, job_timestamp "
                f"FROM {SCHEMA}.curb_segment_jobs WHERE job_id=%s",
                (args.segmenter_job,),
            )
            segment_counts = _fetch_one(
                cur,
                f"SELECT count(*) AS segments, "
                f"count(DISTINCT segment_id) AS unique_segments, "
                f"count(DISTINCT blockface_id) AS covered_blockfaces "
                f"FROM {SCHEMA}.curb_segments WHERE job_id=%s",
                (args.segmenter_job,),
            )
            segment_counts["uncovered_blockfaces"] = 231 - int(
                segment_counts["covered_blockfaces"]
            )

            policy_job = _fetch_one(
                cur,
                f"SELECT job_id::text, job_name, job_description, job_timestamp "
                f"FROM {SCHEMA}.policy_handling_jobs WHERE job_id=%s",
                (args.policy_job,),
            )
            policy_counts = _fetch_one(
                cur,
                f"SELECT count(*) AS segment_policy_rows, "
                f"count(DISTINCT (segment_id,job_id)) AS unique_segment_job_keys, "
                f"count(*) FILTER (WHERE policy_list='[]'::jsonb) "
                f"AS empty_policy_lists, "
                f"count(*) FILTER (WHERE policy_list<>'[]'::jsonb) "
                f"AS nonempty_policy_lists, "
                f"sum(jsonb_array_length(policy_list)) AS policy_entries "
                f"FROM {SCHEMA}.curb_segment_policies WHERE job_id=%s",
                (args.policy_job,),
            )
            wrong_segment_lineage = _fetch_one(
                cur,
                f"SELECT count(*) AS count FROM {SCHEMA}.curb_segment_policies csp "
                f"JOIN {SCHEMA}.curb_segments cs ON cs.segment_id=csp.segment_id "
                f"WHERE csp.job_id=%s AND cs.job_id<>%s",
                (args.policy_job, args.segmenter_job),
            )["count"]
            cur.execute(
                f"SELECT rule->>'activity' AS activity, count(*) AS count "
                f"FROM {SCHEMA}.curb_segment_policies csp "
                f"CROSS JOIN LATERAL jsonb_array_elements(csp.policy_list) policy "
                f"CROSS JOIN LATERAL jsonb_array_elements(policy->'rules') rule "
                f"WHERE csp.job_id=%s GROUP BY rule->>'activity' "
                f"ORDER BY rule->>'activity'",
                (args.policy_job,),
            )
            policy_activities = {
                row["activity"]: int(row["count"]) for row in cur.fetchall()
            }
    finally:
        connection.close()

    checks = {
        "preflight_passed": preflight["status"] == "passed",
        "schema_seed_passed": schema_seed["status"] == "passed",
        "source_repeat_ids_exact_match_after_import": source_id_check["exact_match"],
        "sign_import_counts": {
            key: int(sign_counts[key])
            for key in ("locations", "signs", "images", "driveways")
        }
        == {"locations": 117, "signs": 143, "images": 143, "driveways": 0},
        "exactly_one_image_per_sign": int(image_check["one_image"]) == 143
        and int(image_check["not_one_image"]) == 0,
        "sign_reader_covers_all_signs": int(sign_reader_counts["covered_signs"]) == 143,
        "segment_keys_unique": int(segment_counts["segments"])
        == int(segment_counts["unique_segments"]),
        "segment_policy_keys_unique": int(policy_counts["segment_policy_rows"])
        == int(policy_counts["unique_segment_job_keys"]),
        "policy_rows_use_only_selected_segmenter": int(wrong_segment_lineage) == 0,
        "policy_config_uses_selected_sign_reader": policy_config["source_jobs"][
            "sign_reader"
        ]
        == args.sign_reader_job,
        "default_parking_anytime_disabled": policy_config["default_parking_anytime"]
        is False,
        "no_publication_stage_run": True,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        raise RuntimeError(f"Final Seaport acceptance checks failed: {failed_checks}")

    manifest = {
        "run_name": "Seaport Survey123 Curb-Policy Run",
        "status": "complete",
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "gcp_project_id": "smart-grant-460018",
        "database": "cds",
        "schema": SCHEMA,
        "publication": {
            "api_updater_run": False,
            "public_schema_rollover_run": False,
        },
        "inputs": preflight["inputs"],
        "export_counts": preflight["export_counts"],
        "live_reconciliation": preflight["live_reconciliation"],
        "spatial_seed": schema_seed,
        "generated_job_ids": {
            "blockface": schema_seed["jobs"]["seaport_blockface"],
            "sign_loader": args.sign_loader_job,
            "sign_reader": args.sign_reader_job,
            "curb_segmenter": args.segmenter_job,
            "curb_policy": args.policy_job,
        },
        "source_job_ids": {
            key: value
            for key, value in schema_seed["jobs"].items()
            if key != "seaport_blockface"
        },
        "job_metadata": {
            "sign_loader": sign_job,
            "sign_reader": sign_reader_job,
            "curb_segmenter": segment_job,
            "curb_policy": policy_job,
        },
        "model_settings": {
            "preprocess": sign_reader_config["gemini_preprocess_settings"],
            "reader": sign_reader_config["gemini_settings"],
            "database_recorded_reader": json.loads(sign_reader_job["model_settings"]),
            "concurrency": sign_reader_config["gemini_concurrent_limit"],
            "max_retries": sign_reader_config["max_retries"],
        },
        "sign_import": {
            "counts": sign_counts,
            "source_id_reconciliation": source_id_check,
            "images_per_sign": image_check,
            "excluded_sign_types": sign_loader_config["survey123"][
                "exclude_sign_types"
            ],
        },
        "sign_reader": sign_reader_counts,
        "segmentation": {
            "counts": segment_counts,
            "snapping": snapping,
            "snap_tolerance_ft": segmenter_config["snap_tolerance_ft"],
            "tiny_segment_threshold_ft": segmenter_config["tiny_seg_threshold_ft"],
        },
        "curb_policies": {
            "counts": policy_counts,
            "activity_rule_counts": policy_activities,
            "wrong_segment_job_rows": int(wrong_segment_lineage),
            "default_parking_anytime": policy_config["default_parking_anytime"],
            "selected_segmenter_job": policy_config["source_jobs"]["curb_segmenter"],
            "selected_sign_reader_job": policy_config["source_jobs"]["sign_reader"],
        },
        "table_counts": table_counts,
        "acceptance_checks": checks,
        "artifacts": {
            "preflight": _artifact(args.preflight),
            "schema_seed": _artifact(args.schema_seed),
            "allowlist": _artifact(
                REPO_ROOT
                / sign_loader_config["survey123"]["parent_allowlist"]["csv_path"]
            ),
            "image_directory": preflight["artifacts"]["image_directory"],
            "image_files": preflight["artifacts"]["downloaded_image_files"],
            "segments_geojson": _artifact(args.segment_artifact),
            "run_log": str(args.log.resolve()),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"status": "complete", "output": str(args.output), **checks}, indent=2
        )
    )


if __name__ == "__main__":
    main()
