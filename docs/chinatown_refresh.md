# Chinatown refresh: September 23, 2026

Target: project `smart-grant-460018`, Cloud SQL instance `dev`, database `cds`, schema `chinatown_cds`. The connected PostgreSQL server's private address matched the instance (`10.119.0.3`). The existing user tunnel on localhost:5432 was used.

## Completed and pending

- Imported all 550 eligible signs at 457 locations, with 549 readable photos. The selection preserves all 325 previous survey signs and adds 225. Previous jobs remain in place.
- Created 1,480 segments covering 527 blockfaces. Two additional blockfaces, 1.20 and 1.38 feet long, were also excluded by the previous run; the existing tiny-segment rule removes unanchored blockfaces under three feet.
- Restored 162 existing policy descriptions and verified them through the deployed Chinatown API. Policy IDs, rules, schedules, rates, zones and associations were preserved. A repeated preparation required zero generation calls.
- With explicit user approval, interpreted all 549 photos through Gemini with no service/parsing failures. The reader accounts for all 550 signs, including the missing-photo review marker. Raw and reviewed jobs are retained separately.
- Published the reviewed refresh in one transaction. The deployed API returns 1,248 active zones and 172 active policies, all with descriptions. Of these, 154 policies retain their existing IDs and text; 18 new descriptions were reviewed. There are 71 new zones, 36 retired zones, and 121 existing zones with changed policy relationships; 1,177 existing zone IDs remain active.
- Verified five refreshed locations through both API endpoints. A read-only rerun preserved every active zone/policy ID and description, produced no relationship changes, and made zero Gemini calls.
- Frontend map display/routing remains unverified: no map URL was provided and the in-app browser had no available connection. Backend/API publication is complete.
- Curb-cut implementation remains a separate follow-up with the prerequisites below.

Evidence is in the ignored local directory `output/chinatown_run_20260923/`. `run_manifest.json` records exact completed jobs, configurations, source hashes and exceptions. These artifacts and photos are not committed.

## Source selection and exceptions

The source is the configured Survey123 feature service, parent layer 0 (`Form_2`) and repeat layer 1 (`sign_repeat`):

`https://services.arcgis.com/sFnw0xNflSi8J0uh/arcgis/rest/services/service_80d5dd0ee96e40f98b991a3234dabe00/FeatureServer`

Survey123 does not apply the loader's generic geographic filter. The dedicated loader instead uses the frozen parent-GlobalID allowlist in `survey/parent_globalids.csv`. The selection is the union of the City's Chinatown polygon and the previous Chinatown survey footprint, whose bounding box is `[-71.06576836197875, 42.34744825733924, -71.05842118766655, 42.35262167323814]`. A strict polygon would have omitted 104 previously imported signs. No legacy sign sources were merged.

