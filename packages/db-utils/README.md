# db-utilities

A Python connector class for PostGIS database access. The `SmartCurbDB` class provides a convenient interface to read from and write to PostgreSQL tables with built-in support for geospatial data via geopandas.

## Installation

This project advises using the `uv` package manager. Repositories that make
use of this tool will need to add it to their `pyproject.toml` file. This
can be done in one of two ways.

### Option 1: Local Path (Recommended for Development)

If you have the smart-curb-db repository in the parent directory:

```bash
uv add ../smart-curb-db
```

**Use this when:**

- You're actively developing this package or plan to make changes
- The package is cloned as a sibling directory
- You want to test local changes immediately

### Option 2: Git URL

Clone and add from GitHub:

```bash
uv add git+https://github.com/OETBoston/smart-curb-db.git
```

**Use this when:**

- You want the package from the main branch without cloning locally
- You prefer automatic updates from the remote repository
- This package is a dependency in another project

## Configuration

Set the following environment variables to configure your database connection:

- `DB_HOST` (default: `localhost`) - PostgreSQL server hostname
- `DB_PORT` (default: `5432`) - PostgreSQL server port
- `DB_USER` (default: `postgres`) - Database user
- `DB_PASSWORD` (default: `postgres`) - Database password

You can use a `.env` file with `python-dotenv` to load these variables:

```bash
# .env
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
```

## Usage

### Basic Connection

Use `SmartCurbDB` as a context manager to ensure proper connection handling:

```python
from db_utils import SmartCurbDB

with SmartCurbDB(dbname="my_database", schema="public") as db:
    # Your database operations here
    pass
```

### Reading Data

#### Read as DataFrame

```python
with SmartCurbDB(dbname="my_database", schema="public") as db:
    df = db.get_data("my_table")
    print(df.head())
```

#### Read as GeoDataFrame

To read geospatial data, specify the geometry column:

```python
with SmartCurbDB(dbname="my_database", schema="public") as db:
    gdf = db.get_data("my_table", geom_col="geometry")
    print(gdf.head())
```

#### Filtering Rows

Use the `filter` parameter to add a WHERE clause:

```python
with SmartCurbDB(dbname="my_database", schema="public") as db:
    df = db.get_data(
        "my_table",
        filter="age > 30 AND city = 'Boston'"
    )
```

#### Selecting Specific Columns

Use the `columns` parameter to select only certain columns:

```python
with SmartCurbDB(dbname="my_database", schema="public") as db:
    df = db.get_data(
        "my_table",
        columns=["name", "age", "email"]
    )
```

#### Combining Filters and Columns

```python
with SmartCurbDB(dbname="my_database", schema="public") as db:
    gdf = db.get_data(
        "my_table",
        geom_col="geometry",
        filter="status = 'active'",
        columns=["id", "name", "geometry"]
    )
```

### Writing Data

Append data to an existing table using pandas DataFrame or geopandas GeoDataFrame:

```python
import pandas as pd
from db_utils import SmartCurbDB

with SmartCurbDB(dbname="my_database", schema="public") as db:
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"],
        "value": [100.5, 200.75, 300.0]
    })
    db.append_data("my_table", df)
```

## Error Handling

The class validates data and raises appropriate exceptions:

Example of error checking when reading:

```python
from db_utils import SmartCurbDB

try:
    with SmartCurbDB(dbname="my_database", schema="public") as db:
        df = db.get_data("nonexistent_table")
except ValueError as e:
    print(f"Table error: {e}")
except ConnectionError as e:
    print(f"Connection error: {e}")
```

Example of error checking when writing

```python
from db_utils import SmartCurbDB

try:
    with SmartCurbDB(dbname="my_database", schema="public") as db:
        db.append_data("my_table", invalid_df)
except ValueError as e:
    print(f"Data Specification Error: {e}")
except ConnectionError as e:
    print(f"Connection error: {e}")
except Exception as e:
    print(f"SQL Data Validation Error: {e})
```

Common errors:

- `ConnectionError`: Database connection is not open
- `ValueError`: Table does not exist, columns are invalid, or data is invalid

SQLAlchemy will return issue-specific errors if data provided cannot be added
to the named table.
