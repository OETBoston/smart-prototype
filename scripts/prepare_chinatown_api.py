"""Preserve the current Chinatown API in tables before running new staging jobs.

The existing views select the latest staging job automatically. Seed their current
records into the standard API tables, then replace both views in one transaction.
Without --apply the complete migration is exercised and rolled back.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "chinatown_cds"


def canonical(value: object) -> object:
    """Compare view content independently of array aggregation order."""
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return sorted(
            (canonical(v) for v in value),
            key=lambda v: json.dumps(v, sort_keys=True, default=str),
        )
    return value


def read_views(cursor) -> dict:
    """Capture the complete visible API state within the current transaction."""
    result = {}
    for view in ("vw_curb_zones", "vw_curb_policies"):
        cursor.execute(
            sql.SQL("SELECT to_jsonb(v) AS row FROM {}.{} v").format(
                sql.Identifier(SCHEMA), sql.Identifier(view)
            )
        )
        result[view] = canonical([r["row"] for r in cursor.fetchall()])
    return result


def main() -> None:
    """Validate a schema-only publication migration and optionally commit it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.backup.is_file() or args.backup.stat().st_size == 0:
        raise ValueError("A completed schema backup is required before migration")
    if args.backup.read_bytes()[:5] != b"PGDMP":
        raise ValueError("Expected a pg_dump custom-format backup")
    load_dotenv(ROOT / ".env")
    source = ROOT / "packages/api-db-rollover/src/api_db_rollover/sql/init_db.sql"
    ddl = source.read_text(encoding="utf-8")
    ddl = re.sub(r"\bpublic_cds_next\b", SCHEMA, ddl)
    ddl = re.sub(r"DROP VIEW IF EXISTS \w+;", "", ddl)
    # Chinatown already exposes designated_period as a JSON array. Retain it.
    ddl = ddl.replace("designated_period VARCHAR,", "designated_period TEXT[],")
    table_ddl, view_ddl = ddl.split("-- Create Views", 1)
    if re.search(r"\bDROP\b", table_ddl + view_ddl, re.I):
        raise ValueError("Unexpected destructive statement in API initialization SQL")
    connection = psycopg2.connect(
        dbname="cds",
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=10,
    )
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SET LOCAL lock_timeout = '10s'")
            cur.execute("SELECT to_regclass('chinatown_cds.curb_policies') AS existing")
            if cur.fetchone()["existing"]:
                raise ValueError(
                    "API tables already exist; inspect them instead of reseeding"
                )
            before = read_views(cur)
            cur.execute(table_ddl)
            # The API's existing IDs, dates and geometries must survive migration.
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name='curb_zones' "
                "ORDER BY ordinal_position",
                (SCHEMA,),
            )
            zone_columns = sql.SQL(", ").join(
                sql.Identifier(r["column_name"]) for r in cur.fetchall()
            )
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.curb_zones ({}) SELECT {} FROM {}.vw_curb_zones"
                ).format(
                    sql.Identifier(SCHEMA),
                    zone_columns,
                    zone_columns,
                    sql.Identifier(SCHEMA),
                )
            )
            cur.execute(
                "INSERT INTO chinatown_cds.curb_policies "
                "(curb_policy_id, name, description, published_date, priority) "
                "SELECT curb_policy_id, name, description, published_date, priority "
                "FROM chinatown_cds.vw_curb_policies"
            )
            for table, field in (
                ("curb_policy_rules", "rules"),
                ("curb_policy_time_spans", "time_spans"),
                ("curb_policy_rates", "rates"),
            ):
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {}.{} SELECT r.* FROM {}.vw_curb_policies v "
                        "CROSS JOIN LATERAL jsonb_populate_recordset(NULL::{}.{}, "
                        "COALESCE(v.{}, '[]'::jsonb)) r"
                    ).format(
                        sql.Identifier(SCHEMA),
                        sql.Identifier(table),
                        sql.Identifier(SCHEMA),
                        sql.Identifier(SCHEMA),
                        sql.Identifier(table),
                        sql.Identifier(field),
                    )
                )
            cur.execute(
                "INSERT INTO chinatown_cds.curb_zone_policies "
                "SELECT curb_zone_id, unnest(curb_policy_ids) "
                "FROM chinatown_cds.vw_curb_zones"
            )
            cur.execute(view_ddl)
            after = read_views(cur)
            if before != after:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                (args.output.parent / "api_migration_diff.json").write_text(
                    json.dumps(
                        {"before": before, "after": after}, indent=2, default=str
                    ),
                    encoding="utf-8",
                )
                raise ValueError("API records changed during migration; rolling back")
            cur.execute('GRANT USAGE ON SCHEMA chinatown_cds TO "cds-api"')
            cur.execute(
                'GRANT SELECT ON ALL TABLES IN SCHEMA chinatown_cds TO "cds-api"'
            )
        if args.apply:
            connection.commit()
        else:
            connection.rollback()
        result = {
            "status": "committed" if args.apply else "validated_and_rolled_back",
            "schema": SCHEMA,
            "api_content_unchanged": True,
            "counts": {key: len(value) for key, value in before.items()},
            "backup": str(args.backup.resolve()),
            "backup_sha256": hashlib.sha256(args.backup.read_bytes()).hexdigest(),
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
