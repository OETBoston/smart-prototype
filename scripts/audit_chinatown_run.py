"""Read-only reconciliation of the explicitly selected Chinatown run."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image
from run_chinatown_stage import ROOT, query


def audit(run_dir: Path) -> dict:
    """Check frozen source identity, usable local photos and spatial output."""
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    stages = manifest["stages"]
    asset_job = stages["sign_loader"]["job_id"]
    segment_job = stages["curb_segmenter"]["job_id"]
    jobs = stages["curb_segmenter"]["config"]["source_jobs"]
    frozen = manifest["survey_preflight"]
    hashes_match = all(
        hashlib.sha256((run_dir / "survey" / name).read_bytes()).hexdigest() == digest
        for name, digest in frozen["sha256"].items()
    )
    expected = set(json.loads((run_dir / "survey/expected_sign_ids.json").read_text()))
    rows = query(
        "SELECT s.source_sign_id, s.sign_type_code, a.source_location_id, "
        "ST_X(a.location), ST_Y(a.location) FROM chinatown_cds.signs s "
        "JOIN chinatown_cds.asset_locations a "
        "ON a.asset_location_id=s.sign_location_id "
        "WHERE s.job_id=%s AND a.job_id=%s",
        (asset_job, asset_job),
    )
    parents = {
        p["attributes"]["globalid"].strip("{}").lower(): p["geometry"]
        for p in json.loads((run_dir / "survey/parents.json").read_text())
    }
    location_changes = [
        sid
        for sid, _, parent, x, y in rows
        if abs(parents[parent]["x"] - x) > 1e-9 or abs(parents[parent]["y"] - y) > 1e-9
    ]
    image_rows = query(
        "SELECT i.sign_id::text, i.uri FROM chinatown_cds.images i "
        "JOIN chinatown_cds.signs s USING (sign_id) WHERE s.job_id=%s",
        (asset_job,),
    )
    unreadable_images = []
    for sign, uri in image_rows:
        try:
            with Image.open(uri) as photo:
                photo.verify()
        except (OSError, ValueError) as error:
            unreadable_images.append({"sign_id": sign, "reason": type(error).__name__})
    missing = query(
        "SELECT s.source_sign_id FROM chinatown_cds.signs s WHERE s.job_id=%s "
        "AND NOT EXISTS (SELECT 1 FROM chinatown_cds.images i "
        "WHERE i.sign_id=s.sign_id)",
        (asset_job,),
    )
    segments, blockfaces, invalid = query(
        "SELECT count(*), count(DISTINCT blockface_id), count(*) FILTER (WHERE "
        "geography IS NULL OR ST_IsEmpty(geography) OR NOT ST_IsValid(geography) "
        "OR GeometryType(geography) <> 'LINESTRING') "
        "FROM chinatown_cds.curb_segments WHERE job_id=%s",
        (segment_job,),
    )[0]
    sequence_errors = query(
        "SELECT blockface_id::text FROM chinatown_cds.curb_segments WHERE job_id=%s "
        "GROUP BY blockface_id HAVING min(segment_seq) <> 0 "
        "OR max(segment_seq) <> count(*)-1 OR count(DISTINCT segment_seq) <> count(*)",
        (segment_job,),
    )
    uncovered = query(
        "SELECT b.blockface_id::text FROM chinatown_cds.curb_blockfaces b "
        "WHERE b.job_id=%s AND NOT EXISTS (SELECT 1 FROM chinatown_cds.curb_segments s "
        "WHERE s.job_id=%s AND s.blockface_id=b.blockface_id)",
        (jobs["blockface_creator"], segment_job),
    )
    baseline = json.loads((run_dir / "database_preflight.json").read_text())
    prior_jobs = [j["job_id"] for j in baseline["jobs"]["curb_segment_jobs"]]
    excluded_details = query(
        "SELECT b.blockface_id::text, ST_Length(ST_Transform(b.geography,2249)), "
        "EXISTS (SELECT 1 FROM chinatown_cds.curb_segments s WHERE "
        "s.blockface_id=b.blockface_id AND s.job_id::text=ANY(%s)) "
        "FROM chinatown_cds.curb_blockfaces b WHERE b.blockface_id::text=ANY(%s)",
        (prior_jobs, [r[0] for r in uncovered]),
    )
    tiny_threshold = stages["curb_segmenter"]["config"]["tiny_seg_threshold_ft"]
    unexpected_uncovered = [
        key
        for key, length, previously_present in excluded_details
        if length >= tiny_threshold or previously_present
    ]
    unsnapped = query(
        "SELECT a.source_location_id, a.job_id::text, d.distance_ft "
        "FROM chinatown_cds.asset_locations a CROSS JOIN LATERAL ("
        "SELECT min(ST_Distance(ST_Transform(a.location,2249), "
        "ST_Transform(b.geography,2249))) AS distance_ft "
        "FROM chinatown_cds.curb_blockfaces b WHERE b.job_id=%s) d "
        "WHERE a.job_id::text = ANY(%s) AND d.distance_ft > 30 ORDER BY a.job_id",
        (
            jobs["blockface_creator"],
            [asset_job, jobs["fire_hydrant"], jobs["bus_stop"]],
        ),
    )
    result = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "frozen_hashes_match": hashes_match,
        "source_ids_exact_match": len(rows) == len(expected)
        and {r[0] for r in rows} == expected,
        "signs": len(rows),
        "locations_changed_since_freeze": location_changes,
        "images": len(image_rows),
        "unreadable_images": unreadable_images,
        "missing_attachment_source_ids": [r[0] for r in missing],
        "excluded_driveways": frozen["excluded_driveways"],
        "segments": segments,
        "represented_blockfaces": blockfaces,
        "invalid_segments": invalid,
        "segment_sequence_errors": sequence_errors,
        "uncovered_blockfaces": [r[0] for r in uncovered],
        "preexisting_tiny_blockface_exclusions": [
            {"blockface_id": key, "length_ft": length}
            for key, length, _ in excluded_details
            if key not in unexpected_uncovered
        ],
        "unexpected_uncovered_blockfaces": unexpected_uncovered,
        "unsnapped_locations": [
            dict(zip(("source_location_id", "job_id", "distance_ft"), row, strict=True))
            for row in unsnapped
        ],
    }
    if "sign_reader" in stages:
        reader = stages["sign_reader"]["job_id"]
        result["reader"] = dict(
            zip(
                ("policy_rows", "distinct_signs", "unusable_policy_rows"),
                query(
                    "SELECT count(*), count(DISTINCT p.sign_id), count(*) FILTER "
                    "(WHERE p.policy_json::text LIKE '%%unusable image%%') "
                    "FROM chinatown_cds.sign_policies p "
                    "JOIN chinatown_cds.signs s USING(sign_id) "
                    "WHERE p.job_id=%s AND s.job_id=%s",
                    (reader, asset_job),
                )[0],
                strict=True,
            )
        )
        if result["reader"]["distinct_signs"] != len(expected):
            raise ValueError("Reader output does not account for every selected sign")
        unrelated = query(
            "SELECT count(*) FROM chinatown_cds.sign_policies p "
            "JOIN chinatown_cds.signs s USING(sign_id) "
            "WHERE p.job_id=%s AND s.job_id<>%s",
            (reader, asset_job),
        )[0][0]
        if unrelated:
            raise ValueError("Reader output includes a different asset job")
        result["reader"]["unrelated_asset_policies"] = unrelated
    if "policy_applier" in stages:
        policy_job = stages["policy_applier"]["job_id"]
        counts = query(
            "SELECT count(*), count(DISTINCT p.segment_id), "
            "count(*) FILTER (WHERE s.job_id IS DISTINCT FROM %s), "
            "count(*) FILTER (WHERE p.policy_list::text LIKE '%%unusable image%%') "
            "FROM chinatown_cds.curb_segment_policies p "
            "LEFT JOIN chinatown_cds.curb_segments s USING(segment_id) "
            "WHERE p.job_id=%s",
            (segment_job, policy_job),
        )[0]
        result["policy_applier"] = dict(
            zip(
                (
                    "rows",
                    "distinct_segments",
                    "unrelated_segments",
                    "segments_needing_image_review",
                ),
                counts,
                strict=True,
            )
        )
        if counts[0] != counts[1] or counts[2]:
            raise ValueError(
                "Policy output duplicates segments or mixes segmentation jobs"
            )
        result["policy_applier"]["segments_without_policy_output"] = (
            segments - counts[1]
        )
    (run_dir / "run_quality_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    manifest["quality_audit"] = result
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    if (
        not hashes_match
        or not result["source_ids_exact_match"]
        or location_changes
        or unreadable_images
        or invalid
        or sequence_errors
        or unexpected_uncovered
    ):
        raise ValueError("Run audit failed; inspect run_quality_audit.json")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir", type=Path, default=ROOT / "output/chinatown_run_20260923"
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    report = audit(args.run_dir)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "unsnapped_locations"}, indent=2
        )
    )
