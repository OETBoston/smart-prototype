# Cartegraph Loader

A pipeline for preprocessing and loading parking sign data from Cartegraph into a PostgreSQL/PostGIS database.

This toolkit automates the ingestion of parking sign data, performs geographic and status-based filtering, groups nearby signs together, and uploads the results to the database in a standardized format.

The pipeline is configuration-driven, reproducible, and designed to run sequentially from a single entry point.

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

| Parameter             | Description |
|-----------------------|-------------|
| job_name              | Name of job being run, to be used in `asset_jobs` table |
| job_description       | A description of the job being run, e.g. Cartegraph data for Charlestown |
| data_source_name      | Name of data source, to be used in `data_sources` table |
| dbname                | Target database name |
| schema                | Target schema name |
| debug_mode            | If `True`, disables database writes |
| signs_path            | Path to where signs csv is stored. This data comes form the [Analyze Boston data portal](https://data.boston.gov/dataset/signs-cartegraph)|
| neighborhoods_path    | Path to where neighborhoods shp files are stored. This data comes from the [Analyze Boston data portal](https://data.boston.gov/dataset/bpda-neighborhood-boundaries)|
| neighborhoods         | List of neighborhoods used for filtering; can be empty, then signs from all neighborhoods are processed and uploaded |
| parking_mutcd_codes   | List of MUTCD codes related to parking regulations |
| status_filters        | Used to filter `asset_status_field`, currently filtering out "Missing" and "Proposed" signs; "Removed" signs are noted in the db with the `sign_removed_date` field. |
| grouping_distance_ft  | Number of feet used to group parking signs (e.g. if 2 signs within 5 ft of each other, they are grouped to the same location) |
| output_crs            | CRS to final uploaded files |

---

## Usage

This project uses `uv` for seamless environment management. You do not need to manually activate a virtual environment; `uv run` handles it automatically.

### Running the ETL Pipeline

From the repository root:

```bash
uv run python packages/sign-loader/src/sign_loader/main.py
```

The script will:
1. Load and validate input data
2. Filter signs by MUTCD codes and status
3. Remove duplicates based on modification date
4. Group nearby signs by geographic proximity
5. Format data into database tables
6. Upload to PostgreSQL (or log what would be uploaded in debug mode)

### Debug Mode

To test the pipeline without writing to the database, set `debug_mode: True` in `config.yaml`. 
The pipeline will log all operations as if uploading, but no data will be written to the database.

---

## Pipeline Steps

### 1. **Data Loading**
Reads sign data from CSV and neighborhood boundaries from GeoJSON/Shapefile.

### 2. **Data Cleaning**
* Filters for signs with valid latitude/longitude coordinates
* Removes records missing required fields (MUTCD code)
* Removes duplicates, keeping the most recently modified record

### 3. **Sign Filtering**
* Filters for parking signs using configurable MUTCD codes (e.g., "P-", "MS-")
* Excludes signs with certain statuses (e.g., "Missing", "Proposed")

### 4. **Geographic Filtering**
* Optionally filters signs to specific neighborhoods using spatial joins
* Groups nearby signs together by truncating coordinates to a configurable distance (default: 5 ft)

### 5. **Data Formatting**
Transforms the processed GeoDataFrame into database-ready tables:
* `asset_jobs`: Job metadata
* `data_sources`: Data source information
* `asset_locations`: Grouped sign locations
* `signs`: Individual sign records
* `images`: Associated sign images

### 6. **Database Upload**
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

