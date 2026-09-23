"""Freeze Chinatown Survey123 inputs and audit the target without database writes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import psycopg2
import requests
import yaml
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/sign-loader/src/sign_loader"))
from survey123 import _build_client, _normalize_guid, _resolve_layer_ids  # noqa: E402

BOUNDARY_URL = (
    "https://gis.boston.gov/arcgis/rest/services/"
    "Basemaps/basemap_IPS/MapServer/17/query"
)


def write_json(path: Path, value: object) -> None:
    """Write a local, inspectable artifact without credentials."""
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def audit_database() -> dict:
    """Record target tables, columns, job metadata, and description coverage."""
    result = {}
    with psycopg2.connect(
        dbname="cds",
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=10,
    ) as connection:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with connection.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS database, version() AS version")
            result["server"] = dict(cur.fetchone())
            cur.execute(
                "SELECT table_name, table_type FROM information_schema.tables "
                "WHERE table_schema = 'chinatown_cds' ORDER BY table_name"
            )
            tables = list(cur.fetchall())
            result["tables"] = tables
            result["counts"] = {}
            result["jobs"] = {}
            for table in tables:
                name = table["table_name"]
                cur.execute(
                    sql.SQL("SELECT count(*) AS n FROM {}.{}").format(
                        sql.Identifier("chinatown_cds"), sql.Identifier(name)
                    )
                )
                result["counts"][name] = cur.fetchone()["n"]
                if name.endswith("_jobs"):
                    cur.execute(
                        sql.SQL("SELECT * FROM {}.{} ORDER BY job_timestamp").format(
                            sql.Identifier("chinatown_cds"), sql.Identifier(name)
                        )
                    )
                    result["jobs"][name] = list(cur.fetchall())
            cur.execute(
                "SELECT table_name, column_name, data_type, udt_name "
                "FROM information_schema.columns WHERE table_schema='chinatown_cds' "
                "ORDER BY table_name, ordinal_position"
            )
            result["columns"] = list(cur.fetchall())
            if "curb_policies" in result["counts"]:
                cur.execute(
                    "SELECT count(*) AS total, count(*) FILTER ("
                    "WHERE description IS NULL "
                    "OR btrim(description)='' OR lower(btrim(description)) IN "
                    "('no description available','no policy description provided.',"
                    "'no policy description provided')) AS missing "
                    "FROM chinatown_cds.curb_policies"
                )
                result["descriptions"] = dict(cur.fetchone())
            cur.execute(
                "SELECT schemaname, viewname, definition FROM pg_views "
                "WHERE schemaname='chinatown_cds' ORDER BY viewname"
            )
            result["views"] = list(cur.fetchall())
    return result


def freeze_surveys(
    config_path: Path, output: Path, preserve_existing_footprint: bool = False
) -> dict:
    """Select all current parents within the official Chinatown neighborhood."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    survey = config["survey123"]
    response = requests.get(
        BOUNDARY_URL,
        params={
            "where": "Name = 'Chinatown'",
            "outFields": "*",
            "outSR": 4326,
            "returnGeometry": "true",
            "f": "geojson",
        },
        timeout=60,
    )
    response.raise_for_status()
    boundary = response.json()
    if not boundary.get("features"):
        raise ValueError(
            "The authoritative boundary query returned no Chinatown polygon"
        )
    polygon = unary_union([shape(f["geometry"]) for f in boundary["features"]])
    write_json(output / "chinatown_boundary.geojson", boundary)
    previous_bounds = None
    if preserve_existing_footprint:
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
                cur.execute(
                    "SELECT min(ST_X(a.location)), min(ST_Y(a.location)), "
                    "max(ST_X(a.location)), max(ST_Y(a.location)) "
                    "FROM chinatown_cds.signs s JOIN chinatown_cds.asset_locations a "
                    "ON a.asset_location_id=s.sign_location_id"
                )
                previous_bounds = cur.fetchone()
        if any(value is None for value in previous_bounds):
            raise ValueError("Previous Chinatown survey footprint is unavailable")
        polygon = polygon.union(box(*previous_bounds))
    write_json(
        output / "selection_geometry.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": polygon.__geo_interface__,
                    "properties": {"previous_survey_bounds": previous_bounds},
                }
            ],
        },
    )
    client = _build_client(survey)
    parent_id, repeat_id = _resolve_layer_ids(client, survey)
    parents = client.query_layer(parent_id, where="1=1", return_geometry=True)
    repeats = client.query_layer(repeat_id, where="1=1", return_geometry=False)
    selected = []
    nearby = []
    # Boundary-adjacent points are reported for review, never silently included.
    projected = (
        gpd.GeoSeries([polygon], crs=4326).to_crs(2249).buffer(30).to_crs(4326).iloc[0]
    )
    for feature in parents["features"]:
        geometry = feature.get("geometry")
        if not geometry or geometry.get("x") is None or geometry.get("y") is None:
            continue
        point = Point(geometry["x"], geometry["y"])
        if polygon.covers(point):
            selected.append(feature)
        elif projected.covers(point):
            nearby.append(feature)
    ids = {_normalize_guid(f["attributes"]["globalid"]) for f in selected}
    if not ids or None in ids or len(ids) != len(selected):
        raise ValueError(
            "Selected Chinatown parent IDs are empty, invalid, or duplicated"
        )
    matched = [
        f
        for f in repeats["features"]
        if _normalize_guid(f["attributes"].get("parentglobalid")) in ids
    ]
    eligible = [
        f
        for f in matched
        if str(f["attributes"].get("sign_type", "")).strip().casefold() != "driveway"
    ]
    repeat_ids = {_normalize_guid(f["attributes"]["globalid"]) for f in eligible}
    if not repeat_ids or None in repeat_ids or len(repeat_ids) != len(eligible):
        raise ValueError(
            "Selected Chinatown sign IDs are empty, invalid, or duplicated"
        )
    with (output / "parent_globalids.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["GlobalID"])
        writer.writerows([[value] for value in sorted(ids)])
    write_json(output / "parents.json", selected)
    write_json(output / "repeats.json", matched)
    write_json(output / "boundary_adjacent_parents.json", nearby)
    write_json(output / "expected_sign_ids.json", sorted(repeat_ids))
    result = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "service_url": survey["service_url"],
        "parent_layer_id": parent_id,
        "repeat_layer_id": repeat_id,
        "boundary_url": BOUNDARY_URL,
        "selection": "All current parents in Chinatown polygon"
        + (
            " or previous Chinatown survey bounding box"
            if preserve_existing_footprint
            else ""
        ),
        "previous_survey_bounds": previous_bounds,
        "all_service_parents": len(parents["features"]),
        "selected_parents": len(selected),
        "selected_repeats": len(matched),
        "eligible_signs": len(eligible),
        "excluded_driveways": len(matched) - len(eligible),
        "boundary_adjacent_parents": len(nearby),
        "sign_types": dict(Counter(f["attributes"].get("sign_type") for f in matched)),
        "creation_dates": dict(
            Counter(
                datetime.fromtimestamp(f["attributes"]["CreationDate"] / 1000, UTC)
                .date()
                .isoformat()
                for f in selected
                if f["attributes"].get("CreationDate")
            )
        ),
        "sha256": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name in (
                "chinatown_boundary.geojson",
                "selection_geometry.geojson",
                "parent_globalids.csv",
                "parents.json",
                "repeats.json",
                "expected_sign_ids.json",
                "boundary_adjacent_parents.json",
            )
        },
    }
    write_json(output / "survey_preflight.json", result)
    return result


def main() -> None:
    """Run a source freeze or a read-only database baseline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "packages/sign-loader/config.yaml"
    )
    parser.add_argument("--database-only", action="store_true")
    parser.add_argument("--include-existing-footprint", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.database_only:
        result = audit_database()
        write_json(args.output / "database_preflight.json", result)
        print(
            json.dumps(
                {
                    "counts": result["counts"],
                    "descriptions": result.get("descriptions"),
                },
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                freeze_surveys(
                    args.config, args.output, args.include_existing_footprint
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
