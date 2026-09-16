"""Pre/post data-quality checks for the staging_next policy tables.

Computes data-quality metrics for ``sign_policies`` and ``curb_segment_policies``
(plus cross-table integrity / api-updater readiness checks), prints a report,
saves a timestamped JSON snapshot, and diffs against a previous snapshot.

Run once before the upsert and once after to observe the differences:

    uv run python scripts/check_staging_policies.py --label pre
    # ... run scripts/load_staging_policies.py ...
    uv run python scripts/check_staging_policies.py --label post

By default the second run diffs against the most recent prior snapshot for the
same schema. All queries are read-only.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from curb_utils.db_utils import SmartCurbDB
from curb_utils.logging import get_console, get_logger
from dotenv import load_dotenv
from rich.table import Table
from sqlalchemy import text

logger = get_logger(__name__)
console = get_console()

# scripts/<this file> -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output"

SECTIONS = ("sign_policies", "curb_segment_policies", "cross_table")


# ── Query helpers ─────────────────────────────────────────────────────────────


def _scalar(db: SmartCurbDB, sql: str) -> object:
    """Run a SELECT returning a single value."""
    assert db.connection is not None
    return db.connection.execute(text(sql)).scalar()


def _one_row(db: SmartCurbDB, sql: str) -> dict[str, object]:
    """Run a SELECT returning a single row as a {column: value} dict."""
    assert db.connection is not None
    return dict(db.connection.execute(text(sql)).one()._mapping)


def _grouped(db: SmartCurbDB, sql: str) -> dict[str, int]:
    """Run a two-column ``SELECT key, count`` into a {key: count} dict.

    NULL keys are rendered as the literal string ``(null)`` so the result is
    JSON-serialisable.
    """
    assert db.connection is not None
    rows = db.connection.execute(text(sql)).fetchall()
    out: dict[str, int] = {}
    for row in rows:
        key = "(null)" if row[0] is None else str(row[0])
        out[key] = int(row[1])
    return out


# ── Within-table metrics ──────────────────────────────────────────────────────


def _sign_policies_metrics(
    db: SmartCurbDB, schema: str, checksum: bool
) -> dict[str, object]:
    """Collect within-table metrics for ``sign_policies``."""
    t = f"{schema}.sign_policies"

    base_sql = f"""
        SELECT
            count(*) AS total_rows,
            count(DISTINCT sign_id) AS distinct_signs,
            count(DISTINCT job_id) AS distinct_jobs,
            count(*) FILTER (WHERE policy_json IS NULL) AS null_policy_json,
            count(*) FILTER (WHERE cds_override IS NOT NULL) AS human_overrides,
            count(*) FILTER (WHERE ai_commentary IS NOT NULL) AS with_commentary,
            count(*) FILTER (WHERE policy_json->'rules' IS NULL) AS missing_rules,
            count(*) FILTER (WHERE policy_json->'time_spans' IS NULL) AS no_time_spans,
            count(*) FILTER (WHERE policy_json->'priority' IS NULL) AS missing_priority
        FROM {t}
    """
    metrics: dict[str, object] = dict(_one_row(db, base_sql))

    metrics["rows_per_job"] = _grouped(
        db,
        f"SELECT job_id, count(*) FROM {t} GROUP BY job_id ORDER BY count(*) DESC",
    )
    metrics["policy_arrow"] = _grouped(
        db,
        f"SELECT policy_arrow, count(*) FROM {t} "
        f"GROUP BY policy_arrow ORDER BY count(*) DESC",
    )

    activity_sql = f"""
        SELECT rule->>'activity' AS activity, count(*)
        FROM {t} sp
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(sp.policy_json->'rules') = 'array'
                 THEN sp.policy_json->'rules' ELSE '[]'::jsonb END
        ) AS rule
        GROUP BY 1 ORDER BY 2 DESC
    """
    metrics["activities"] = _grouped(db, activity_sql)

    priority_sql = f"""
        SELECT
            min((policy_json->>'priority')::int) AS min,
            max((policy_json->>'priority')::int) AS max,
            avg((policy_json->>'priority')::float8) AS avg
        FROM {t}
        WHERE jsonb_typeof(policy_json->'priority') = 'number'
    """
    metrics["priority"] = _one_row(db, priority_sql)

    if checksum:
        checksum_sql = f"""
            SELECT md5(string_agg(
                sign_policy_id::text || ':' || coalesce(policy_json::text, ''),
                ',' ORDER BY sign_policy_id))
            FROM {t}
        """
        metrics["checksum"] = _scalar(db, checksum_sql)

    return metrics


def _curb_segment_policies_metrics(
    db: SmartCurbDB, schema: str, checksum: bool
) -> dict[str, object]:
    """Collect within-table metrics for ``curb_segment_policies``."""
    t = f"{schema}.curb_segment_policies"

    base_sql = f"""
        SELECT
            count(*) AS total_rows,
            count(DISTINCT segment_id) AS distinct_segments,
            count(DISTINCT job_id) AS distinct_jobs,
            count(*) FILTER (WHERE policy_list IS NULL) AS null_policy_list,
            count(*) FILTER (
                WHERE jsonb_typeof(policy_list) <> 'array'
            ) AS non_array
        FROM {t}
    """
    metrics: dict[str, object] = dict(_one_row(db, base_sql))

    metrics["rows_per_job"] = _grouped(
        db,
        f"SELECT job_id, count(*) FROM {t} GROUP BY job_id ORDER BY count(*) DESC",
    )

    # Length stats only over rows that are genuinely JSON arrays.
    length_sql = f"""
        SELECT
            count(*) FILTER (WHERE jsonb_array_length(policy_list) = 0) AS empty,
            count(*) FILTER (WHERE jsonb_array_length(policy_list) > 0) AS non_empty,
            min(jsonb_array_length(policy_list)) AS min,
            max(jsonb_array_length(policy_list)) AS max,
            avg(jsonb_array_length(policy_list)::float8) AS avg
        FROM {t}
        WHERE jsonb_typeof(policy_list) = 'array'
    """
    metrics["policy_list_length"] = _one_row(db, length_sql)

    activity_sql = f"""
        SELECT rule->>'activity' AS activity, count(*)
        FROM {t} csp
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(csp.policy_list) = 'array'
                 THEN csp.policy_list ELSE '[]'::jsonb END
        ) AS pol
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(pol->'rules') = 'array'
                 THEN pol->'rules' ELSE '[]'::jsonb END
        ) AS rule
        GROUP BY 1 ORDER BY 2 DESC
    """
    metrics["activities"] = _grouped(db, activity_sql)

    if checksum:
        checksum_sql = f"""
            SELECT md5(string_agg(
                segment_id::text || ':' || job_id::text || ':'
                || coalesce(policy_list::text, ''),
                ',' ORDER BY segment_id, job_id))
            FROM {t}
        """
        metrics["checksum"] = _scalar(db, checksum_sql)

    return metrics


# ── Cross-table integrity / api-updater readiness ─────────────────────────────


def _cross_table_metrics(db: SmartCurbDB, schema: str) -> dict[str, object]:
    """Collect cross-table integrity and api-updater readiness checks."""
    sp = f"{schema}.sign_policies"
    csp = f"{schema}.curb_segment_policies"
    signs = f"{schema}.signs"
    segs = f"{schema}.curb_segments"
    sr_jobs = f"{schema}.sign_reader_jobs"
    ph_jobs = f"{schema}.policy_handling_jobs"

    metrics: dict[str, object] = {}

    metrics["signs_without_policies"] = _scalar(
        db,
        f"SELECT count(*) FROM {signs} s WHERE NOT EXISTS "
        f"(SELECT 1 FROM {sp} p WHERE p.sign_id = s.sign_id)",
    )
    metrics["segments_without_policies"] = _scalar(
        db,
        f"SELECT count(*) FROM {segs} s WHERE NOT EXISTS "
        f"(SELECT 1 FROM {csp} p WHERE p.segment_id = s.segment_id)",
    )
    metrics["orphan_policy_segments"] = _scalar(
        db,
        f"SELECT count(*) FROM {csp} p WHERE NOT EXISTS "
        f"(SELECT 1 FROM {segs} s WHERE s.segment_id = p.segment_id)",
    )
    metrics["orphan_policy_signs"] = _scalar(
        db,
        f"SELECT count(*) FROM {sp} p WHERE NOT EXISTS "
        f"(SELECT 1 FROM {signs} s WHERE s.sign_id = p.sign_id)",
    )
    metrics["segment_policy_jobs_missing"] = _scalar(
        db,
        f"SELECT count(*) FROM {csp} p WHERE NOT EXISTS "
        f"(SELECT 1 FROM {ph_jobs} j WHERE j.job_id = p.job_id)",
    )
    metrics["sign_policy_jobs_missing"] = _scalar(
        db,
        f"SELECT count(*) FROM {sp} p WHERE NOT EXISTS "
        f"(SELECT 1 FROM {sr_jobs} j WHERE j.job_id = p.job_id)",
    )
    metrics["policy_segments_null_geography"] = _scalar(
        db,
        f"SELECT count(*) FROM {csp} p "
        f"JOIN {segs} s ON s.segment_id = p.segment_id "
        f"WHERE s.geography IS NULL",
    )
    metrics["non_empty_policy_segments"] = _scalar(
        db,
        f"SELECT count(*) FROM {csp} "
        f"WHERE jsonb_typeof(policy_list) = 'array' "
        f"AND jsonb_array_length(policy_list) > 0",
    )
    return metrics


def collect_snapshot(
    db: SmartCurbDB, schema: str, label: str, ts: datetime, checksum: bool
) -> dict[str, object]:
    """Build the full metrics snapshot dictionary."""
    return {
        "schema": schema,
        "label": label,
        "timestamp": ts.isoformat(timespec="seconds"),
        "sign_policies": _sign_policies_metrics(db, schema, checksum),
        "curb_segment_policies": _curb_segment_policies_metrics(db, schema, checksum),
        "cross_table": _cross_table_metrics(db, schema),
    }


def evaluate_warnings(snapshot: dict[str, object]) -> list[str]:
    """Return human-readable warnings for any violated data-quality invariant."""
    warnings: list[str] = []
    sign = snapshot["sign_policies"]
    seg = snapshot["curb_segment_policies"]
    cross = snapshot["cross_table"]
    assert isinstance(sign, dict) and isinstance(seg, dict) and isinstance(cross, dict)

    def _nonzero(section: dict[str, object], key: str, message: str) -> None:
        value = section.get(key)
        if isinstance(value, int) and value > 0:
            warnings.append(f"{message}: {value}")

    _nonzero(sign, "null_policy_json", "sign_policies with NULL policy_json")
    _nonzero(seg, "null_policy_list", "curb_segment_policies with NULL policy_list")
    _nonzero(seg, "non_array", "curb_segment_policies with non-array policy_list")
    _nonzero(
        cross, "orphan_policy_segments", "policy segments missing from curb_segments"
    )
    _nonzero(cross, "orphan_policy_signs", "sign policies missing from signs")
    _nonzero(cross, "segment_policy_jobs_missing", "segment policy job_ids missing")
    _nonzero(cross, "sign_policy_jobs_missing", "sign policy job_ids missing")
    _nonzero(
        cross,
        "policy_segments_null_geography",
        "policy segments whose curb_segments.geography is NULL (breaks api-updater)",
    )

    if cross.get("non_empty_policy_segments") == 0:
        warnings.append(
            "no curb_segment_policies have a non-empty policy_list; "
            "api-updater would produce no policies"
        )
    return warnings


# ── Reporting ─────────────────────────────────────────────────────────────────


def _fmt(value: object) -> str:
    """Format a metric value for display."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def print_report(snapshot: dict[str, object]) -> None:
    """Print a per-section report of the snapshot metrics."""
    console.rule(
        f"Data quality: {snapshot['schema']} "
        f"[{snapshot['label']}] @ {snapshot['timestamp']}"
    )
    for section in SECTIONS:
        data = snapshot[section]
        assert isinstance(data, dict)
        table = Table(title=section, header_style="bold", show_lines=False)
        table.add_column("metric")
        table.add_column("value", justify="right")
        for key, value in data.items():
            if isinstance(value, dict):
                table.add_row(key, "")
                for sub_key, sub_value in value.items():
                    table.add_row(f"  {sub_key}", _fmt(sub_value))
            else:
                table.add_row(key, _fmt(value))
        console.print(table)


