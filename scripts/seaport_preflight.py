"""Validate the Seaport Survey123 export against the live service without DB writes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
SIGN_LOADER_SRC = REPO_ROOT / "packages" / "sign-loader" / "src" / "sign_loader"
sys.path.insert(0, str(SIGN_LOADER_SRC))

from survey123 import _normalize_guid, load_survey123  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _column(rows: list[dict[str, str]], requested: str) -> str:
    if not rows:
        raise ValueError("CSV contains no data rows")
    columns = {name.casefold(): name for name in rows[0]}
    try:
        return columns[requested.casefold()]
    except KeyError as exc:
        raise ValueError(
            f"CSV column {requested!r} is missing; available={list(rows[0])}"
        ) from exc


def _guid_set(rows: list[dict[str, str]], column: str) -> set[str]:
    normalized = {_normalize_guid(row[column]) for row in rows}
    if None in normalized:
        raise ValueError(f"CSV column {column!r} contains an invalid UUID")
    return {value for value in normalized if value is not None}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-csv", type=Path, required=True)
    parser.add_argument("--repeat-csv", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "packages" / "sign-loader" / "config.yaml",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-parents", type=int, default=128)
    parser.add_argument("--expected-repeats", type=int, default=143)
    parser.add_argument("--expected-attachments", type=int, default=143)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(REPO_ROOT / ".env")
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))

    parent_rows = _read_csv(args.parent_csv)
    repeat_rows = _read_csv(args.repeat_csv)
    parent_gid_column = _column(parent_rows, "GlobalID")
    repeat_gid_column = _column(repeat_rows, "GlobalID")
    repeat_parent_column = _column(repeat_rows, "ParentGlobalID")
    sign_type_column = _column(repeat_rows, "Select the type of sign")

    export_parent_ids = _guid_set(parent_rows, parent_gid_column)
    eligible_rows = [
        row
        for row in repeat_rows
        if row[sign_type_column].strip().casefold() != "driveway"
    ]
    eligible_repeat_ids = _guid_set(eligible_rows, repeat_gid_column)
    eligible_parent_ids = _guid_set(eligible_rows, repeat_parent_column)
    missing_export_parents = eligible_parent_ids - export_parent_ids

    if len(parent_rows) != args.expected_parents or len(export_parent_ids) != len(
        parent_rows
    ):
        raise ValueError(
            "Parent export reconciliation failed: "
            f"rows={len(parent_rows)}, unique={len(export_parent_ids)}, "
            f"expected={args.expected_parents}"
        )
    if len(eligible_rows) != args.expected_repeats or len(eligible_repeat_ids) != len(
        eligible_rows
    ):
        raise ValueError(
            "Eligible repeat export reconciliation failed: "
            f"rows={len(eligible_rows)}, unique={len(eligible_repeat_ids)}, "
            f"expected={args.expected_repeats}"
        )
    if missing_export_parents:
        raise ValueError(
            "Eligible repeats reference missing export parents: "
            f"{missing_export_parents}"
        )

    base_path = REPO_ROOT / "packages" / "sign-loader"
    live_signs = load_survey123(config=config, base_path=base_path)
    live_repeat_ids = set(live_signs["source_sign_id"])
    live_parent_ids = set(live_signs["source_location_id"])
    attachment_counts = live_signs["attachments"].map(len)
    attachment_total = int(attachment_counts.sum())
    image_paths = [
        Path(attachment["uri"])
        for attachments in live_signs["attachments"]
        for attachment in attachments
    ]

    if live_repeat_ids != eligible_repeat_ids:
        raise ValueError(
            "Live repeat IDs do not exactly equal eligible export repeat IDs: "
            f"missing={sorted(eligible_repeat_ids - live_repeat_ids)}, "
            f"unexpected={sorted(live_repeat_ids - eligible_repeat_ids)}"
        )
    if len(live_signs) != args.expected_repeats:
        raise ValueError(
            f"Expected {args.expected_repeats} live signs, got {len(live_signs)}"
        )
    if (
        attachment_total != args.expected_attachments
        or not attachment_counts.eq(1).all()
    ):
        raise ValueError(
            "Attachment reconciliation failed: "
            f"total={attachment_total}, per_sign_counts="
            f"{attachment_counts.value_counts().to_dict()}"
        )
    missing_images = [str(path) for path in image_paths if not path.is_file()]
    non_jpeg_images = [
        str(path)
        for path in image_paths
        if path.suffix.casefold() not in {".jpg", ".jpeg"}
    ]
    if missing_images or non_jpeg_images:
        raise ValueError(
            f"Image validation failed: missing={missing_images}, "
            f"non_jpeg={non_jpeg_images}"
        )
    if live_signs["sign_type_code"].fillna("").str.casefold().eq("driveway").any():
        raise ValueError("A driveway record survived the live importer exclusion")

    result = {
        "status": "passed",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "inputs": {
            "parent_csv": str(args.parent_csv.resolve()),
            "parent_csv_sha256": _sha256(args.parent_csv),
            "repeat_csv": str(args.repeat_csv.resolve()),
            "repeat_csv_sha256": _sha256(args.repeat_csv),
            "allowlist_csv": str(
                (
                    REPO_ROOT / config["survey123"]["parent_allowlist"]["csv_path"]
                ).resolve()
            ),
            "allowlist_csv_sha256": _sha256(
                REPO_ROOT / config["survey123"]["parent_allowlist"]["csv_path"]
            ),
        },
        "export_counts": {
            "parents": len(parent_rows),
            "unique_parent_ids": len(export_parent_ids),
            "repeat_rows": len(repeat_rows),
            "excluded_driveways": len(repeat_rows) - len(eligible_rows),
            "eligible_repeats": len(eligible_rows),
            "eligible_locations": len(eligible_parent_ids),
        },
        "live_reconciliation": {
            "parents_exactly_matched_to_allowlist": len(export_parent_ids),
            "eligible_repeats": len(live_signs),
            "eligible_locations": len(live_parent_ids),
            "attachments": attachment_total,
            "attachments_per_sign": {
                str(key): int(value)
                for key, value in attachment_counts.value_counts().sort_index().items()
            },
            "jpeg_attachments": len(image_paths),
            "driveways": 0,
            "source_repeat_ids_exact_match": True,
        },
        "artifacts": {
            "image_directory": str(image_paths[0].parent) if image_paths else None,
            "downloaded_image_files": len(image_paths),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