Boundary source: [Boston basemap neighborhood layer 17](https://gis.boston.gov/arcgis/rest/services/Basemaps/basemap_IPS/MapServer/17). `survey/selection_geometry.geojson`, `parents.json`, `repeats.json`, `expected_sign_ids.json`, and `survey_preflight.json` preserve geometry, records, counts and SHA-256 hashes. The selected source dates extend through July 15, 2026.

Reconciliation found:

- Exact imported source-ID match; no parent location changed between freeze and import.
- No driveway records in this selection. The dedicated loader excludes driveway sign types from interpretation.
- One source record has no attachment: sign `1c2360ce-a838-4919-badb-fd2887cbf5b3`, repeat object ID 649, parent `fed295dc-9556-46c3-9252-0405ceabed52`. The repeat attachment inventory confirms the gap. This sign received the existing `unusable image` review policy; no restriction was inferred from its type label or a sibling's photo.
- Seventeen survey locations and 29 hydrants exceed the unchanged 30-foot snap tolerance. Bus stops and meters snapped successfully. Details are in `run_quality_audit.json`; missing attachments are in `survey/missing_attachments.json`.
- No invalid segment geometry or sequence errors, and no unexplained blockface loss.

Photo review covered all 30 changed existing sign interpretations, a systematic sample of newly added signs, and source examples of newly introduced policy patterns. Corrections or review flags were applied to 34 source signs in two separate reviewed jobs, preserving raw Gemini output. Examples include omitted seasonal months, inferred bicycle exemptions, incorrect arrows, cropped schedules, idling misclassified as stopping, and named patient/agency reservations that the current schema cannot express. This was not an exhaustive human audit of every photo.

The final reader has 77 review-marker policy rows across 76 distinct signs, including the missing attachment. The existing `unusable image` marker covers unreadable/incomplete images and unsupported interpretations; it is not a new regulation. `signs_needing_review.csv`, `sign_review_corrections.json`, and `sign_review_additional.json` retain source IDs, photos, reasons, and before/after evidence. Review markers reach 316 staging segments. The 17 unsnapped survey locations represent 21 signs, separately listed in `unsnapped_sign_ids.json`.

## Publication isolation and backup

The initial Chinatown schema exposed API views directly over the latest staging job and had no API base tables. That would publish intermediate jobs before review and could not store descriptions. `scripts/prepare_chinatown_api.py` created the API tables and seeded the original 1,213 zones and 162 policies, preserving their IDs, dates and view content. Both views were changed in one transaction to read these tables. The dry run rolled back successfully; the applied migration verified identical API content. Native `TEXT[]` storage for `designated_period` preserves Chinatown's existing JSON-array response.

Before any database writes, PostgreSQL 18 `pg_dump` created `chinatown_before.dump`, a custom-format backup of the complete schema and its data. `pg_restore --list` validated the archive; see `backup_contents.txt` and `backup.json`. SHA-256:

`f556fa1b58999d8fad61a241371280c6ead505a1163213ffd95cd5329fae3b48`

A second archive, `chinatown_before_final_publication.dump`, preserves all completed staging jobs and the restored descriptions immediately before the final export. It is 1,083,430 bytes; SHA-256 `85bc0e5997f4d96e0c7df64bc14290a4816757e6b610675921ac1046009e9696`. Its archive listing also passed. See `before_final_publication_backup.json`.

For recovery, restore the archive into an isolated PostgreSQL 18/PostGIS database first and compare the affected records before applying a scoped repair. A full schema replacement would discard the new append-only jobs. No restore into the live schema has been attempted.

## Exact jobs and stage sequence

| Input or stage | Job ID |
| --- | --- |
| Blockfaces | `e7ff4630-94dd-4098-aad6-aec7f7c3a12d` |
| Hydrants | `e9e630af-2e20-4221-873a-890bb3477646` |
| Bus stops | `223c3644-f0cd-4d28-877b-8ffa056cc2fe` |
| Meters | `65fe0581-a94c-4d00-afb0-a12460ee898d` |
| New survey import | `21375052-7829-4715-b1f9-9e0e490986ca` |
| New segmentation | `5ec9b7af-2126-4136-94df-d66891c6c28c` |
| Raw Gemini reader | `2d001150-a59c-4d76-947f-917b6e86b8da` |
| Final reviewed reader | `349c2cdc-5c77-4b3f-9c16-1d4c88724e93` |
| Final policy application | `525262a4-24d6-4ba9-8174-5515d50175d7` |

Configurations are in `configs/chinatown/`. Completed stages pin downstream inputs to their exact new job IDs. The reader used `gemini-3.1-flash-lite-preview` for preprocessing and `gemini-3-flash-preview` for interpretation, with concurrency 10. Description generation used `gemini-3.1-flash-lite-preview`, with concurrency five. Configurations and description prompt hashes are recorded with the review artifacts. Superseded processing jobs remain in the manifest and database.

The following sequence documents the completed run; do not repeat completed stages in this run directory. From the repository root:

```powershell
.venv/Scripts/python.exe scripts/run_chinatown_stage.py sign_reader
.venv/Scripts/python.exe scripts/audit_chinatown_run.py
.venv/Scripts/python.exe scripts/run_chinatown_stage.py policy_applier
.venv/Scripts/python.exe scripts/publish_chinatown.py prepare
```

Inspect `publication_review.json`, `publication_descriptions_review.csv`, and `publication_preview_*.csv` against the source and previous API snapshots. Check new restrictions, unusable-image policies, unsnapped assets, overlaps, and policy/zone differences before publishing:

```powershell
.venv/Scripts/python.exe scripts/publish_chinatown.py publish
.venv/Scripts/python.exe scripts/publish_chinatown.py verify
```

Preparation writes a local artifact containing exact proposed UUIDs, timestamps, geometries and descriptions. Publication checks its hash and fingerprints of all six existing API tables, validates relationships, and exports in one transaction. A database change after preparation requires a fresh review. The serialized artifact must remain local and trusted.

The stage wrapper rejects completed stages and unrecorded jobs with the same run name. If a reader fails after writing batches, inspect the partial job, choose a new run-specific job name, and keep `re_process: true` so the replacement job accounts for the complete snapshot. Do not select a partial job downstream. The top-level runner is insufficient because it omits loading and API publication.

For a future source refresh, use a new run directory, re-freeze the selection with `scripts/chinatown_preflight.py --include-existing-footprint`, and update the dedicated configuration's allowlist and image paths before importing. Do not overwrite this run's source evidence.

## Description validation

Missing means null, blank, or a known generator placeholder. After deduplication, both new and reused active policies are eligible. Existing valid text is preserved. Empty responses and generation errors abort preparation; complete descriptions avoid initializing Gemini.

Review of the original prompt found reversed user exceptions and omitted calendar details. The prompt now preserves exception direction, calendar conditions and rates. Four generated sentences were clarified during review without changing structured rules; the exact edits and artifact hash are in `description_backfill_review.json`. All supplied time intervals and rate amounts were checked. Rates follow the [CDS cents convention](https://github.com/openmobilityfoundation/curb-data-specification/blob/main/curbs/README.md#rate).

The independent restoration used `publish_chinatown.py prepare --descriptions-only`, then `publish --descriptions-only`. The resulting API returned 162 descriptions and the original 1,213 zones. Evidence: `description_backfill_validation.json`, `description_backfill_publish.log`, and `api_*_before_full_refresh.json`. The final publication snapshots are `api_policies_after.json` and `api_zones_after.json`; they include 36 retired zones and eight historical policies in addition to the active records.

API used: [Chinatown policies](https://smart-curb-api-dev-cln5x3g7hq-uk.a.run.app/curbs/policies?schema=chinatown_cds). Cloud Run's development API has schema override enabled and connects to the verified Cloud SQL instance. The map frontend URL was not available; browser rendering and routing to this endpoint remain unverified.

Local validation: 96 relevant tests passed. Coverage includes description preservation/failure/no-op cases, deduplication, retained policy associations, transaction rollback, API identity/description verification, mixed UUID/string database readers, spatial rounding and adjacent-zone preservation, optional configuration arguments, token-safe ArcGIS errors, and sign/meter segmentation. A live PostgreSQL check verified that a failed relationship write rolled back a preceding policy write, with all six table fingerprints unchanged (`live_rollback_validation.json`). Five refreshed location queries passed (`refreshed_location_api_checks.json`), as did the completed publication's read-only rerun (`publication_rerun_validation.json`).

Spatial review exposed exact-intersection comparisons retaining old zones after tiny reprojection differences. Comparisons now use a one-millimeter local metric tolerance and exclude shared endpoints/crossings. The final active zones total 155,292.888631 feet, matching the staging coverage; there are no detected overlaps above 0.01 feet. Evidence: `publication_spatial_review.json`. Review and publication also normalize UUID values across the two database readers without changing exported IDs.

The endpoint-row repair uses named columns so additional snapping metadata does not break segmentation. The existing fixture's geometry comparison now honors its numeric tolerance (the observed differences were below 0.000000005 feet).

## Curb-cut follow-up

First confirm the authoritative source, driveway versus pedestrian-ramp meaning, curb extent/width, restriction, and priority. Do not copy hydrant distances or policies without those decisions.

Hydrants affect both segmentation and policy application. The follow-up should:

1. Load a distinct feature type in `asset_locations` and `nonsign_features`, with its own source job.
2. Extend optional asset/job configuration in `curb_segmenter/config.py` and asset loading in `io_utils.py`.
3. Adapt snapping and segmentation in `curb_segmentation.py` to the confirmed width and geometry; extend segment ordering, boundary-location lists and tiny-segment handling.
4. Add the confirmed policy to `policy_applier/handler_utils/policy_defaults.py` and the corresponding start/end events in `handler.py`.
5. Verify policy identity, descriptions and relationships through API export. Cover overlapping features, curb ends, short segments, unsnapped features and unchanged results with curb cuts disabled.

No curb-cut behavior was added to this refresh.