def _flatten(data: dict[str, object], prefix: str = "") -> dict[str, object]:
    """Flatten a nested metrics dict into dotted keys."""
    out: dict[str, object] = {}
    for key, value in data.items():
        full_key = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, prefix=f"{full_key}."))
        else:
            out[full_key] = value
    return out


def _is_number(value: object) -> bool:
    """True for int/float but not bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _delta(prev: object, curr: object) -> str:
    """Describe the change between two metric values."""
    if _is_number(prev) and _is_number(curr):
        assert isinstance(prev, (int, float)) and isinstance(curr, (int, float))
        diff = curr - prev
        sign = "+" if diff >= 0 else ""
        return f"{sign}{diff:g}"
    if prev is None and curr is not None:
        return "new"
    if curr is None and prev is not None:
        return "removed"
    return "changed"


def print_diff(prev: dict[str, object], curr: dict[str, object]) -> None:
    """Print scalar deltas and distribution key changes between two snapshots."""
    console.rule(
        f"Diff: {prev.get('label')} ({prev.get('timestamp')}) -> "
        f"{curr.get('label')} ({curr.get('timestamp')})"
    )
    for section in SECTIONS:
        prev_section = prev.get(section, {})
        curr_section = curr.get(section, {})
        assert isinstance(prev_section, dict) and isinstance(curr_section, dict)
        prev_flat = _flatten(prev_section)
        curr_flat = _flatten(curr_section)

        table = Table(title=f"{section} (changes)", header_style="bold")
        table.add_column("metric")
        table.add_column("pre", justify="right")
        table.add_column("post", justify="right")
        table.add_column("delta", justify="right")

        changed = False
        for key in sorted(set(prev_flat) | set(curr_flat)):
            prev_value = prev_flat.get(key)
            curr_value = curr_flat.get(key)
            if prev_value != curr_value:
                changed = True
                table.add_row(
                    key,
                    _fmt(prev_value),
                    _fmt(curr_value),
                    _delta(prev_value, curr_value),
                )
        if changed:
            console.print(table)
        else:
            console.print(f"{section}: no changes")


# ── Snapshot persistence ──────────────────────────────────────────────────────


def save_snapshot(snapshot: dict[str, object], output_dir: Path, ts: datetime) -> Path:
    """Write the snapshot to a timestamped JSON file and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = ts.strftime("%Y%m%d_%H%M%S")
    filename = f"policy_quality_{snapshot['schema']}_{snapshot['label']}_{stamp}.json"
    path = output_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, default=str)
    return path


