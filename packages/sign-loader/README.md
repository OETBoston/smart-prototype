# Sign Loader

A pipeline for preprocessing and loading parking sign data into PostgreSQL/PostGIS database.

This toolkit automates the ingestion of parking sign data, performs geographic and status-based filtering, groups nearby signs together, and uploads the results to the database in a standardized format.
---

## Prerequisites

* Python **3.13+**
* `uv` installed

Install `uv` (if you don't have it yet):

```bash
pip install uv
```

---

## Installation

Clone the repository and install dependencies:

```bash
cd smart-prototype/packages/sign-loader
uv sync
```

This will:
* Create a virtual environment
* Install all dependencies defined in `pyproject.toml`
* Install the `curb-utils` workspace package

---

## Environment Variables

This project loads database credentials using `python-dotenv`. To get started:

1. **Create a `.env` file** in the repository root (not in this package):
   ```bash
   touch /path/to/smart-prototype/.env
   ```

2. **Add your database credentials**:
   ```text
   DB_HOST=localhost
   DB_PORT=5432
   DB_USER=your_username
   DB_PASSWORD=your_password
   ```

3. **Note:** The `.env` file is ignored by git and should never be committed.

---

## Core Structure

```text
.
├── main.py                 # Entry point – orchestrates the full workflow
├── config.yaml             # Runtime configuration
└── data/                   # Input data directory (CSV and shapefiles)
```

---

## Configuration (`config.yaml`)

The pipeline is controlled by `config.yaml`, which defines:

* **Data paths**: Input CSV files and shapefiles
* **Database settings**: Connection parameters and schema
* **Filtering rules**: MUTCD codes for parking signs, status filters
* **Processing parameters**: Grouping distance, output CRS

Below details common paramaters needed no matter the input:

| Parameter             | Description                                                                                                                                                           | 
|-----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| job_name              | Name of job being run, to be used in `asset_jobs` table                                                                                                               |
| job_description       | A description of the job being run, e.g. Cartegraph data for Charlestown                                                                                              |
| data_source_name      | Name of data source, to be used in `data_sources` table                                                                                                               |
| dbname                | Target database name                                                                                                                                                  |
| schema                | Target schema name                                                                                                                                                    |
| debug_mode            | If `True`, disables database writes                                                                                                                                   |
| signs_path            | Path to where signs csv is stored                                                                                                                                     |
| input_crs             | CRS of input signs file                                                                                                                                               |
| output_crs            | CRS to final uploaded files                                                                                                                                           |


#### Cartegraph Input

`main.py` is set up to preprocess Cartegraph data that comes from the [Cartegraph dataset on Analyze Boston data portal](https://data.boston.gov/dataset/signs-cartegraph).

For Cartegraph data, configure the required column mappings in `cartegraphy_required_columns` within `config.yaml`:

| Config Field | Type | Description | Cartegraph Example |
|--------------|------|-------------|-------------------|
| `source_sign_id` | string | Column name containing unique sign identifiers | `oid` |
| `source_image_id` | string | Column name containing unique image identifiers | `attachment_oid` |
| `uri` | string | Column name containing URLs to sign images | `attachment_public_url` |
| `sign_type_code` | string | Column name containing MUTCD sign codes | `mutcd_code_field` |
| `added_date` | string | Column name containing sign creation date | `entry_date_field` |
| `geometry_columns` | array | Array of column names containing geometry data (latitude/longitude) | `["latitude", "longitude"]` |
| `date_columns` | object | Object mapping date field types to column names | See example below |

**Date columns example:**
```yaml
date_columns:
  sign_modified_date: "cg_last_modified_field"
  attachment_modified_date: "attachment_cg_last_modified_field"
```

**Optional Configuration:**

Column-based filtering can be configured in `column_filters`:

| Field | Type | Description |
|-------|------|-------------|
| `column` | string | Name of the column in the source dataset to filter |
| `values` | array | List of values to match against |
| `mode` | string | Filter mode: `starts_with`, `drop`, or `keep` |

**Example configuration:**
```yaml
column_filters:
  - column: "asset_status"
    values: ["Missing", "Proposed"]
    mode: "drop"
```

**Additional Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `grouping_distance_ft` | number | Distance in feet to group nearby signs (default: 5 ft) |

**Data Validation:**

Records are automatically filtered if they meet any of these conditions:
- Missing values in latitude/longitude columns
- Null or missing MUTCD code

#### Other Input

If using a different signs dataset, configure the required and optional columns in `other_data_source` within `config.yaml`:

| Column Name | Type | Required | Description |
|-------------|------|----------|-------------|
| `geometry` | string | ✓ | Name of the geometry column in the dataset |
| `uri` | string | ✓ | Name of the column containing URLs to sign images |
| `source_sign_id` | string | | Name of the column containing unique sign identifiers |
| `source_image_id` | string | | Name of the column containing unique image identifiers |
| `notes_col` | string | | Name of the column containing sign notes or metadata |


---

## Usage

This project uses `uv` for seamless environment management. You do not need to manually activate a virtual environment; `uv run` handles it automatically.

### Running the Pipeline

Before running the pipeline, update the `config.yaml`. Then, from the repository root:

```bash
uv run python packages/sign-loader/src/sign_loader/main.py
```

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
* Filters for signs with valid latitude/longitude coordinates
* Removes records missing required fields (MUTCD code)
* Removes duplicates, keeping the most recently modified record
* Filters for parking signs using configurable MUTCD codes (e.g., "P-", "MS-")
* Excludes signs with certain statuses (e.g., "Missing", "Proposed")
* Optionally filters signs to specific neighborhoods using spatial joins
* Groups nearby signs together by truncating coordinates to a configurable distance (default: 5 ft)

For other datasets:
* Reprojects dataset into correct CRS

### 3. **Data Formatting**
Transforms the processed GeoDataFrame into database-ready tables:
* `asset_jobs`: Job metadata
* `data_sources`: Data source information
* `asset_locations`: Grouped sign locations
* `signs`: Individual sign records
* `images`: Associated sign images

### 4. **Database Upload**
Appends formatted tables to PostgreSQL database using the `SmartCurbDB` connector.

---

## Outputs

The pipeline creates the following database tables:

| Table | Description |
|-------|-------------|
| `asset_jobs` | Job metadata and description |
| `data_sources` | Data source information |
| `asset_locations` | Grouped sign locations (by geographic proximity) |
| `signs` | Individual parking sign records |
| `images` | Sign image metadata |

To learn more about the fields in these tables, check out the [documentation of the full staging database](https://github.com/OETBoston/smart-prototype/blob/main/docs/staging_database.md)

### Logging

Logs are written to both console and file:
* **Console**: Real-time pipeline progress
* **File**: `logs/cartegraph_loader_YYYYMMDD_HHMMSS.log`

## Troubleshooting

### `FileNotFoundError: No such file or directory`

Ensure you're running the script from the repository root:
```bash
cd /path/to/smart-prototype
uv run python packages/sign-loader/src/sign_loader/main.py
```

### `.env` parse error

Check that your `.env` file has valid syntax:
```text
KEY=value
ANOTHER_KEY=another_value
```

Avoid spaces around `=` and ensure all values are properly formatted.

### Database connection errors

Verify that:
1. Database credentials are correct in `.env`
2. The database server is running
3. The specified schema exists in the database

