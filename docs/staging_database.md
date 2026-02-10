# Staging Database Structure

The Boston Curb staging database contains input data that supports the curb identification
process, and serves as a location to store intermediate results. The structure of tables
in this database are defined here.

## Input Assets Tables

This set of tables contains input data about **assets**, with the primary asset type being `signs`.
The assets tables also include limited information about other non-sign assets such as `hydrants`
and `bus_stops`. It can be extended to include other non-sign assets, but curb segmentation code
would need to be modified to make use of these other asset types.

### asset_locations

| column_name        | column_type        | Notes                                                                                                                          |
| :----------------- | :----------------- | :----------------------------------------------------------------------------------------------------------------------------- |
| asset_location_id  | UUID (PRIMARY KEY) |                                                                                                                                |
| data_source_id     | UUID (FOREIGN KEY) |                                                                                                                                |
| job_id             | UUID (FOREIGN KEY) |                                                                                                                                |
| source_location_id | VARCHAR            | Optional but **highly recommended** field containing a unique identifier linking the location to the original source database. |
| location           | GEOMETRY(Point)    | Location of the signpost (not the photo taker).                                                                                |

### signs

| column_name       | column_type        | Notes                                                                                                                          |
| :---------------- | :----------------- | :----------------------------------------------------------------------------------------------------------------------------- |
| sign_id           | UUID (PRIMARY KEY) |                                                                                                                                |
| sign_location_id  | UUID (FOREIGN KEY) |                                                                                                                                |
| data_source_id    | UUID (FOREIGN KEY) |                                                                                                                                |
| job_id            | UUID (FOREIGN KEY) |                                                                                                                                |
| source_sign_id    | VARCHAR            | Optional but **highly recommended** field containing a unique identifier linking the location to the original source database. |
| added_date        | TIMESTAMP          | Indicates when the sign added to the database.                                                                                 |
| sign_removed_date | TIMESTAMP          | Indicates when a sign was or will be removed, null to indicate that the sign is still present with no plans for removal.       |
| sign_type_code    | VARCHAR            | Optional field to contain an identifier linked to the City's database of sign types (Boston calls these MUTCD codes).          |
| sign_notes        | VARCHAR            | Optional space for free-form text notes about the sign.                                                                        |

### images

| column_name     | column_type        | Notes                                                                                                            |
| :-------------- | :----------------- | :--------------------------------------------------------------------------------------------------------------- |
| image_id        | UUID (PRIMARY KEY) |                                                                                                                  |
| sign_id         | UUID (FOREIGN KEY) | Should be indexed, related to signs.sign_id                                                                      |
| data_source_id  | UUID (FOREIGN KEY) |                                                                                                                  |
| job_id          | UUID (FOREIGN KEY) |                                                                                                                  |
| uri             | VARCHAR            | A uri to a stable and persistent location where the image can be found.                                          |
| image_date      | TIMESTAMP          | Date and time the images was added to the database.                                                              |
| source_image_id | VARCHAR            | Optional but recommended field to contain a unique identifier linking the image to the original source database. |

### data_sources

| column_name    | column_type        | Notes |
| :------------- | :----------------- | :---- |
| data_source_id | UUID (PRIMARY KEY) |       |
| source_name    | VARCHAR            |       |

### nonsign_features

| column_name         | column_type        | Notes                                                               |
| :------------------ | :----------------- | :------------------------------------------------------------------ |
| feature_id          | UUID (PRIMARY KEY) |                                                                     |
| feature_location    | UUID (FOREIGN KEY) |                                                                     |
| feature_type        | VARCHAR            | Short name describing the feature, such as `hydrant` or `bus_stop`. |
| feature_description | VARCHAR            | Optional longer description of the feature                          |

### asset_jobs

