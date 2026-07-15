# Sign Loader

A pipeline for preprocessing and loading parking sign data into PostgreSQL/PostGIS database.

This toolkit automates the ingestion of parking sign data, performs geographic and status-based filtering, groups nearby signs together, and uploads the results to the database in a standardized format.

## Repository Structure

```text
.
├── main.py                 # Entry point – orchestrates the full workflow
├── config.yaml             # Runtime configuration
└── data/                   # Input data directory (CSV and shapefiles)
```

---

## Usage

From the project root (`smart-prototype/`), run:

```bash
uv run python packages/sign-loader/src/sign_loader/main.py
```

## Configuration

Runtime behavior is controlled through a YAML configuration file.
See the [default config file](./config.yaml) for details.


Th config defines:

- **Data paths**: Input CSV files and shapefiles
- **Database settings**: Connection parameters and schema
- **Filtering rules**: MUTCD codes for parking signs, status filters
- **Processing parameters**: Grouping distance, output CRS


#### Cartegraph Input

`main.py` is set up to preprocess Cartegraph data that comes from the [Cartegraph dataset on Analyze Boston data portal](https://data.boston.gov/dataset/signs-cartegraph).

For Cartegraph data, configure the required column mappings in `cartegraphy_required_columns` within `config.yaml`:

| Config Field       | Type   | Description                                                         | Cartegraph Example          |
| ------------------ | ------ | ------------------------------------------------------------------- | --------------------------- |
| `source_sign_id`   | string | Column name containing unique sign identifiers                      | `oid`                       |
| `source_image_id`  | string | Column name containing unique image identifiers                     | `attachment_oid`            |
| `uri`              | string | Column name containing URLs to sign images                          | `attachment_public_url`     |
| `sign_type_code`   | string | Column name containing MUTCD sign codes                             | `mutcd_code_field`          |
| `added_date`       | string | Column name containing sign creation date                           | `entry_date_field`          |
| `geometry_columns` | array  | Array of column names containing geometry data (latitude/longitude) | `["latitude", "longitude"]` |
| `date_columns`     | object | Object mapping date field types to column names                     | See example below           |

Records are automatically filtered if they meet any of these conditions:

- Missing values in latitude/longitude columns
- Null or missing MUTCD code

The sign 

#### Other Input

If using a different signs dataset, configure the required and optional columns in `other_data_source` within `config.yaml.

At least following must be configured: `geometry` (the point geometry of the sign location) 
and `uri` (a publicly available URI pointed at a sign image).


The script will:

1. Load and validate input data
2. Preprocess data
3. Format data into database tables
4. Upload to PostgreSQL (or log what would be uploaded in debug mode)

### Debug Mode

To test the pipeline without writing to the database, set `debug_mode: True` in `config.yaml`.
The pipeline will log all operations as if uploading, but no data will be written to the database.

---

## Pipeline Steps

### 1. **Data Loading**

Reads sign data from CSV and neighborhood boundaries from GeoJSON/Shapefile.

### 2. **Data Preprocessing**

For Cartegraph datasets:

- Filters for signs with valid latitude/longitude coordinates
- Removes records missing required fields (MUTCD code)
- Removes duplicates, keeping the most recently modified record
- Filters for parking signs using configurable MUTCD codes (e.g., "P-", "MS-")
- Excludes signs with certain statuses (e.g., "Missing", "Proposed")
- Optionally filters signs to specific neighborhoods using spatial joins
- Groups nearby signs together by truncating coordinates to a configurable distance (default: 5 ft)

For other datasets:

- Reprojects dataset into correct CRS

### 3. **Data Formatting**

Transforms the processed GeoDataFrame into database-ready tables:

- `asset_jobs`: Job metadata
- `data_sources`: Data source information
- `asset_locations`: Grouped sign locations
- `signs`: Individual sign records
- `images`: Associated sign images

### 4. **Database Upload**

Appends formatted tables to PostgreSQL database using the `SmartCurbDB` connector.

---

## Outputs

The pipeline creates the following database tables:

| Table             | Description                                      |
| ----------------- | ------------------------------------------------ |
| `asset_jobs`      | Job metadata and description                     |
| `data_sources`    | Data source information                          |
| `asset_locations` | Grouped sign locations (by geographic proximity) |
| `signs`           | Individual parking sign records                  |
| `images`          | Sign image metadata                              |

To learn more about the fields in these tables, check out the [documentation of the full staging database](https://github.com/OETBoston/smart-prototype/blob/main/docs/staging_database.md)
