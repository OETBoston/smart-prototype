"""Idempotent upsert of staging_next policy CSVs into Postgres.

Reads the policy CSV exports and upserts them into their matching tables in the
target schema using ``SmartCurbDB.update_or_append`` (``INSERT ... ON CONFLICT
DO UPDATE``). Re-running the script is safe: rows are matched on their primary
keys, so existing records are updated in place and new records are inserted.

Usage:
    uv run python scripts/load_staging_policies.py
    uv run python scripts/load_staging_policies.py --only sign_policies
    uv run python scripts/load_staging_policies.py --schema staging --dbname cds

Pass ``--replace`` to first delete existing rows for the job_id(s) present in each
CSV (within the same transaction as the upsert), so the table exactly matches the
file for those jobs rather than retaining stale rows:

    uv run python scripts/load_staging_policies.py --replace
"""

import argparse
from pathlib import Path

import pandas as pd
from curb_utils.db_utils import SmartCurbDB
from curb_utils.logging import get_logger
from dotenv import load_dotenv
from sqlalchemy import text

logger = get_logger(__name__)

# scripts/<this file> -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUTS_DIR = REPO_ROOT / "inputs" / "staging_next"

# table name -> (csv filename, primary-key columns used to match existing rows)
UPSERT_SPECS: dict[str, tuple[str, list[str]]] = {
    "sign_policies": ("sign_policies.csv", ["sign_policy_id"]),
    "curb_segment_policies": ("curb_segment_policies.csv", ["segment_id", "job_id"]),
}


def load_csv(path: Path) -> pd.DataFrame:
    """Load a policy CSV with values preserved as strings.

    UUID and JSON columns are kept as raw strings (which is what the jsonb upsert
    expects), and empty cells are converted to ``None`` so they are written as SQL
    ``NULL`` rather than empty strings. This matters for the ``policy_arrow`` CHECK
    constraint, which only permits 'left', 'right', 'both', or NULL.
    """
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {path}")

    df = pd.read_csv(path, dtype=str)
    # pandas reads empty cells as NaN even with dtype=str; convert them to None.
    return df.where(pd.notnull(df), None)


def _replace_jobs(db: SmartCurbDB, table: str, df: pd.DataFrame) -> None:
    """Delete existing rows whose ``job_id`` appears in ``df``.

    Runs on the same connection/transaction as the subsequent upsert, so the
    delete and re-insert commit atomically. This makes the table exactly match
    the CSV for the file's job(s) instead of leaving behind stale rows for
    segments/policies that were removed in the new export.
    """
    if "job_id" not in df.columns:
        logger.warning(
            "--replace requested but %s has no job_id column; skipping delete.", table
        )
        return

    job_ids = sorted({j for j in df["job_id"].tolist() if j is not None})
    if not job_ids:
        logger.warning("--replace requested but no job_id values found for %s.", table)
        return

    assert db.connection is not None
    result = db.connection.execute(
        text(f"DELETE FROM {db.schema}.{table} WHERE job_id::text = ANY(:job_ids)"),
        {"job_ids": job_ids},
    )
    logger.info(
        "Replace mode: deleted %s existing row(s) from %s for job_id(s): %s",
        result.rowcount,
        table,
        ", ".join(job_ids),
    )


def upsert_table(
    db: SmartCurbDB,
    table: str,
    df: pd.DataFrame,
    key_columns: list[str],
    replace: bool = False,
) -> None:
    """Deduplicate on the key columns and upsert the dataframe into ``table``.

    When ``replace`` is True and the data has a ``job_id`` column, existing rows
    for the job_id(s) present in the CSV are deleted first (within the same
    transaction as the upsert).
    """
    row_count = len(df)
    df = df.drop_duplicates(subset=key_columns, keep="last")
    dropped = row_count - len(df)
    if dropped:
        logger.warning(
            "Dropped %d duplicate row(s) on key %s for table %s",
            dropped,
            key_columns,
            table,
        )

    if replace:
        _replace_jobs(db, table, df)

    logger.info("Upserting %d row(s) into %s ...", len(df), table)
    db.update_or_append(table, df, key_columns=key_columns)
    logger.info("Finished upserting %d row(s) into %s", len(df), table)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dbname",
        default="cds",
        help="Target Postgres database name (default: cds).",
    )
    parser.add_argument(
        "--schema",
        default="staging_next",
        help="Target schema (default: staging_next).",
    )
    parser.add_argument(
        "--inputs-dir",
        type=Path,
        default=DEFAULT_INPUTS_DIR,
        help="Directory containing the policy CSV files.",
    )
    parser.add_argument(
        "--only",
        choices=sorted(UPSERT_SPECS),
        help="Upsert only the named table instead of all of them.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Before upserting, delete existing rows whose job_id appears in the CSV "
            "so the table exactly matches the file for those job(s). Only affects "
            "tables that have a job_id column."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Load each policy CSV and upsert it into its corresponding table."""
    args = parse_args()
    load_dotenv()

    if args.only:
        specs = {args.only: UPSERT_SPECS[args.only]}
    else:
        specs = UPSERT_SPECS

    for table, (filename, key_columns) in specs.items():
        csv_path = args.inputs_dir / filename
        logger.info("Loading %s -> %s.%s", csv_path, args.schema, table)
        df = load_csv(csv_path)

        # Each table is upserted in its own connection/transaction so that one
        # file's success is not lost if a later file fails.
        with SmartCurbDB(dbname=args.dbname, schema=args.schema) as db:
            upsert_table(db, table, df, key_columns, replace=args.replace)

    logger.info("All upserts complete.")


if __name__ == "__main__":
    main()
