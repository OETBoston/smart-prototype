import os
from types import TracebackType
from typing import Any, Sequence, overload
from uuid import uuid4

import geopandas as gpd
import pandas as pd
from psycopg2.errors import InvalidTextRepresentation
from sqlalchemy import Connection, Engine, Inspector, Row, create_engine, inspect, text
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import DataError, ProgrammingError


class SmartCurbDB:
    """WARNING: Do not use this class with untrusted inputs.

    Manages connections and queries to a PostgreSQL database with support for
    geospatial data.

    This class provides methods to read from and write to PostgreSQL tables, with
    built-in support for geopandas GeoDataFrames and spatial queries.

    """

    def __init__(self, dbname: str, schema: str) -> None:
        """Initializes a SmartCurbDB instance with database connection parameters.

        Args:
            dbname (str): Name of the database to connect to.
            schema (str): Name of the schema to use.

        Example:
            Basic usage with context manager:

            >>> with SmartCurbDB(dbname="my_db", schema="public") as db:
            ...     df = db.get_data("my_table")
            ...     gdf = db.get_data("my_table", geom_col="geometry")

            With WHERE clause row filtering and specific columns:

            >>> with SmartCurbDB(dbname="my_db", schema="public") as db:
            ...     df = db.get_data(
            ...         "my_table",
            ...         filter="age > 30 AND city = 'Boston'",
            ...         columns=["name", "age", "email"]
            ...     )

            Appending data:

            >>> with SmartCurbDB(dbname="my_db", schema="public") as db:
            ...     df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
            ...     db.append_data("my_table", df)

            Modifying data:

            >>> with SmartCurbDB(dbname="my_db", schema="public") as db:
            ...     # filter must return one and only one record.
            ...     db.modify_record("my_table", filter="id=123", column="my_field",
            ...     value="abcd")
        """
        if not dbname or not schema:
            raise ValueError("Missing required dbname or schema argument.")

        self.schema = schema
        self.dbname = dbname
        self.engine: Engine | None = None
        self.connection: Connection | None = None

        # Load config from env variables
        self.host = os.environ.get("DB_HOST", "localhost")
        self.port = int(os.environ.get("DB_PORT", "5432"))
        self.user = os.environ.get("DB_USER")
        self.password = os.environ.get("DB_PASSWORD")

        if self.user is None or self.password is None:
            raise ValueError("Missing required db connection environment variables")

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
        """WARNING: Do not use this method with untrusted inputs.

        Establishes a connection to the PostgreSQL database.

        Creates a SQLAlchemy engine and connection using environment variables
        for host, port, user, and password. Operations are performed on the
        specified schema.
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
        """WARNING: Do not use this method with untrusted inputs.

        Appends data to the specified table in the database.

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

    def update_or_append(
        self,
        table_name: str,
        data: pd.DataFrame | gpd.GeoDataFrame,
        key_columns: Sequence[str],
    ) -> None:
        """WARNING: Do not use this method with untrusted inputs.

        Updates existing records and appends new ones to the specified table.

        For each row in data, if a record matching key_columns already exists it is
        updated with the provided column values. If no matching record exists the row is
        inserted.

        key_columns must correspond to a UNIQUE or PRIMARY KEY constraint on the table.
        When inserting new rows, all columns must be present in the data.

        Args:
            table_name (str): Name of the table to write to.
            data (pd.DataFrame | gpd.GeoDataFrame): Data to upsert.
            key_columns (Sequence[str]): Column(s) used to match existing records.
                Must correspond to a UNIQUE or PRIMARY KEY constraint on the table.

        Raises:
            ValueError: If data is not a DataFrame or GeoDataFrame.
            ValueError: If key_columns are not present in data or the table.
            ValueError: If key_columns do not match a UNIQUE or PRIMARY KEY constraint.
            ValueError: If data contains only key columns with no columns to update.
            ValueError: If the specified table does not exist.
            ConnectionError: If the database connection is not open.
            InvalidInputError: If the data cannot be written to the database.
        """
        if not isinstance(data, (pd.DataFrame, gpd.GeoDataFrame)):
            raise ValueError(
                "Data must be a pandas DataFrame or geopandas GeoDataFrame."
            )

        inspector = self._check_db_status(table_name)
        # for type checker, guaranteed by _check_db_status
        assert self.engine is not None
        assert self.connection is not None

        key_columns_list = list(key_columns)

        # Validate key_columns exist in data
        missing_from_data = [col for col in key_columns_list if col not in data.columns]
        if missing_from_data:
            raise ValueError(
                f"key_columns {missing_from_data} are not present in the provided data."
            )

        # Validate key_columns exist in the table
        table_columns = {
            col["name"] for col in inspector.get_columns(table_name, schema=self.schema)
        }
        missing_from_table = [
            col for col in key_columns_list if col not in table_columns
        ]
        if missing_from_table:
            raise ValueError(
                f"key_columns {missing_from_table} do not "
                + f"exist in table '{table_name}'."
            )

        # Validate key_columns match a UNIQUE or PRIMARY KEY constraint
        pk = inspector.get_pk_constraint(table_name, schema=self.schema)
        pk_cols = set(pk.get("constrained_columns", []))
        unique_constraints = inspector.get_unique_constraints(
            table_name, schema=self.schema
        )
        unique_col_sets = [set(uc["column_names"]) for uc in unique_constraints]
        key_col_set = set(key_columns_list)

        if key_col_set != pk_cols and key_col_set not in unique_col_sets:
            raise ValueError(
                f"key_columns {key_columns_list} do not match any UNIQUE or PRIMARY KEY"
                f" constraint on table '{table_name}'."
            )

        # Determine columns to update (all data columns that are not key columns)
        non_key_columns = [col for col in data.columns if col not in key_col_set]
        if not non_key_columns:
            raise ValueError(
                "Data contains only key columns — there are no columns to update."
            )

        # Verify all table columns are included in the dataframe
        missing_from_df = [col for col in table_columns if col not in data.columns]
        if missing_from_df:
            raise ValueError(
                "Dataframe does not contain all columns present in the database table"
            )

        # Update the database in a transaction
        with self.engine.begin() as tx_connection:
            staging_table = self._create_empty_table_copy(table_name, tx_connection)

            # Append to the temporary table, no schema for a temporary table
            if isinstance(data, gpd.GeoDataFrame):
                try:
                    data.to_postgis(
                        staging_table,
                        tx_connection,
                        schema=self.schema,
                        if_exists="append",
                        index=False,
                    )
                except InvalidTextRepresentation as e:
                    raise InvalidInputError(
                        "Failed to write data to PostGIS temporary table "
                        + "(likely bad input)"
                    ) from e
            else:
                try:
                    data.to_sql(
                        staging_table,
                        tx_connection,
                        schema=self.schema,
                        if_exists="append",
                        index=False,
                    )
                except (DataError, ProgrammingError) as e:
                    raise InvalidInputError(
                        "Failed to write data to PostgreSQL temporary table "
                        + "(likely bad input)"
                    ) from e

            # Build the upsert SQL
            data_columns = list(data.columns)
            quoted_cols = [f'"{col}"' for col in data_columns]
            quoted_keys = [f'"{col}"' for col in key_columns_list]
            quoted_non_keys = [f'"{col}"' for col in non_key_columns]

            cols_clause = ", ".join(quoted_cols)
            conflict_clause = ", ".join(quoted_keys)
            update_clause = ", ".join(
                f"{col} = EXCLUDED.{col}" for col in quoted_non_keys
            )

            upsert_sql = (
                f"INSERT INTO {self.schema}.{table_name} ({cols_clause}) "
                f"SELECT {cols_clause} FROM {self.schema}.{staging_table} "
                f"ON CONFLICT ({conflict_clause}) "
                f"DO UPDATE SET {update_clause}"
            )

            # Execute the upsert SQL
            try:
                tx_connection.execute(text(upsert_sql))
            except (DataError, ProgrammingError) as e:
                raise InvalidInputError(
                    "Failed to upsert data to PostgreSQL (likely bad input)"
                ) from e

            # Drop the staging table
            tx_connection.execute(text(f"DROP TABLE {self.schema}.{staging_table};"))

    @overload
    def get_data(
        self,
        table_name: str,
        geom_col: None = None,
        filter: str | None = None,
        columns: Sequence[str] | None = None,
    ) -> pd.DataFrame: ...

    @overload
    def get_data(
        self,
        table_name: str,
        geom_col: str,
        filter: str | None = None,
        columns: Sequence[str] | None = None,
    ) -> gpd.GeoDataFrame: ...

    def get_data(
        self,
        table_name: str,
        geom_col: str | None = None,
        filter: str | None = None,
        columns: Sequence[str] | None = None,
    ) -> pd.DataFrame | gpd.GeoDataFrame:
        """WARNING: Do not use this method with untrusted inputs.

        Retrieves data from a database table as a DataFrame or GeoDataFrame.

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
        sql = f"SELECT {columns_clause} FROM {self.schema}.{table_name}{where_clause}"

        # Read as DataFrame
        if geom_col is None:
            return pd.read_sql(text(sql), self.connection)
        else:
            # Read as GeoDataFrame
            return gpd.read_postgis(sql, self.connection, geom_col=geom_col)

    def modify_record(
        self, table_name: str, filter: str, column: str, value: str | int | float
    ) -> None:
        """WARNING: Do not use this method with untrusted inputs.

        Updates a single value in a record and column.

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
        sql = f"SELECT COUNT(*) FROM {self.schema}.{table_name}{where_clause}"

        try:
            count = self.connection.execute(text(sql)).scalar_one()
        except Exception as e:
            self.connection.rollback()
            raise ValueError("Unable to count records - check filter value") from e

        if count == 0:
            raise ValueError(f"Filter returned no records: {filter}")
        if count > 1:
            raise ValueError(f"Filter returned {count} records, expected exactly 1.")

        # Update the column in that selected record
        update_sql = (
            f'UPDATE {self.schema}.{table_name} SET "{column}" = :value WHERE {filter}'
        )

        # Apply the edit
        try:
            self.connection.execute(text(update_sql), {"value": value})
        except Exception as e:
            self.connection.rollback()
            raise InvalidInputError(
                "Failed to write data to PostgreSQL (likely bad input)"
            ) from e

        self.connection.commit()

    def _check_db_status(self, table_name: str) -> Inspector:
        """WARNING: Do not use this method with untrusted inputs.

        Checks if the database connection is open and if the specified table exists.

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

    def _create_empty_table_copy(
        self, source: str, conn: Connection | None = None
    ) -> str:
        """Creates an empty table based on the source table. If
        the source table is a spatial table, the empty table is also a
        spatial table. The table is NOT dropped on commit.
        The caller is advised to drop the table when done with it.

        The connection argument overrides the objects active connection,
        which can be useful for applying this function within a transaction.

        Args:
            source (str): Name of the table to be copied
            conn (Connection | None): SQLAlchemy connection to use, or None to use the
            object's connection property.

        Returns:
            str: Name of the temporary table
        """

        tx_conn = self._parse_connection_arg(conn)

        # Create an empty copy
        temp_table = f"temp_table_{uuid4().hex[:8]}"
        tx_conn.execute(
            text(f"""
           CREATE TABLE {self.schema}.{temp_table} 
           (LIKE {self.schema}.{source}) 
            """)
        )

        # If the source table has geometry columns, we need to alter the
        # temporary table also have geometry columns
        geo_cols = self._get_geometry_columns(source, tx_conn)

        for col in geo_cols:
            tx_conn.execute(
                text(f"""
                    ALTER TABLE {self.schema}.{temp_table} 
                    ALTER COLUMN "{col.f_geometry_column}" 
                    TYPE geometry({col.type}, {col.srid})
                    USING "{col.f_geometry_column}"::geometry({col.type}, {col.srid})
                """)
            )

        return temp_table

    def _get_geometry_columns(
        self, table: str, conn: Connection | None = None
    ) -> Sequence[Row[Any]]:
        """Get a list of geometry columns, returning the a sequence of information
        about each row:

         - f_geometry_column: column name
         - type: geometry type
         - srid: coordinate system
         - coord_dimension: Number of dimensions

        Args:
            table (str): table to check
            conn (Connection | None): SQLAlcmemy connection to use, or None to use the
            object's connection property.

        Returns:
            Sequence[Row[Any]]: Geometry column rows. Each row contains the
            column name, geometry type, SRID, and number of dimensions.
        """

        tx_conn = self._parse_connection_arg(conn)

        sql = text("""
        SELECT f_geometry_column, type, srid, coord_dimension
        FROM geometry_columns
        WHERE f_table_schema = :schema
        AND f_table_name = :table
        """)

        result = tx_conn.execute(
            sql,
            {"schema": self.schema, "table": table},
        )

        return result.fetchall()

    def _parse_connection_arg(self, conn: Connection | None) -> Connection:
        """Parse an optional connection argument, return either the
        passed argument, or the object's active connection.

        Fails if conn and self.connection are both None

        Args:
            conn (_type_): Optional connection

        Raises:
            ConnectionError: Both the conn argument and self.connection are null

        Returns:
            Connection: connection to use, prioritizing conn
        """

        # Select the connection to use
        rv = conn or self.connection
        if rv is None:
            raise ConnectionError("Database connection failed")

        return rv


class InvalidInputError(TypeError):
    """Raised when invalid data prevents conversion of a dataframe to sql"""

    pass