| column_name     | column_type        | Notes                                                                                                                                                |
| :-------------- | :----------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------- |
| job_id          | UUID (PRIMARY KEY) |                                                                                                                                                      |
| job_timestamp   | TIMESTAMP          | Time job was run                                                                                                                                     |
| job_name        | VARCHAR            | Short name that concisely describes a sign or other asset data import job.                                                                           |
| job_description | VARCHAR            | Extended description of an asset reader import job. Examples: "Cartegraph for Chinatown, 2025-12-22" or "Manual photos for Charlestown, 2025-12-23". |

## Input Block Face Tables

The input block face tables contain information about block faces that will be processed. Block faces
serve as inputs to the curb segmentation process.

### curb_blockfaces

| column_name       | column_type          | Notes                                                                          |
| :---------------- | :------------------- | :----------------------------------------------------------------------------- |
| blockface_id      | UUID (PRIMARY KEY)   |                                                                                |
| job_id            | UUID (FOREIGN KEY)   |                                                                                |
| geography         | GEOMETRY(LineString) | This could be JSON, WKT, or a PostGIS location.                                |
| direction_of_flow | VARCHAR              | Direction of flow in the adjacent lane. Values must be `forward` or `reverse`. |

### blockface_jobs

| column_name     | column_type        | Notes                                                             |
| :-------------- | :----------------- | :---------------------------------------------------------------- |
| job_id          | UUID (PRIMARY KEY) |                                                                   |
| job_timestamp   | TIMESTAMP          | Time job was run                                                  |
| job_name        | VARCHAR            | Short name that concisely describes a curb geometry creation job. |
| job_description | VARCHAR            | Extended description of a curb geometry creation job.             |

## Parking Meter Tables

This set of tables contains data regarding parking policies from the parking meters and how to link these policies to `curb_segments`.

### meter_policies

| column_name                | column_type        | Notes                                                                                   |
| :------------------------- | :----------------- | :-------------------------------------------------------------------------------------- |
| meter_policy_id            | UUID (PRIMARY KEY) |                                                                                         |
| job_id                     | UUID (FOREIGN KEY) | Job ID that links to metadata about the asset job that generated the policy.            |
| run_date                   | TIMESTAMP          | Time the record was generated.                                                          |
| policy_json                | JSONB              | Meter policy parsed in CDS policy object format.                                        |


### curb_segments_meter_zones

| column_name                | column_type        | Notes                                                                                   |
| :------------------------- | :----------------- | :-------------------------------------------------------------------------------------- |
| curb_segment_id            | UUID (FOREIGN KEY) |                                                                                         |
| meter_zone_id              | INT                | Zone ID from original parking meter dataset.                                            |

### meter_policies_meter_zones

| column_name                | column_type        | Notes                                                                                   |
| :------------------------- | :----------------- | :-------------------------------------------------------------------------------------- |
| meter_policy_id            | UUID (FOREIGN KEY) |                                                                                         |
| meter_zone_id              | INT                | Zone ID from original parking meter dataset.                                            |


## Sign Reader Output Tables

The sign reader creates policies based on sign imagery. Sign reader output contains the results of this
process referenced to the original images and their locations.

### sign_policies

| column_name             | column_type        | Notes                                                                                   |
| :---------------------- | :----------------- | :-------------------------------------------------------------------------------------- |
| sign_policy_id          | UUID (PRIMARY KEY) |                                                                                         |
| sign_id                 | UUID (FOREIGN KEY) |                                                                                         |
| job_id                  | UUID (FOREIGN KEY) | Job ID that links to metadata about the sign reader job that generated the policy.      |
| run_date                | TIMESTAMP          | Time the record was generated.                                                          |
| policy_json             | JSONB              | Sign policy as interpreted by the sign reader in CDS policy object format.             |
| policy_arrow            | VARCHAR            | left, right, or both (no arrows implies both).                                          |
| ai_confidence_score     | VARCHAR            | Score of 1-100 indicating AI confidence in CDS policy [may be broken into components?]. |
| ai_commentary           | VARCHAR            | Optional field to allow AI to provide "commentary" on reasoning.                        |
| cds_override            | VARCHAR            | Human-modified CDS override based on manual review.                                     |
| cds_override_commentary | VARCHAR            | Human commentary on reasoning for CDS override.                                         |

