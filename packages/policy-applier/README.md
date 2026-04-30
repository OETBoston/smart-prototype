# Smart Curb Policy Handling

This project provides tools for visualizing and processing curbside parking policies using Streamlit and Python. It supports both interactive UI exploration and programmatic policy assignment for curb segments.

## Project Status
>
> **`main.py`** is the policy applier script that processes curb segments and assigns policies.
> 
> **`toy-app.py`** is the toy Streamlit app for exploration and testing.
> 
> **`app.py`** is the main visualizer for real-world curb segments and policies, using data from Postgres tables.

## Features
- **Streamlit Visualizer** for real-world curb policy visualization and configuration (`app.py`)
- **Streamlit Toy App** for interactive curb policy exploration and configuration (`toy-app.py`)
- **Automated policy assignment** for curb segments based on sign and curb data (`main.py`)

## Requirements
- Python 3.13+
- [uv](https://github.com/astral-sh/uv) for dependency management

## Installation
1. **Clone the repository:**
   ```sh
   git clone https://github.com/OETBoston/smart-curb-policy-handling.git
   cd smart-curb-policy-handling
   ```
2. **Switch to the development branch (if needed):**
   > [!IMPORTANT]
   > The latest features may be in `v1-dev`. Switch branches if required:
   ```sh
   git switch v1-dev
   ```
3. **Install dependencies using uv:**
   ```sh
   uv sync
   ```
   > **Note:** All dependencies are listed in `pyproject.toml`.

## Prerequisites for Connecting to GCP Postgres
To use the real-world visualizer (`app.py`) or run policy assignment on production data (`main.py`), you must connect to the GCP-hosted Postgres database. Follow these steps:

1. **Configure Environment Variables:**
   - Copy the provided `.env.template` file to `.env`:
     ```sh
     cp .env.template .env
     ```
   - Edit `.env` and replace the placeholders with your own credentials:
     - `db_user=YOUR_DB_USER`
     - `db_password=YOUR_DB_PASSWORD`

2. **Open a Proxy Connection to the Postgres Server:**
   - Use Google Cloud SDK to open a local proxy to the remote Postgres server, please refer to [this Confluence page](https://camsys.atlassian.net/wiki/spaces/BOSCDS/pages/2854060033/Postgres+DB+Access) for detailed instructions.
     

## Usage

### 1. Visualizer for Real-World Curb Segments
Launch the main Streamlit visualizer (requires access to Postgres tables):
```sh
uv run streamlit run app.py
```
- Visualizes and configures curb policies using real-world data.

### 2. Policy Applier Toy Streamlit App (For Exploration)
Launch the interactive toy curb policy visualizer:
```sh
uv run streamlit run toy-app.py
```
- Adjust curb segments, configure signs, and visualize policy assignments in a sandboxed environment.

### 3. Command-Line Policy Assignment
Process curb segment data and assign policies programmatically. Two arguments are required:
1. A curb segmenter job id.
2. The database schema to read inputs and write outputs (defaults to `staging`).
3. 
```sh
python main.py [--job-id JOB_ID --schema SCHEMA] [--help]
```
- Use `--job-id JOB_ID` to process curb segments created by a specific job ID.
- Use `--help` to see all available arguments and options.

## Project Structure
- `app.py` — Streamlit UI for real-world curb policy visualization (Postgres-backed)
- `main.py` — Command-line tool for policy assignment (argument parsing, batch processing)
- `db_utils/` — Database connection and query helpers
- `display_utils/` — Visualization and display utilities
- `handler_utils/` — Policy handler logic
- `io_utils/` — Input/output helpers
- `models/` — Data models and schemas
- `cached_images/`, `cached_tables/` — Cached data for performance
- `toy-app.py` — Streamlit toy app for curb policy exploration
- `policy_utils.py` — (For toy app) Core logic for policy propagation and assignment
- `utils.py` — (For toy app) Utility functions for toy app data extraction and processing

# Curb Policy Testing Guide

This test suite validates the full logic of `main.py` without requiring a database connection or a specific Job UUID.

## Required Test Assets
Ensure your project structure matches the following. The test uses these local files to simulate database tables:

```text
project_root/
├── main.py
├── tests/
│   ├── test_main.py
│   └── test_data/
│       └── test_name, e.g. test0
│           ├── curb_segments.geojson
│           ├── signs.csv
│           ├── asset_locations.geojson
│           ├── nonsign_feataures.csv
│           ├── sign_policies.csv
│           └── expected_output.csv
```

## Running the Test
Run the following command from the project root:

```python
uv run python -m pytest tests/test_main.py -v
```

## Troubleshooting: Assertion Failures

If the test fails (e.g., the output data doesn't match the expected data), here is what happens to your files and environment:

### 1. File Location after Failure
Because the failure occurs during the comparison step, the output file has already been written.
* **Location:** The generated file will be at `tests/data_data/[testname]/curb_policy_output.csv`.

### 2. Debugging Differences
If the data does not match, `pytest` will show a "diff" in the terminal. To investigate further:
1.  Open `tests/test_data/testname/curb_policy_output.csv` (the actual result).
2.  Open `tests/test_data/testname/expected_curb_policy_output.csv` (your baseline).
3.  Compare the rows to identify if the logic error is in the Forward Pass, Backward Pass, or the final JSON formatting.


