import os
from types import TracebackType
from typing import Sequence

import geopandas as gpd
import pandas as pd
from psycopg2.errors import InvalidTextRepresentation
from sqlalchemy import Connection, Engine, Inspector, create_engine, inspect, text
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import DataError, ProgrammingError

# TODO:
# Use pytest to create unit tests for this class.


class SmartCurbDB:
    """Manages connections and queries to a PostgreSQL database with support for
    geospatial data.

    This class provides methods to read from and write to PostgreSQL tables, with
    built-in support for geopandas GeoDataFrames and spatial queries.

    """

    def __init__(self, dbname: str, schema: str | None = None) -> None:
        """Initializes a SmartCurbDB instance with database connection parameters.

        Args:
            dbname (str): Name of the database to connect to.
            schema (str | None, optional): Name of the schema to use. Defaults to None.

        Example:
            Basic usage with context manager:

            >>> with SmartCurbDB(dbname="my_db", schema="public") as db:
            ...     df = db.get_data("my_table")
            ...     gdf = db.get_data("my_table", geom_col="geometry")

            With WHERE clause row filtering and specific columns:

            >>> with SmartCurbDB(dbname="my_db") as db:
            ...     df = db.get_data(
            ...         "my_table",
            ...         filter="age > 30 AND city = 'Boston'",
            ...         columns=["name", "age", "email"]
            ...     )

            Appending data:

            >>> with SmartCurbDB(dbname="my_db") as db:
            ...     df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
            ...     db.append_data("my_table", df)

            Modifying data:

            >>> with SmartCurbDB(dbname="my_db") as db:
            ...     # filter must return one and only one record.
            ...     db.modify_record("my_table", filter="id=123", field="my_field",
            ...     value="abcd")
        """
        self.schema = schema
        self.dbname = dbname
        self.engine: Engine | None = None
        self.connection: Connection | None = None

        # Load config from env variables
        self.host = os.environ.get("DB_HOST", "localhost")
        self.port = int(os.environ.get("DB_PORT", "5432"))
        self.user = os.environ.get("DB_USER", "postgres")
        self.password = os.environ.get("DB_PASSWORD", "postgres")

    def __enter__(self) -> "SmartCurbDB":
        self.connect()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def connect(self) -> None:
        """Establishes a connection to the PostgreSQL database.

        Creates a SQLAlchemy engine and connection using environment variables
        for host, port, user, and password. Sets the search path to the specified
        schema if provided.
        """
        url = URL.create(
            drivername="postgresql+psycopg2",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.dbname,
        )
        self.engine = create_engine(url)
        self.connection = self.engine.connect()
        if self.schema:
            # Set the search path to the specified schema
            self.connection.execute(text(f"SET search_path TO {self.schema}, public"))
            self.connection.commit()

    def close(self) -> None:
        """Closes the database connection and disposes of the engine."""
        if self.connection:
            self.connection.close()
            self.connection = None
        if self.engine:
            self.engine.dispose()
            self.engine = None

    def append_data(
        self, table_name: str, data: pd.DataFrame | gpd.GeoDataFrame
    ) -> None:
        """Appends data to the specified table in the database.

        Args:
            table_name (str): Name of the table to write to.
            data (pd.DataFrame | gpd.GeoDataFrame): pandas DataFrame or geopandas
                GeoDataFrame.

        Raises:
            ValueError: If data is not a DataFrame or GeoDataFrame.
            ValueError: If the specified table does not exist.
            ConnectionError: If the database connection is not open.
        """
        if not isinstance(data, (pd.DataFrame, gpd.GeoDataFrame)):
            raise ValueError(
                "Data must be a pandas DataFrame or geopandas GeoDataFrame."
            )

        # Check DB status and table existence
        self._check_db_status(table_name)
        # for type checker, guaranteed by _check_db_status
        assert self.engine is not None

        if isinstance(data, gpd.GeoDataFrame):
            # Write GeoDataFrame
            try:
                data.to_postgis(
                    table_name, self.engine, schema=self.schema, if_exists="append"
                )

            except InvalidTextRepresentation as e:
                raise InvalidInputError(
                    "Failed to write data to PostGIS (likely bad input)"
                ) from e
        else:
            # Write DataFrame
            try:
                data.to_sql(
                    table_name,
                    self.engine,
                    schema=self.schema,
                    if_exists="append",
                    index=False,
                )
            except (DataError, ProgrammingError) as e:
                raise InvalidInputError(
                    "Failed to write data to PostgreSQL (likely bad input)"
                ) from e

    def get_data(
        self,
        table_name: str,
        geom_col: str | None = None,
        filter: str | None = None,
        columns: Sequence[str] | None = None,
    ) -> pd.DataFrame | gpd.GeoDataFrame:
        """Retrieves data from a database table as a DataFrame or GeoDataFrame.

        To return a GeoDataFrame, provide the geom_col parameter.

        Args:
            table_name (str): Name of the table to read.
            geom_col (str | None, optional): Name of the geometry column to read as
                GeoDataFrame. If None, returns DataFrame. Defaults to None.
            filter (str | None, optional): SQL WHERE clause to filter rows. Defaults to
                None.
            columns (Sequence[str] | None, optional): Column name(s) to select.
                Defaults to all columns.

        Returns:
            pd.DataFrame | gpd.GeoDataFrame: A pandas DataFrame or geopandas
                GeoDataFrame.

        Raises:
            ValueError: If the specified table does not exist.
            ConnectionError: If the database connection is not open.
        """
        # Check DB status and table existence
        inspector = self._check_db_status(table_name)
        # for type checker, guaranteed by _check_db_status
        assert self.connection is not None

        # Build the WHERE clause if filter is provided
        where_clause = f" WHERE {filter}" if filter else ""

        # Build the column list
        if columns is None:
            columns_clause = "*"
        else:
            if geom_col is not None and geom_col not in columns:
                raise ValueError(
                    "Geometry column must be included in columns list if specified."
                )
            columns_clause = ", ".join(
                self._validate_and_quote_columns(columns, inspector, table_name)
            )

        # Build the SQL statement
        if self.schema:
            sql = (
                f"SELECT {columns_clause} FROM {self.schema}.{table_name}{where_clause}"
            )
        else:
            sql = f"SELECT {columns_clause} FROM {table_name}{where_clause}"

        # Read as DataFrame
        if geom_col is None:
            return pd.read_sql(text(sql), self.connection)
        else:
            # Read as GeoDataFrame
            return gpd.read_postgis(sql, self.connection, geom_col=geom_col)

    def modify_record(
        self, table_name: str, filter: str, column: str, value: str | int | float
    ) -> None:
        """Updates a single value in a record and column.

        Args:
            table_name (str): Name of the table to read.
            filter (str): SQL WHERE clause to filter rows.
                Must return exactly one record.
            column (str): Column name to update.
            value (str | int | float): New value

        Raises:
            ValueError: If the specified table does not exist.
            ValueError: If the filter returns more than one record.
            ConnectionError: If the database connection fails.
        """
        # Check DB status and table existence
        inspector = self._check_db_status(table_name)
        # for type checker, guaranteed by _check_db_status
        assert self.engine is not None
        assert self.connection is not None

        # Validate that the column exists
        available_columns = {
            col["name"] for col in inspector.get_columns(table_name, schema=self.schema)
        }
        if column not in available_columns:
            raise ValueError(
                f"Column '{column}' does not exist in table '{table_name}'."
            )

        # Select the record based on filter to verify only one was selected
        where_clause = f" WHERE {filter}"
        if self.schema:
            sql = f"SELECT * FROM {self.schema}.{table_name}{where_clause}"
        else:
            sql = f"SELECT * FROM {table_name}{where_clause}"

        result_df = pd.read_sql(text(sql), self.engine)

        if len(result_df) == 0:
            raise ValueError(f"Filter returned no records: {filter}")
        if len(result_df) > 1:
            raise ValueError(
                f"Filter returned {len(result_df)} records, expected exactly 1."
            )

        # Update the column in that selected record
        if self.schema:
            update_sql = (
                f'UPDATE {self.schema}.{table_name} SET "{column}" = :value '
                f"WHERE {filter}"
            )
        else:
            update_sql = f'UPDATE {table_name} SET "{column}" = :value WHERE {filter}'

        # Apply the edit
        self.connection.execute(text(update_sql), {"value": value})
        self.connection.commit()

    def _check_db_status(self, table_name: str) -> Inspector:
        """Checks if the database connection is open and if the specified table exists.

        Args:
            table_name (str): Name of the table to verify.

        Returns:
            Inspector: SQLAlchemy Inspector object for the database.

        Raises:
            ConnectionError: If the database connection is not open.
            ValueError: If the specified table does not exist.
        """

        if self.engine is None or self.connection is None:
            raise ConnectionError(
                "Database connection is not open. Use within a context manager or call "
                "connect()."
            )

        # Make sure the table exists, provide ValueError if not
        inspector = inspect(self.engine)
        if inspector is None:
            raise ConnectionError(
                "Could not connect to the database engine to verify table exists."
            )
        inspector: Inspector
        if not inspector.has_table(table_name, schema=self.schema):
            raise ValueError(
                f"Table '{table_name}' does not exist in schema '{self.schema}'."
            )
        return inspector

    def _validate_and_quote_columns(
        self,
        columns: Sequence[str],
        inspector: Inspector,
        table_name: str,
    ) -> list[str]:
        """Validates user-provided columns against the table schema and returns a
        quoted list.

        Args:
            columns (Sequence[str] | str): Column name(s) to validate.
            inspector (Inspector): SQLAlchemy Inspector object for the database.
            table_name (str): Name of the table to check against.

        Returns:
            list[str]: List of quoted column names suitable for SQL generation.

        Raises:
            ValueError: If columns list is empty or if any columns do not exist in the
                table.
        """

        columns_list = list(columns)

        if not columns_list:
            raise ValueError("Columns list cannot be empty.")

        available_columns = {
            column["name"]
            for column in inspector.get_columns(table_name, schema=self.schema)
        }
        missing_columns = [col for col in columns_list if col not in available_columns]
        if missing_columns:
            raise ValueError(
                f"Columns {missing_columns} do not exist in table '{table_name}'."
            )

        return [f'"{col}"' for col in columns_list]


class InvalidInputError(TypeError):
    """Raised when invalid data prevents conversion of a dataframe to sql"""

    pass
