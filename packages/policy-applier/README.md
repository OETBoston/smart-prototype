# Smart Curb Policy Handling

This module provides a pipeline for policy assignment for curb segments based on physical curb assets.
`main.py` is the main entry point for running the pipeline. 

## Usage

### Command-Line Policy Assignment
Process curb segment data and assign policies programmatically. Two arguments are required:

```sh
python main.py [--job-id JOB_ID --schema SCHEMA] [--help]
```
- Use `--job-id JOB_ID` to process curb segments created by a specific job ID.
- Use `--schema SCHEMA` to specify the staging database schema for input and output tables.
- Use `--help` to see all available arguments and options.

## Module Structure
- `main.py` — Command-line tool for policy assignment (argument parsing, batch processing)
- `db_utils/` — Database connection and query helpers
- `handler_utils/` — Policy handler logic
- `io_utils/` — Input/output helpers

## Core Logic: In-Depth Policy Assignment

The `policy_applier` module programmatically evaluates physical curb assets and translates them into logical segment-level parking policies. Here is a deep dive into the processing pipeline:

### 1. Data Ingestion & Preparation
The `prepare_location_policies` function consolidates all input sources:
- **Signs**: Merged with their corresponding sign policies.
- **Meters**: Split into `start_asset_location_id` (mapped to `Direction.AWAY`) and `end_asset_location_id` (mapped to `Direction.TOWARD`).
- **Lookups**: Creates `df_geom` to map asset and segment IDs to geometries, and `feature_lookup` to identify non-sign features like fire hydrants and bus stops.

### 2. Blockface Validation
Segments are grouped by `blockface_id` and sorted by `segment_seq`. The `validate_blockface` function ensures:
- The blockface does not have mixed `is_left_side_oneway` values.
- The `segment_seq` is a continuous `0` to `n-1` sequence.

### 3. Event Log Generation
For each blockface, `generate_event_log` processes items sequentially from the upstream location to the downstream location. It generates an ordered sequence of events (`type`, `id`, `policy`, `direction`). Imagine this event log as a timeline of encounters as you drive down the blockface.

When determining direction (`TOWARD` vs. `AWAY`), perspective is relative to driving downstream. Depending on which side of the street the sign is located, the physical arrows translate differently:
- **Right-hand side:** A right-pointing arrow points `TOWARD` you; a left-pointing arrow points `AWAY` from you.
- **Left-hand side:** A right-pointing arrow points `AWAY` from you; a left-pointing arrow points `TOWARD` you.
- **Bidirectional:** A sign with a double arrow ("both" or nan) will always point both `TOWARD` and `AWAY`, regardless of which side of the street it is on.

Based on this perspective, the process translates physical assets into logical events:
- **Directional Translation:** The physical arrow direction ("left", "right", "both") is evaluated against `is_left_side_oneway` to determine the correct logical flow (`Direction.TOWARD` or `Direction.AWAY`).
- **Non-Sign Features:** Fire hydrants and bus stops lack explicit directional policies. Instead, they dynamically inject an `AWAY` event followed immediately by a `TOWARD` event using hardcoded default policies (`FIRE_HYDRANT_POLICY` and `BUS_STOP_POLICY`), creating an isolated restriction zone.

### 4. Projection
The event log is merged with spatial data (`df_geom`). The `GeoDataFrame` is then projected from EPSG:4326 (WGS 84) to EPSG:3395 (World Mercator) to enable accurate linear distance calculations along the curb.

### 5. Forward Pass
The `run_policy_pass` function iterates through the event log from start to finish, maintaining an `active_policies` dictionary (keyed by the policy JSON string):
- **Arrow Events**: An `AWAY` direction activates the policy (adding it to the dictionary), while a `TOWARD` direction deactivates it. This is because encountering an arrow pointing `AWAY` from you means you are *entering* its effective zone, whereas an arrow pointing `TOWARD` you means you are *exiting* the zone.
- **Segment Events**: When a segment is encountered, the script iterates through all currently `active_policies`, extracts the `priority` field from the parsed JSON, and appends a record linking the `segment_id` to the active policy.

### 6. Backward Pass
To account for policies pointing backwards against the flow of the blockface, the event log is completely reversed (`iloc[::-1]`), and the directions are flipped (`TOWARD` -> `AWAY`, `AWAY` -> `TOWARD`). The `run_policy_pass` function is then run again on this reversed log.

### 7. Resolution and Priority Sorting
- The outputs from the Forward and Backward passes are merged. If a policy is found to be active during *either* pass, it applies to the segment. 
- Duplicate policies on the same segment (e.g., a policy that is active in both the forward and backward passes over the same space) are dropped so they are only applied once.
- The merged DataFrame is grouped by segment and sorted strictly by the `priority` field embedded in the policy JSON.
- Any segment without an active policy is assigned an empty list, unless `blanket_allowance=True`, which appends a default `PARKING_ANYTIME_POLICY`.

### 8. Export
The final sorted list of policy dictionaries for each segment is serialized into a JSON string (`policy_list`) and written back out to the Postgres database under a newly created policy handling job ID.
