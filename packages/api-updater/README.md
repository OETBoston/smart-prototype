# API Update Logic

The `api_update` package handles the ingestion, processing, and synchronization of curb regulations from staging tables into the public-facing API database (CDS format).

The process is orchestrated by `core.py` and consists of three main phases: Data Acquisition, Data Transformation, and Data Export. `prepare_api_update` returns the proposed tables without publishing them; `api_updater` prepares and exports them.

## Overview and Configuration

Runtime parameters are specified in `config.yaml`. 
See the [default config file](./src/api_updater/config.yaml) for details.

## Usage

From the project root, run:

```sh
uv run python -m api_updater
# Or select a dedicated configuration:
uv run python -m api_updater --config configs/chinatown/api_updater.yaml
```

## 1. Data Acquisition (`extractor.py`)

The pipeline connects to the database and pulls data from two distinct schemas:

- **Staging Data (`staging_db_schema`):**
  - Reads `curb_segments` and `curb_segment_policies`.
  - Both `source_jobs.curb_segmenter` and `source_jobs.policy_handler` must select explicit job IDs. Unfiltered historical jobs can duplicate policies.
- **API Data (`api_db_schema`):**
  - Reads the current state of the CDS API tables: `curb_zones` (filtered to active zones where `end_date IS NULL`), `curb_policies`, `curb_zone_policies`, `curb_policy_rules`, `curb_policy_time_spans`, and `curb_policy_rates`.

## 2. Data Transformation (`transformer.py`)

The `transform_policy_updates` function performs the core logic. The process includes deduplication, spatial change detection, and relationship mapping.

### Pre-processing Existing Data

- Constructs a canonical JSON representation of each existing policy and its sub-elements (rules, time spans, rates) via `get_policy_json`.
- Generates a unique hash `signature` for each existing policy via `get_policy_signatures`.

### Pre-processing Staging Data

- Consolidates the staging curb segments and their associated policies into a unified dataframe (`consolidate_curb_segments`).
- **Flattening:** Un-nests the `policy_list` using `explode()` and extracts unique policies from the nested JSON structures (`extract_unique_policies`). It creates a mapping between `curb_zone_id` and the policy JSONs.
- Generates canonical JSON and hash `signatures` for the new policies so they can be compared against the existing database state.

### Deduplication (Signature Matching)

- Compares the hash signatures of newly extracted policies against the signatures of existing policies in the API data.
- If a new policy has a signature identical to an existing one, the newly created policy and its sub-elements are discarded.
- The new curb zone's relationship is instead mapped directly to the _existing_ `curb_policy_id`. This step is crucial to prevent database bloat from duplicate, identical policies.

### Spatial Processing & Change Detection

A spatial join (`gpd.sjoin` with `intersects` predicate) is performed between the new curb zones and the existing active curb zones to determine how to update records. It strictly checks intersections that result in `LineString` or `MultiLineString` geometries.

1.  **Exact Geometry Match & Exact Policy Match:**
    - The existing zone is kept.
    - The `last_updated_date` is refreshed to the current run time.
    - The "new" zone record is discarded.
2.  **Exact Geometry Match & Different Policies:**
    - The existing zone geometry is kept and its `last_updated_date` is updated.
    - The old policy associations (`curb_zone_policies`) for this zone are marked for expiration.
    - The new policies are mapped to the existing `curb_zone_id`.
    - The "new" zone record is discarded.
3.  **Different Geometries (Spatial Overlap/Intersection):**
    - The old zone is retired (its `end_date` and `last_updated_date` are set to the current run time).
    - The old policy associations are marked for expiration.
    - The new zone (with its new geometry and new `curb_zone_id`) is inserted as an entirely new active zone.

### Cleanup & Enhancements

- **Orphan Removal:** The logic filters all policy elements to ensure that only policies actually linked to an active `curb_zone_id` (either new or existing) are retained. Orphan policies, rules, time spans, and rates are discarded.
- **AI Policy Descriptions:** After deduplication and active-policy filtering, the pipeline fills null, blank, and generator-placeholder descriptions for both new and reused policies. Valid text and policy IDs are preserved. The Gemini prompt includes schedules, exceptions and rates; inspect generated wording before publication. An empty or failed response stops the update. A complete description set makes no Gemini calls.
- **Final Assembly:** Uses `pd.concat` to merge new and old dataframes together, ready for export.

## 3. Data Export (`exporter.py`)

The processed datasets are converted into an export dictionary mapping table names to their respective dataframes and primary keys. They are then exported to two destinations:

- **Local CSV Backup (`export_to_csv`):**
  - Intermediate tables are saved to the local `output/` directory for debugging, tracking, and backup. Empty dataframes are gracefully skipped.
- **Database Upsert (`export_to_db`):**
  - All related writes use one `SmartCurbDB` transaction. Failure rolls back the entire export. Removed associations are deleted before their replacements are inserted, including policies retained on a changed zone.
  - **Appends:** New zone-policy mappings are added (`append_data`).
  - **Deletions:** Expired zone-policy mappings are removed (`delete`).
  - **Upserts:** Core tables (`curb_zones`, `curb_policies`, `curb_policy_rules`, `curb_policy_time_spans`, `curb_policy_rates`) use an `update_or_append` logic based on their primary keys to insert new rows and update modified ones (such as setting an `end_date` for retired zones).

See the [Chinatown runbook](../../docs/chinatown_refresh.md) for the frozen source, reviewed publication workflow and current run status.