def find_latest_snapshot(output_dir: Path, schema: str) -> Path | None:
    """Return the most recently modified prior snapshot for the schema, if any."""
    if not output_dir.exists():
        return None
    candidates = sorted(
        output_dir.glob(f"policy_quality_{schema}_*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbname", default="cds", help="Database name (default: cds).")
    parser.add_argument(
        "--schema", default="staging_next", help="Schema (default: staging_next)."
    )
    parser.add_argument(
        "--label",
        default="snapshot",
        help="Label for this snapshot, e.g. pre or post (default: snapshot).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for snapshot JSON files.",
    )
    parser.add_argument(
        "--compare-to",
        type=Path,
        help="Explicit prior snapshot JSON to diff against.",
    )
    parser.add_argument(
        "--no-compare",
        action="store_true",
        help="Do not diff against a prior snapshot.",
    )
    parser.add_argument(
        "--checksum",
        action="store_true",
        help="Also compute a per-table md5 fingerprint (scans full tables).",
    )
    return parser.parse_args()


def main() -> None:
    """Collect metrics, print a report, save a snapshot, and diff vs the prior one."""
    args = parse_args()
    load_dotenv()
    ts = datetime.now()

    logger.info("Collecting metrics for %s.%s ...", args.dbname, args.schema)
    with SmartCurbDB(dbname=args.dbname, schema=args.schema) as db:
        snapshot = collect_snapshot(db, args.schema, args.label, ts, args.checksum)

    print_report(snapshot)

    for warning in evaluate_warnings(snapshot):
        logger.warning(warning)

    # Resolve the prior snapshot before writing the new one.
    prior_path: Path | None = None
    if not args.no_compare:
        prior_path = args.compare_to or find_latest_snapshot(
            args.output_dir, args.schema
        )

    new_path = save_snapshot(snapshot, args.output_dir, ts)
    logger.info("Saved snapshot to %s", new_path)

    if args.no_compare:
        return
    if prior_path and prior_path.exists():
        with open(prior_path, encoding="utf-8") as f:
            prior = json.load(f)
        print_diff(prior, snapshot)
    else:
        logger.info("No prior snapshot found to compare against.")


if __name__ == "__main__":
    main()
