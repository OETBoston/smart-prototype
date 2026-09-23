"""Create and spatially seed the isolated Seaport CDS schema transactionally."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCHEMA = "staging_next"
TARGET_SCHEMA = "seaport_cds"
EXPANSION_DEGREES = 0.003

SOURCE_JOBS = {
    "blockface": "c9eb0c6f-5475-4f8e-8cac-8289f4c85265",
    "fire_hydrant": "e9e630af-2e20-4221-873a-890bb3477646",
    "bus_stop": "223c3644-f0cd-4d28-877b-8ffa056cc2fe",
    "parking_meters": "65fe0581-a94c-4d00-afb0-a12460ee898d",
}
EXPECTED_COUNTS = {
    "blockfaces": 231,
    "fire_hydrant_locations": 154,
    "bus_stop_locations": 18,
    "parking_meter_policies": 42,
    "parking_meter_locations": 76,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--ddl",
        type=Path,
        default=REPO_ROOT / "sql_schema" / "00_create_staging.sql",
    )
    parser.add_argument("--project-id", default="smart-grant-460018")
    return parser.parse_args()


def _bbox(path: Path) -> dict[str, float]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 128:
        raise ValueError(f"Expected 128 Seaport parent rows, got {len(rows)}")
    xs = [float(row["x"]) for row in rows]
    ys = [float(row["y"]) for row in rows]
    raw = {
        "xmin": min(xs),
        "ymin": min(ys),
        "xmax": max(xs),
        "ymax": max(ys),
    }
    return {
        **{f"raw_{key}": value for key, value in raw.items()},
        "xmin": raw["xmin"] - EXPANSION_DEGREES,
        "ymin": raw["ymin"] - EXPANSION_DEGREES,
        "xmax": raw["xmax"] + EXPANSION_DEGREES,
        "ymax": raw["ymax"] + EXPANSION_DEGREES,
    }


def _safe_ddl(path: Path) -> str:
    ddl = path.read_text(encoding="utf-8-sig")
    ddl = re.sub(
        r"DROP\s+SCHEMA\s+IF\s+EXISTS\s+staging_next\s+CASCADE\s*;",
        "",
        ddl,
        flags=re.IGNORECASE,
    )
    ddl = re.sub(r"\bstaging_next\b", TARGET_SCHEMA, ddl)
    if re.search(r"\bDROP\s+SCHEMA\b", ddl, flags=re.IGNORECASE):
        raise ValueError("Refusing to execute schema DDL containing DROP SCHEMA")
    return ddl


def _count(cur, query: sql.Composed, params: tuple = ()) -> int:
    cur.execute(query, params)
    return int(cur.fetchone()[0])


def main() -> None:
    args = parse_args()
    load_dotenv(REPO_ROOT / ".env")
    bbox = _bbox(args.parent_csv)
    ddl = _safe_ddl(args.ddl)
    blockface_job_id = str(uuid.uuid4())

    connection = psycopg2.connect(
        dbname=os.getenv("DB_NAME", "cds"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
    )
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)",
                (TARGET_SCHEMA,),
            )
            if cur.fetchone()[0]:
                raise RuntimeError(
                    f"Schema {TARGET_SCHEMA!r} already exists; refusing to "
                    "overwrite it."
                )

            cur.execute(ddl)
            target = sql.Identifier(TARGET_SCHEMA)
            source = sql.Identifier(SOURCE_SCHEMA)
            envelope_params = (
                bbox["xmin"],
                bbox["ymin"],
                bbox["xmax"],
                bbox["ymax"],
            )

            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.blockface_jobs "
                    "(job_id, job_name, job_description) VALUES (%s, %s, %s)"
                ).format(target),
                (
                    blockface_job_id,
                    "seaport-blockfaces",
                    "Seaport spatial subset from staging_next blockface job "
                    + SOURCE_JOBS["blockface"],
                ),
            )
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.curb_blockfaces "
                    "(blockface_id, job_id, geography, is_left_side_oneway) "
                    "SELECT blockface_id, %s, geography, is_left_side_oneway "
                    "FROM {}.curb_blockfaces "
                    "WHERE job_id = %s AND ST_Intersects("
                    "geography, ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
                ).format(target, source),
                (blockface_job_id, SOURCE_JOBS["blockface"], *envelope_params),
            )

            selected_asset_jobs = [
                SOURCE_JOBS["fire_hydrant"],
                SOURCE_JOBS["bus_stop"],
                SOURCE_JOBS["parking_meters"],
            ]
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.asset_jobs SELECT * FROM {}.asset_jobs "
                    "WHERE job_id = ANY(%s::uuid[])"
                ).format(target, source),
                (selected_asset_jobs,),
            )

            cur.execute(
                sql.SQL(
                    "CREATE TEMP TABLE seaport_selected_meter_policies "
                    "ON COMMIT DROP AS "
                    "SELECT mp.* FROM {}.meter_policies mp "
                    "JOIN {}.asset_locations s "
                    "ON s.asset_location_id = mp.start_asset_location_id "
                    "JOIN {}.asset_locations e "
                    "ON e.asset_location_id = mp.end_asset_location_id "
                    "WHERE mp.job_id = %s AND ("
                    "ST_Intersects(s.location, ST_MakeEnvelope(%s, %s, %s, %s, 4326)) "
                    "OR ST_Intersects(e.location, "
                    "ST_MakeEnvelope(%s, %s, %s, %s, 4326)))"
                ).format(source, source, source),
                (
                    SOURCE_JOBS["parking_meters"],
                    *envelope_params,
                    *envelope_params,
                ),
            )
            cur.execute(
                sql.SQL(
                    "CREATE TEMP TABLE seaport_selected_locations ON COMMIT DROP AS "
                    "SELECT al.* FROM {}.asset_locations al "
                    "WHERE al.job_id IN (%s, %s) AND ST_Intersects("
                    "al.location, ST_MakeEnvelope(%s, %s, %s, %s, 4326)) "
                    "UNION "
                    "SELECT al.* FROM {}.asset_locations al "
                    "WHERE al.asset_location_id IN ("
                    "SELECT start_asset_location_id "
                    "FROM seaport_selected_meter_policies UNION "
                    "SELECT end_asset_location_id "
                    "FROM seaport_selected_meter_policies)"
                ).format(source, source),
                (
                    SOURCE_JOBS["fire_hydrant"],
                    SOURCE_JOBS["bus_stop"],
                    *envelope_params,
                ),
            )

            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.data_sources "
                    "SELECT ds.* FROM {}.data_sources ds "
                    "WHERE ds.data_source_id IN ("
                    "SELECT DISTINCT data_source_id "
                    "FROM seaport_selected_locations)"
                ).format(target, source)
            )
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.asset_locations "
                    "SELECT * FROM seaport_selected_locations"
                ).format(target)
            )
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.nonsign_features "
                    "SELECT nf.* FROM {}.nonsign_features nf "
                    "WHERE nf.feature_location IN ("
                    "SELECT asset_location_id FROM seaport_selected_locations)"
                ).format(target, source)
            )
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.meter_policies "
                    "SELECT * FROM seaport_selected_meter_policies"
                ).format(target)
            )

            counts = {
                "blockfaces": _count(
                    cur,
                    sql.SQL(
                        "SELECT count(*) FROM {}.curb_blockfaces WHERE job_id = %s"
                    ).format(target),
                    (blockface_job_id,),
                ),
                "fire_hydrant_locations": _count(
                    cur,
                    sql.SQL(
                        "SELECT count(*) FROM {}.asset_locations WHERE job_id = %s"
                    ).format(target),
                    (SOURCE_JOBS["fire_hydrant"],),
                ),
                "bus_stop_locations": _count(
                    cur,
                    sql.SQL(
                        "SELECT count(*) FROM {}.asset_locations WHERE job_id = %s"
                    ).format(target),
                    (SOURCE_JOBS["bus_stop"],),
                ),
                "parking_meter_locations": _count(
                    cur,
                    sql.SQL(
                        "SELECT count(*) FROM {}.asset_locations WHERE job_id = %s"
                    ).format(target),
                    (SOURCE_JOBS["parking_meters"],),
                ),
                "parking_meter_policies": _count(
                    cur,
                    sql.SQL(
                        "SELECT count(*) FROM {}.meter_policies WHERE job_id = %s"
                    ).format(target),
                    (SOURCE_JOBS["parking_meters"],),
                ),
                "asset_jobs": _count(
                    cur, sql.SQL("SELECT count(*) FROM {}.asset_jobs").format(target)
                ),
                "data_sources": _count(
                    cur, sql.SQL("SELECT count(*) FROM {}.data_sources").format(target)
                ),
                "nonsign_features": _count(
                    cur,
                    sql.SQL("SELECT count(*) FROM {}.nonsign_features").format(target),
                ),
            }
            mismatches = {
                key: {"expected": expected, "actual": counts[key]}
                for key, expected in EXPECTED_COUNTS.items()
                if counts[key] != expected
            }
            if mismatches:
                raise RuntimeError(f"Seed count validation failed: {mismatches}")

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    result = {
        "status": "passed",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "gcp_project_id": args.project_id,
        "source_schema": SOURCE_SCHEMA,
        "target_schema": TARGET_SCHEMA,
        "bbox": {**bbox, "expansion_degrees": EXPANSION_DEGREES},
        "jobs": {**SOURCE_JOBS, "seaport_blockface": blockface_job_id},
        "counts": counts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