### sign_reader_jobs

| column_name     | column_type        | Notes                                                                                                                                            |
| :-------------- | :----------------- | :----------------------------------------------------------------------------------------------------------------------------------------------- |
| job_id          | UUID (PRIMARY KEY) |                                                                                                                                                  |
| job_timestamp   | TIMESTAMP          | Time job was run                                                                                                                                 |
| job_name        | VARCHAR            | Short name that concisely describes a sign reader job.                                                                                           |
| job_description | VARCHAR            | Extended description of a sign reader job. This should include information such as model/process versions, prompts, and other pertinent details. |

## Curb Segmenter Output Tables

The curb segmenter breaks blockfaces into segments based on sign and other non-sign asset locations.
It produces lines that reference assets at either end of the segment. These locations can be linked
to signs or non-sign assets that caused the segment to be split.

### curb_segments

| column_name         | column_type          | Notes                                           |
| :------------------ | :------------------- | :---------------------------------------------- |
| segment_id          | UUID (PRIMARY KEY)   |                                                 |
| blockface_id        | UUID (FOREIGN KEY)   |                                                 |
| job_id              | UUID (FOREIGN KEY)   |                                                 |
| run_date            | TIMESTAMP            |                                                 |
| geography           | GEOMETRY(LineString) | This could be JSON, WKT, or a PostGIS location. |
| upstream_location   | UUID (FOREIGN KEY)   |                                                 |
| downstream_location | UUID (FOREIGN KEY)   |                                                 |

### curb_segment_jobs

| column_name     | column_type        | Notes                                                                                                                                                                                                                       |
| :-------------- | :----------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| job_id          | UUID (PRIMARY KEY) |                                                                                                                                                                                                                             |
| job_timestamp   | TIMESTAMP          | Time job was run                                                                                                                                                                                                            |
| job_name        | VARCHAR            | Short name that concisely describes a curb segmentation job.                                                                                                                                                                |
| job_description | VARCHAR            | Extended description of a sign reader job. This should include information such as the version of the curb segmenter program and the source of the curb geography (e.g., "MassDOT streets layer current as of 12-22-2025"). |

## Policy Handler Output Tables

The policy handler assigns policies to curb segments. Policy Handler output contains the results of this
process, in which each record represents a single policy instance applied to a segment.

### curb_segment_policies

| column_name             | column_type        | Notes                                                                                   |
| :---------------------- | :----------------- | :-------------------------------------------------------------------------------------- |
| assignment_id           | UUID (PRIMARY KEY) |                                                                                         |
| segment_id              | UUID (FOREIGN KEY) | Segment ID that links to "curb_segments"                                                |
| policy_id               | UUID (FOREIGN KEY) | Policy ID that links to "policies"                                                      |
| job_id                  | UUID (FOREIGN KEY) | Job ID that links to metadata about the policy handling job that generated the mapping. |
| run_date                | TIMESTAMP          | Time the record was generated.                                                          |

### policy_handling_jobs

| column_name     | column_type        | Notes                                                                                                                                            |
| :-------------- | :----------------- | :-----------------------------------------------------------------------------------------------|
| job_id          | UUID (PRIMARY KEY) |                                                                                                 |
| job_name        | VARCHAR            | Short name that concisely describes a sign reader job.                                          |
| job_description | VARCHAR            | Extended description of a sign reader job. This should include information such as model/process versions, prompts, and other pertinent details. |

### policies
| column_name             | column_type        | Notes                                                                                   |
| :---------------------- | :----------------- | :-------------------------------------------------------------------------------------- |
| policy_id               | UUID (PRIMARY KEY) |                                                                                         |
| policy_json             | JSONB              | Sign policy as interpreted by the sign reader in CDS policy object format .             |
