"""Read-only validation of the job-filter fixes against ``cds.staging_next``.

Proves the two fixes behave correctly against live data without changing
anything. It exercises only the real read / transform paths and deliberately
never touches the write / publish paths.

Fix 1 - api-updater
    * The null-``policy_handler`` guard in ``api_updater`` raises *before* any DB
      access. As a safety net we also neutralise the read / export functions on
      the ``core`` module, so a regression cannot reach the database.
    * The real ``read_db_tables`` path binds the quoted ``job_id = '<uuid>'``
      filter and returns exactly one row per segment for a single
      ``policy_handling_jobs`` run; the unfiltered table has multiple rows per
      segment (the double-count the filter prevents).
    * ``consolidate_curb_segments`` still runs on the filtered set.

Fix 2 - policy-applier
    * ``read_policy_applier_tables`` forwards ``sign_reader_job_id`` so the
      returned ``df_sign_policies`` shrinks to a single sign-reader job.
    * Per-job ``sign_policies`` counts reconcile to the unfiltered total and
      quantify the cross-job duplication the filter removes.

This script NEVER imports or calls ``export_to_db``,
``append_curb_segment_policies``, ``append_policy_handling_jobs`` or the
``api-db-rollover``. The concrete job ids are discovered from the database, so
it does not depend on the TODO placeholders in the package configs.

Run it with the DB tunnel up:

    uv run python scripts/validate_job_filters.py
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# api-updater: the guarded entrypoint module plus the read / transform path.
import api_updater.core as api_updater_core
from api_updater.config import ApiUpdaterConfig
from api_updater.extractor import read_db_tables
from api_updater.utils_geo import consolidate_curb_segments
from curb_utils.db_utils import SmartCurbDB
from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import get_console, get_logger
from dotenv import load_dotenv

# policy-applier: pure read path under test.
from policy_applier.db_utils.db_connector import read_policy_applier_tables
from rich.table import Table
from sqlalchemy import text

logger = get_logger(__name__)
console = get_console()

# scripts/<this file> -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
API_UPDATER_CONFIG = (
    REPO_ROOT / "packages" / "api-updater" / "src" / "api_updater" / "config.yaml"
)


# ── Result tracking ───────────────────────────────────────────────────────────


@dataclass
class Results:
    """Collects PASS/FAIL checks and the overall verdict."""

    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def record(self, name: str, passed: bool, detail: str = "") -> bool:
        """Record one check and log it."""
        passed = bool(passed)
        self.checks.append((name, passed, detail))
        status = "PASS" if passed else "FAIL"
        logger.info("[%s] %s%s", status, name, f" - {detail}" if detail else "")
        return passed

    @property
    def ok(self) -> bool:
        """True only when every recorded check passed."""
        return all(passed for _, passed, _ in self.checks)


# ── SQL helpers (read-only) ───────────────────────────────────────────────────


def _scalar(db: SmartCurbDB, sql: str) -> object:
    """Run a SELECT returning a single value."""
    assert db.connection is not None
    return db.connection.execute(text(sql)).scalar()


def _grouped(db: SmartCurbDB, sql: str) -> dict[str, int]:
    """Run a two-column ``SELECT key, count`` into a {key: count} dict."""
    assert db.connection is not None
    rows = db.connection.execute(text(sql)).fetchall()
    return {("(null)" if r[0] is None else str(r[0])): int(r[1]) for r in rows}


# ── Discovery (cheap aggregates) ──────────────────────────────────────────────


@dataclass
class Discovered:
    """Job ids and aggregate counts discovered from the live schema."""

    policy_jobs: dict[str, int]
    policy_total: int
    policy_distinct_segments: int
    policy_max_per_segment: int
    sign_jobs: dict[str, int]
    sign_total: int
    sign_distinct: int
    segment_jobs: dict[str, int]
    asset_locations: int


def discover(db: SmartCurbDB, schema: str) -> Discovered:
    """Collect job ids and counts used to drive the checks (all read-only)."""
    csp = f"{schema}.curb_segment_policies"
    sp = f"{schema}.sign_policies"
    segs = f"{schema}.curb_segments"

    policy_jobs = _grouped(
        db,
        f"SELECT job_id, count(*) FROM {csp} GROUP BY job_id ORDER BY count(*) DESC",
    )
    sign_jobs = _grouped(
        db,
        f"SELECT job_id, count(*) FROM {sp} GROUP BY job_id ORDER BY count(*) DESC",
    )
    segment_jobs = _grouped(
        db,
        f"SELECT job_id, count(*) FROM {segs} GROUP BY job_id ORDER BY count(*) DESC",
    )
    return Discovered(
        policy_jobs=policy_jobs,
        policy_total=int(_scalar(db, f"SELECT count(*) FROM {csp}")),
        policy_distinct_segments=int(
            _scalar(db, f"SELECT count(DISTINCT segment_id) FROM {csp}")
        ),
        policy_max_per_segment=int(
            _scalar(
                db,
                f"SELECT max(c) FROM "
                f"(SELECT count(*) c FROM {csp} GROUP BY segment_id) t",
            )
        ),
        sign_jobs=sign_jobs,
        sign_total=int(_scalar(db, f"SELECT count(*) FROM {sp}")),
        sign_distinct=int(_scalar(db, f"SELECT count(DISTINCT sign_id) FROM {sp}")),
        segment_jobs=segment_jobs,
        asset_locations=int(
            _scalar(db, f"SELECT count(*) FROM {schema}.asset_locations")
        ),
    )


# ── Fix 1: api-updater ─────────────────────────────────────────────────────────


def check_guard(results: Results) -> None:
    """The null-``policy_handler`` guard must raise before any DB access."""
    data = load_from_yaml(str(API_UPDATER_CONFIG))
    data.setdefault("source_jobs", {})
    # Force the guard condition regardless of what the config currently holds.
    data["source_jobs"]["policy_handler"] = None
    data["source_jobs"]["curb_segmenter"] = None
    cfg = ApiUpdaterConfig(**data)

    # Safety net: if the guard ever regressed, these stubs make the test fail
    # loudly instead of letting api_updater read or export anything.
    original_read = api_updater_core.read_db_tables
    original_export = api_updater_core.export_to_db

    def _forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("DB read/export reached despite null policy_handler")

    api_updater_core.read_db_tables = _forbidden  # type: ignore[assignment]
    api_updater_core.export_to_db = _forbidden  # type: ignore[assignment]
    try:
        api_updater_core.api_updater(cfg)
    except ValueError as exc:
        results.record(
            "fix1.guard_raises_on_null_policy_handler",
            "policy_handler" in str(exc),
            f"ValueError: {exc}",
        )
    except AssertionError as exc:
        results.record("fix1.guard_raises_on_null_policy_handler", False, str(exc))
    else:
        results.record(
            "fix1.guard_raises_on_null_policy_handler",
            False,
            "api_updater did not raise on null policy_handler",
        )
    finally:
        api_updater_core.read_db_tables = original_read  # type: ignore[assignment]
        api_updater_core.export_to_db = original_export  # type: ignore[assignment]


def check_fix1_reads(
    results: Results, disc: Discovered, dbname: str, schema: str
) -> None:
    """Exercise the real api-updater read path and the double-count property."""
    if not disc.policy_jobs:
        results.record("fix1.policy_jobs_present", False, "no curb_segment_policies")
        return

    ph_job = next(iter(disc.policy_jobs))  # most rows (ORDER BY count DESC)
    ph_count = disc.policy_jobs[ph_job]

    # Real api-updater read path, with the quoted filter exactly as core.py builds
    # it. The pre-fix unquoted form (job_id = <uuid>) would be invalid SQL.
    started = time.perf_counter()
    one = read_db_tables(
        dbname,
        schema,
        {"curb_segments": None, "curb_segment_policies": f"job_id = '{ph_job}'"},
    )
    elapsed = time.perf_counter() - started
    csp_one = one["curb_segment_policies"]

    results.record(
        "fix1.filtered_quoted_filter_executes",
        len(csp_one) == ph_count,
        f"job {ph_job[:8]}.. -> {len(csp_one)} rows (expected {ph_count}); "
        f"read {elapsed:.1f}s",
    )
    results.record(
        "fix1.filtered_one_row_per_segment",
        bool(csp_one["segment_id"].is_unique),
        f"{csp_one['segment_id'].nunique()} distinct segments, "
        f"max rows/segment = {int(csp_one.groupby('segment_id').size().max())}",
    )

    # Unfiltered double-count property, proven via a cheap SQL aggregate instead
    # of materialising 200k+ JSONB rows (equivalent to the groupby an unfiltered
    # read_db_tables would produce).
    n_jobs = len(disc.policy_jobs)
    ratio = disc.policy_total / disc.policy_distinct_segments
    results.record(
        "fix1.unfiltered_double_counts",
        disc.policy_max_per_segment >= 2
        if n_jobs >= 2
        else disc.policy_max_per_segment == 1,
        f"{n_jobs} jobs: {disc.policy_total} rows over "
        f"{disc.policy_distinct_segments} segments (x{ratio:.2f}); "
        f"max rows/segment = {disc.policy_max_per_segment}",
    )

    # Transform still runs on the filtered set (consolidate mutates geography in
    # place, so it operates on this fresh read only).
    started = time.perf_counter()
    merged = consolidate_curb_segments(one["curb_segments"], csp_one)
    elapsed = time.perf_counter() - started
    results.record(
        "fix1.consolidate_runs_on_filtered_set",
        len(merged) > 0,
        f"{len(csp_one)} policies -> {len(merged)} curb zones in {elapsed:.1f}s",
    )


# ── Fix 2: policy-applier ──────────────────────────────────────────────────────


def check_fix2(results: Results, disc: Discovered, dbname: str, schema: str) -> None:
    """Exercise the policy-applier sign-reader filter (pure reads)."""
    if not disc.sign_jobs:
        results.record("fix2.sign_jobs_present", False, "no sign_policies")
        return

    sr_job = next(iter(disc.sign_jobs))  # most rows
    sr_count = disc.sign_jobs[sr_job]
    n_sign_jobs = len(disc.sign_jobs)

    # The exact filter expression the fix builds is valid SQL and selects the job.
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        filtered = db.get_data(
            "sign_policies", filter=f"job_id = '{sr_job}'", columns=["sign_id"]
        )
    results.record(
        "fix2.sign_policies_filter_expression_valid",
        len(filtered) == sr_count,
        f"job {sr_job[:8]}.. -> {len(filtered)} rows (expected {sr_count})",
    )

    # Per-job counts reconcile to the unfiltered total; quantify the duplication.
    per_job_sum = sum(disc.sign_jobs.values())
    duplication = disc.sign_total - disc.sign_distinct
    results.record(
        "fix2.sign_policies_counts_reconcile",
        per_job_sum == disc.sign_total,
        f"sum(per-job)={per_job_sum} == total={disc.sign_total}; "
        f"distinct_signs={disc.sign_distinct}; duplicate rows={duplication}",
    )

    # Real function wiring: forwarding sign_reader_job_id shrinks df_sign_policies
    # to the single job. Use the smallest curb_segments job so the (unrelated)
    # segment-geometry read stays cheap; sign_policies is what we assert on.
    seg_job = (
        min(disc.segment_jobs, key=lambda k: disc.segment_jobs[k])
        if disc.segment_jobs
        else None
    )
    seg_n = disc.segment_jobs.get(seg_job, 0) if seg_job else 0
    logger.info(
        "Reading policy-applier tables (segments job %s = %s rows, "
        "asset_locations = %s rows with geometry)...",
        (seg_job or "None")[:8] + (".." if seg_job else ""),
        seg_n,
        disc.asset_locations,
    )
    started = time.perf_counter()
    res_one = read_policy_applier_tables(
        curb_segment_job_id=seg_job,
        sign_reader_job_id=sr_job,
        db_name=dbname,
        db_schema=schema,
    )
    elapsed = time.perf_counter() - started
    df_sp_one = res_one[3]  # df_sign_policies

    results.record(
        "fix2.read_policy_applier_forwards_filter",
        len(df_sp_one) == sr_count,
        f"df_sign_policies = {len(df_sp_one)} rows for job {sr_job[:8]}.. "
        f"(expected {sr_count}); read {elapsed:.1f}s",
    )
    results.record(
        "fix2.filter_shrinks_vs_all_jobs",
        len(df_sp_one) < disc.sign_total if n_sign_jobs >= 2 else True,
        f"{len(df_sp_one)} (one job) vs {disc.sign_total} (all {n_sign_jobs} jobs)",
    )


# ── Reporting / CLI ────────────────────────────────────────────────────────────


def print_summary(results: Results) -> None:
    """Print a PASS/FAIL table of all checks."""
    table = Table(title="validate_job_filters", header_style="bold", show_lines=False)
    table.add_column("check")
    table.add_column("result", justify="center")
    table.add_column("detail")
    for name, passed, detail in results.checks:
        style = "green" if passed else "red"
        table.add_row(name, f"[{style}]{'PASS' if passed else 'FAIL'}[/]", detail)
    console.print(table)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbname", default="cds", help="Database name (default: cds).")
    parser.add_argument(
        "--schema", default="staging_next", help="Schema (default: staging_next)."
    )
    return parser.parse_args()


def main() -> None:
    """Discover job ids, run all read-only checks, and exit non-zero on failure."""
    args = parse_args()
    load_dotenv()
    results = Results()

    console.rule(f"Validating job-filter fixes against {args.dbname}.{args.schema}")
    logger.info("Discovering job ids and counts (read-only)...")
    with SmartCurbDB(dbname=args.dbname, schema=args.schema) as db:
        disc = discover(db, args.schema)
    logger.info(
        "Discovered %s policy_handling_jobs, %s sign_reader_jobs, "
        "%s curb_segment_jobs.",
        len(disc.policy_jobs),
        len(disc.sign_jobs),
        len(disc.segment_jobs),
    )

    check_guard(results)
    check_fix1_reads(results, disc, args.dbname, args.schema)
    check_fix2(results, disc, args.dbname, args.schema)

    print_summary(results)
    if results.ok:
        logger.info("ALL CHECKS PASSED")
        sys.exit(0)
    logger.error("SOME CHECKS FAILED")
    sys.exit(1)


if __name__ == "__main__":
    main()
