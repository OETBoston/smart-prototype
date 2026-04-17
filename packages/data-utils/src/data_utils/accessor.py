# utilities/data_utils/accessor.py
import os
from datetime import date, datetime
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Type,
)

import geopandas as gpd
import pandas as pd
from google.cloud import bigquery
from google.cloud.bigquery import QueryJobConfig, SchemaField
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from shapely import wkt
from shapely.geometry.base import BaseGeometry

from .queries_and_contracts import BaseEntity


class BigQueryProfile(BaseModel):
    """Configuration for a specific BigQuery connection."""

    credentials_path: Optional[str] = None
    project_id: Optional[str] = None
    default_dataset: Optional[str] = None


# Model for the application's global settings
class AppSettings(BaseSettings):
    bigquery_profiles: Dict[str, BigQueryProfile] = {}
    active_profile: Optional[str] = "default_profile"
    # Configuration for how to load these settings
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8", env_prefix="db_access_", extra="ignore"
    )
    active_client: str = "default_client"
    active_environment: str = "default_env"
    environment_prefixes: Dict[str, str] = {}


DEFAULT_PROFILE = BigQueryProfile()


class QuerySpec(BaseModel):
    operation: Literal["SELECT", "INSERT", "DELETE"]

    table: str

    # For SELECT operations
    columns: List[str] = ["*"]
    filters: List[Tuple[str, str, Any]] = []
    limit: Optional[int] = None

    payload: Optional[List[BaseEntity]] = None
    parameters: Dict[str, Any] = {}


class DataClient(Protocol):
    def execute_query(self, sql_query: str) -> Any: ...


def _sql_value(value):
    """Encases string values in quotes, leaves numbers/bools as-is."""
    if isinstance(value, str):
        # Encapsulate the string
        return f"'{value}'"
    if value is None:
        return "NULL"
    return str(value)


# Helper to build the WHERE clause string
def _build_where_clause(query_spec: QuerySpec) -> str:
    """Translates filters into a named parameterized SQL WHERE clause."""
    if not query_spec.filters:
        return ""

    conditions = []
    # Clear parameters before building the clause
    query_spec.parameters.clear()

    for i, (column, operator, value) in enumerate(query_spec.filters):
        # 1. Create a unique parameter name
        param_name = f"p{i}_{column.replace('.', '_')}"

        # 2. Use the named placeholder (@name) in the SQL string
        condition = f"{column} {operator} @{param_name}"
        conditions.append(condition)

        # 3. Add the actual value to the parameters dictionary
        query_spec.parameters[param_name] = value

    return " WHERE " + " AND ".join(conditions)


class BigQueryClient:
    """A realistic client for executing queries against Google BigQuery."""

    def __init__(self, client: bigquery.Client):
        self.client = client
        self.project_id = client.project

    @classmethod
    def initialize(cls, settings: Optional[AppSettings] = None):
        """Initializes the client by loading settings and selecting the active profile."""

        settings = settings or AppSettings()

        profile = settings.bigquery_profiles.get(
            settings.active_profile, BigQueryProfile()
        )

        # If the user explicitly gave a service-account file:
        if profile.credentials_path:
            expanded = os.path.expanduser(profile.credentials_path)
            return cls(
                bigquery.Client.from_service_account_json(
                    expanded,
                    project=profile.project_id,
                )
            )

        # Otherwise: rely fully on ADC
        return cls(
            bigquery.Client(
                project=profile.project_id,
            )
        )

    def _build_sql(self, query_spec: QuerySpec) -> str:
        """Internal: Builds BigQuery-specific SQL from QuerySpec (assumes SELECT or DELETE)."""

        if query_spec.operation == "SELECT":
            # 1. Select Columns
            select_cols = ", ".join(query_spec.columns) if query_spec.columns else "*"
            sql = f"SELECT {select_cols} FROM `{query_spec.table}`"

            # 2. Add WHERE clause based on query_spec.filters
            sql += _build_where_clause(query_spec)

            # 3. Add LIMIT/OFFSET
            if query_spec.limit is not None:
                sql += f" LIMIT {query_spec.limit}"

            return sql

        elif query_spec.operation == "DELETE":
            sql = f"DELETE FROM `{query_spec.table}`"
            sql += _build_where_clause(query_spec)

            return sql

        # Handle unknown operations or operations not built here
        raise ValueError(
            f"Unsupported operation for SQL builder: {query_spec.operation}"
        )

    def raw_sql(
        self, sql_query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> int | List[Dict[str, Any]]:
        """Executes a raw SQL query (SELECT or DML) and waits for completion."""

        job_config = None

        if parameters:
            # Convert the parameters dictionary into a list of BigQuery ScalarQueryParameter objects
            query_params = []
            for name, value in parameters.items():
                bq_type = "STRING"
                if isinstance(value, datetime):
                    bq_type = "TIMESTAMP"
                elif isinstance(value, date):
                    bq_type = "DATE"
                elif isinstance(value, int):
                    bq_type = "INT64"
                elif isinstance(value, float):
                    bq_type = "FLOAT64"
                elif isinstance(value, bool):
                    bq_type = "BOOL"
                query_params.append(
                    # NOTE: We pass the BQ type as a string
                    bigquery.ScalarQueryParameter(name, bq_type, value)  # <--- FIXED
                )

            # Package the parameters inside a QueryJobConfig object
            job_config = QueryJobConfig(query_parameters=query_params)

        # Pass the job_config object
        query_job = self.client.query(sql_query, job_config=job_config)

        if query_job.num_dml_affected_rows is not None:
            return int(query_job.num_dml_affected_rows)

        return [dict(row) for row in query_job.result()]

    def streaming_insert(
        self, table_fqn: str, rows_to_insert: List[Dict], schema: List[SchemaField]
    ) -> List[Dict[str, Any]]:
        """Inserts rows using the BigQuery streaming API. Returns list of errors."""
        table_ref = bigquery.Table.from_string(table_fqn)

        # This line is now correct because 'schema' is passed in the function call
        return self.client.insert_rows(
            table_ref, rows_to_insert, selected_fields=schema
        )

    def _translate_schema(
        self, generic_schema_map: Dict[str, str]
    ) -> List[SchemaField]:
        """Translates a generic schema map into BigQuery SchemaField objects."""
        bq_schema = []
        for name, type_str in generic_schema_map.items():
            # Use the provided type string directly
            bq_schema.append(SchemaField(name, type_str.upper()))
        return bq_schema

    def execute_query(self, query_spec: QuerySpec) -> int | List[Dict[str, Any]]:
        """
        Executes a query or DML operation based on the QuerySpec.
        Returns: int (affected rows) for DML/INSERT, List[Dict] for SELECT.
        """

        if query_spec.operation == "SELECT" or query_spec.operation == "DELETE":
            # 1. Build the SQL string (this now also populates query_spec.parameters)
            sql_query = self._build_sql(query_spec)

            # 2. Then execute it using the raw_sql handler, passing the parameters
            return self.raw_sql(sql_query, parameters=query_spec.parameters)

        elif query_spec.operation == "INSERT":
            if not query_spec.payload:
                return 0

            model_class = type(
                query_spec.payload[0]
            )  # Get the class from the first item

            # 1. Retrieve the generic schema map
            try:
                generic_schema_map = query_spec.payload[0].entity_schema
            except AttributeError:
                raise ValueError(
                    f"Model '{model_class.__name__}' used in payload does not define a "
                    "working entity_schema_map."  # 📝 CHANGED: Updated error message
                )

            # 1b. Translate the generic schema map to BQ-specific SchemaField list
            target_schema_bq = self._translate_schema(generic_schema_map)

            # 2. Convert BaseEntity models to raw dictionaries for BigQuery API
            raw_data = [d.model_dump() for d in query_spec.payload]

            # 3. Use the dedicated streaming API, passing the translated schema
            errors = self.streaming_insert(
                table_fqn=query_spec.table,
                rows_to_insert=raw_data,
                schema=target_schema_bq,
            )

            inserted_count = len(raw_data) - len(errors)

            if errors:
                # Log or handle the insert errors
                print(
                    f"[ERROR] Streaming insert failed for {len(errors)} rows. First error: {errors[0]}"
                )
                # Note: Returning the partial count might be acceptable in tests,
                # but in production, you might want to raise an exception.

            return inserted_count

        else:
            raise ValueError(
                f"Unsupported operation type in QuerySpec: {query_spec.operation}"
            )


class AccessorSelectQueryBuilder:
    """
    Helper class responsible for translating Pydantic Models
    (Filter, Entity) into the client's internal QuerySpec using
    a convention-based, maintainable approach.
    """

    # Define a single source of truth for all range/special filters.
    # Sorted by length (descending) to ensure that longer suffixes
    # (like '_gte') are checked before shorter ones (like '_gt').
    _FILTER_CONVENTIONS = sorted(
        {
            "_min": ">=",  # Descriptive: e.g., speed_limit_min
            "_max": "<=",  # Descriptive: e.g., speed_limit_max
            "_gte": ">=",  # Standard: Greater Than or Equal To
            "_lte": "<=",  # Standard: Less Than or Equal To
            "_gt": ">",
            "_lt": "<",
            "_after": ">",  # Descriptive: e.g., batch_timestamp_after
            "_before": "<",  # Descriptive: e.g., batch_timestamp_before
            "_contains": "LIKE",  # Requires value modification: %value%
            "_prefix": "LIKE",  # Requires value modification: value%
            "_suffix": "LIKE",  # Requires value modification: %value
        }.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    @staticmethod
    def build_query_spec(
        table_name: str,
        entity_model: Type[BaseEntity],
        filter_instance: BaseEntity,
        limit: Optional[int] = None,
    ) -> QuerySpec:
        """
        Translates Pydantic filter input into a QuerySpec, supporting:
        - minimal=True  → SELECT only filter + included fields
        - xxx_included=True → explicit opt-in projection
        """

        # ------------------------------------------------------------
        # 0A. Reject unknown fields even if Pydantic was bypassed
        # ------------------------------------------------------------
        allowed = set(filter_instance.model_fields.keys())
        actual = set(filter_instance.__dict__.keys())

        unknown = actual - allowed
        if unknown:
            invalid = ", ".join(sorted(unknown))
            valid = ", ".join(sorted(allowed))
            raise ValueError(
                f"Unknown filter fields: {invalid}. "
                f"Valid filter fields are: {valid}. "
                f"This may occur if the filter was constructed using model_construct(), "
                f"which bypasses validation."
            )

        # --------------------------------------------
        # 0. Prep for projection logic
        # --------------------------------------------

        # All columns in the entity model (only used when minimal=False)
        entity_fields = list(entity_model.model_fields.keys())

        included_fields: set[str] = set()  # fields explicitly included
        filter_columns: set[str] = set()  # columns referenced by filters

        minimal: bool = getattr(filter_instance, "minimal", False)

        # --------------------------------------------
        # 1. Parse filters and included flags
        # --------------------------------------------

        filters = []

        for field_name, value in filter_instance.model_dump(exclude_none=True).items():
            # Skip the switch itself
            if field_name == "minimal":
                continue

            # Handle xxx_included=True → include "xxx" in projection
            if field_name.endswith("_included") and value is True:
                included_fields.add(field_name.removesuffix("_included"))
                continue

            # Otherwise: treat it as a filtering field
            column_name = field_name
            operator = "="
            final_value = value

            # Look for suffix conventions (_contains, _min, etc.)
            matched = False
            for suffix, op in AccessorSelectQueryBuilder._FILTER_CONVENTIONS:
                if (
                    field_name.endswith(suffix)
                    and field_name[: -len(suffix)] in entity_model.model_fields
                ):
                    matched = True
                    column_name = field_name.removesuffix(suffix)
                    operator = op

                    # Apply LIKE transformations
                    if suffix == "_contains":
                        final_value = f"%{value}%"
                    elif suffix == "_prefix":
                        final_value = f"{value}%"
                    elif suffix == "_suffix":
                        final_value = f"%{value}"
                    break

            filters.append((column_name, operator, final_value))
            filter_columns.add(column_name)

        unknown = filter_columns - set(entity_model.model_fields.keys())
        if unknown:
            raise ValueError(f"Unknown filter fields: {unknown}")

        # --------------------------------------------
        # 2. Determine projection columns
        # --------------------------------------------

        if minimal:
            # Minimal = only fields required by filters + explicit includes
            columns = set(filter_columns) | included_fields

            # If minimal produced no columns, fallback to "*"
            if not columns:
                columns = {"*"}

            columns = list(columns)

        else:
            # Non-minimal = SELECT *
            columns = entity_fields

        # --------------------------------------------
        # 3. Assemble QuerySpec
        # --------------------------------------------

        return QuerySpec(
            operation="SELECT",
            table=table_name,
            columns=columns,
            filters=filters,
            limit=limit,
        )


CLIENT_REGISTRY: Dict[str, Callable[..., DataClient]] = {
    "bigquery": BigQueryClient.initialize,
}


GEOMETRY_SOURCE_COLUMNS = [
    "shape_wkt",  # Standard WKT column (street segments use this)
    "geometry",  # BigQuery GEOGRAPHY (stringified)
    "geom_wkt",  # Optional: some ETL pipelines produce this
    "geom_json",  # If you ever support GeoJSON text
    "wkt",  # Minimalistic WKT naming
]


def initialize_accessor_client_from_config(
    settings: AppSettings, client_key: str
) -> DataClient:
    """Uses the client key to find and execute the correct initializer."""
    initializer = CLIENT_REGISTRY.get(client_key)

    if initializer is None:
        raise ValueError(f"Unknown client specified in config: '{client_key}'")

    return initializer(settings=settings)


def entities_to_data_frame(entities: Sequence[BaseEntity]) -> pd.DataFrame:
    """
    Convert a sequence of Pydantic entities into a pandas DataFrame.
    """
    return pd.DataFrame([e.model_dump() for e in entities])


def data_frame_to_geo_data_frame(
    data_frame: pd.DataFrame,
    initial_crs: Optional[str] = "EPSG:4326",
    target_crs: Optional[str] = "EPSG:4326",
    split_multiline_string: Optional[bool] = False,
    geom_source_col: Optional[str] = None,
    ignore_bad_geometry: bool = False,
) -> gpd.GeoDataFrame:
    """
    Retrieve data and convert it to a GeoDataFrame using a flexible set of allowed
    geometry source columns.
    """

    df = data_frame

    if df.empty:
        return gpd.GeoDataFrame(df.copy(), geometry="geometry", crs=initial_crs)

    # -------------------------------------------------
    # 1. Determine geometry source column
    # -------------------------------------------------
    if geom_source_col:
        if geom_source_col not in df.columns:
            raise ValueError(
                f"geom_source_col='{geom_source_col}' not found in DataFrame. "
                f"Available: {list(df.columns)}"
            )
        source_col = geom_source_col
    else:
        # Scan common list in order
        source_col = None
        for candidate in GEOMETRY_SOURCE_COLUMNS:
            if candidate in df.columns:
                source_col = candidate
                break

        if not source_col:
            raise ValueError(
                f"No acceptable geometry column found. "
                f"Expected one of: {GEOMETRY_SOURCE_COLUMNS}, or pass geom_source_col."
            )

    # -------------------------------------------------
    # 2. Convert to Shapely geometry
    # -------------------------------------------------
    def parse_geom(value, index):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            if ignore_bad_geometry:
                # logger.warning(f"NULL geometry at row {index}; dropping row.")
                return None
            raise ValueError(f"NULL geometry at row {index} (col={source_col}).")

        # Already Shapely?
        if hasattr(value, "geom_type"):
            return value

        if isinstance(value, str) and value.strip():
            try:
                return wkt.loads(value)
            except Exception as exc:
                if ignore_bad_geometry:
                    # logger.warning(f"Bad WKT at row {index}: {value!r} — {exc}")
                    return None
                raise ValueError(
                    f"Failed to parse geometry at row {index}: {value!r}"
                ) from exc

        if ignore_bad_geometry:
            # logger.warning(f"Unsupported geometry at row {index}: {value!r}")
            return None

        raise ValueError(f"Unsupported geometry type at row {index}: {value!r}")

    df["geometry"] = [parse_geom(val, idx) for idx, val in df[source_col].items()]

    df.dropna(subset=["geometry"], inplace=True)

    # -------------------------------------------------
    # 3. Convert to GeoDataFrame & reproject
    # -------------------------------------------------
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=initial_crs)

    if gdf.crs and target_crs and gdf.crs.to_string() != target_crs:
        gdf = gdf.to_crs(target_crs)

    if split_multiline_string:
        gdf = gdf.explode(ignore_index=True)

    return gdf


def geo_data_frame_to_data_frame(
    gdf: gpd.GeoDataFrame,
    geometry_col: str = "geometry",
    serialize_wkt: bool = True,
    drop_geometry: bool = False,
) -> pd.DataFrame:
    """
    Converts a GeoDataFrame into a regular DataFrame.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Input GeoDataFrame.
    geometry_col : str
        Geometry column to extract.
    serialize_wkt : bool
        If True, geometry objects are converted to WKT strings.
    drop_geometry : bool
        If True, geometry column is removed entirely.

    Returns
    -------
    pd.DataFrame
        A non-geo DataFrame representation of the input.
    """

    if gdf.empty:
        return pd.DataFrame()

    df = gdf.copy()

    if geometry_col not in df.columns:
        raise ValueError(
            f"geometry_col='{geometry_col}' not found. Columns: {list(df.columns)}"
        )

    if drop_geometry:
        df = df.drop(columns=[geometry_col])
    else:
        if serialize_wkt:
            df[geometry_col] = df[geometry_col].apply(
                lambda geom: geom.wkt if isinstance(geom, BaseGeometry) else geom
            )
    return pd.DataFrame(df)


def data_frame_to_entities(
    df: pd.DataFrame,
    entity_model: Type[BaseEntity],
    geometry_col: Optional[str] = None,
    parse_wkt: bool = True,
    ignore_bad_geometry: bool = False,
    ignore_extra_fields: bool = False,
) -> List[BaseEntity]:
    if df.empty:
        return []

    # Convert NaN → None to support Pydantic optional fields
    df_processed = df.copy().where(pd.notnull(df), None)

    # -------------------------------
    # Convert WKT → geometry (if specified)
    # -------------------------------
    if geometry_col and geometry_col in df_processed.columns:

        def parse_geom(val, idx):
            if val is None:
                if ignore_bad_geometry:
                    return None
                raise ValueError(f"NULL geometry in row {idx}")

            # Already a shapely geometry?
            if hasattr(val, "geom_type"):
                return val

            # Parse WKT string
            if parse_wkt and isinstance(val, str):
                try:
                    return wkt.loads(val)
                except Exception as e:
                    if ignore_bad_geometry:
                        return None
                    raise ValueError(
                        f"Failed to parse WKT geometry in row {idx}: {val}"
                    ) from e

            if ignore_bad_geometry:
                return None

            raise ValueError(f"Unsupported geometry in row {idx}: {val!r}")

        df_processed[geometry_col] = [
            parse_geom(v, i) for i, v in df_processed[geometry_col].items()
        ]

        if ignore_bad_geometry:
            df_processed.dropna(subset=[geometry_col], inplace=True)

    # -------------------------------
    # Convert rows to Pydantic objects
    # -------------------------------
    entities: List[EntityT] = []

    valid_fields = set(entity_model.model_fields.keys())

    for idx, row in df_processed.iterrows():
        raw_dict = row.to_dict()

        if ignore_extra_fields:
            as_dict = {k: v for k, v in raw_dict.items() if k in valid_fields}
        else:
            as_dict = raw_dict

        try:
            entity = entity_model(**as_dict)
            entities.append(entity)
        except Exception as e:
            if ignore_bad_geometry and geometry_col:
                continue
            raise ValueError(
                f"Failed to construct entity at row {idx}\n"
                f"Row dict: {as_dict}\n"
                f"Error: {e}"
            ) from e

    return entities


class DataAccessor:
    def __init__(
        self,
        table_prefix_map: Optional[Dict[str, str]] = None,
        current_prefix: Optional[str] = None,
        client: Optional["DataClient"] = None,
        config_path: Optional[str] = None,
    ):
        """
        Initializes the accessor with the standard priority:
        1. Explicit arguments
        2. OS Environment Variables (via AppSettings)
        3. Config File (via config_path, loaded by AppSettings)
        """

        settings = AppSettings(_env_file=config_path)

        if client:
            self.client = client
        else:
            client_key = settings.active_client
            self.client = initialize_accessor_client_from_config(settings, client_key)

        if table_prefix_map:
            self.table_prefix_map = table_prefix_map
        else:
            self.table_prefix_map = settings.environment_prefixes

        if current_prefix:
            self.current_prefix = current_prefix
        else:
            env_key = settings.active_environment
            prefix = self.table_prefix_map.get(env_key)

            if not prefix:
                raise ValueError(
                    f"No database prefix found for environment: '{env_key}'. "
                    f"Check DB_ACCESS_ACTIVE_ENVIRONMENT setting and the environment_prefixes map."
                )
            self.current_prefix = prefix

    def _get_table_fqn(self, entity_model: Type[BaseEntity]) -> str:
        """Internal helper to resolve the FQN from the provided model type."""

        # 1. Get the prefix (project.dataset) from the accessor's configuration
        prefix = self.current_prefix

        # 2. Get the logical table name from the Pydantic model class
        # Note: We access the class attribute defined on the Pydantic model
        table_name = entity_model.get_table_name_cls()

        # 3. Stitch them together to form the FQN (e.g., project.dataset.table_name)
        return f"{prefix}.{table_name}"

    def get_as_geo_data_frame(
        self,
        entity_model: Type[BaseEntity],
        filter: BaseEntity,
        limit: Optional[int] = None,
        initial_crs: Optional[str] = "EPSG:4326",
        target_crs: Optional[str] = "EPSG:4326",
        split_multiline_string: Optional[bool] = False,
        geom_source_col: Optional[str] = None,
        ignore_bad_geometry: bool = False,
    ) -> gpd.GeoDataFrame:
        """
        Retrieve data and convert it to a GeoDataFrame using a flexible set of allowed
        geometry source columns.
        """

        df = self.get_as_data_frame(
            entity_model=entity_model, filter=filter, limit=limit
        )

        return data_frame_to_geo_data_frame(
            data_frame=df,
            initial_crs=initial_crs,
            target_crs=target_crs,
            split_multiline_string=split_multiline_string,
            geom_source_col=geom_source_col,
            ignore_bad_geometry=ignore_bad_geometry,
        )

    def get_as_data_frame(
        self,
        entity_model: Type[BaseEntity],
        filter: BaseEntity,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Retrieves data by translating the filter into a query, ensuring results
        are validated against the specified entity_model.
        """
        return entities_to_data_frame(
            self.get(entity_model=entity_model, filter=filter, limit=limit)
        )

    def get(
        self,
        entity_model: Type[BaseEntity],
        filter: BaseEntity,
        limit: Optional[int] = None,
    ) -> List[BaseEntity]:
        """
        Retrieves data by translating the filter into a query, ensuring results
        are validated against the specified entity_model.
        """

        raw_results = None
        if entity_model.get_sql_query() == None:
            # 1. Resolve table FQN
            table_fqn = self._get_table_fqn(entity_model)

            # 2. Build QuerySpec from Pydantic inputs
            query_spec = AccessorSelectQueryBuilder.build_query_spec(
                table_fqn, entity_model, filter, limit
            )

            # 3. Execute query (BigQueryClient handles the translation from QuerySpec to SQL)
            raw_results: List[Dict[str, Any]] = self.client.execute_query(query_spec)
        else:
            raw_sql_template = entity_model.get_sql_query()
            final_sql = raw_sql_template.format(table_prefix=self.current_prefix)
            raw_results = self.get_raw_sql(final_sql)

        # 4. Validate and return
        pydantic_results = [entity_model.model_validate(row) for row in raw_results]

        return pydantic_results

    def get_raw_sql(self, sql_query: str) -> List[Dict[str, Any]]:
        """
        Fetches raw data using a custom SQL query.
        Returns a list of raw dictionaries (no Pydantic validation is performed).
        """
        # The client already has the raw_sql method defined. We just wrap it.
        # Note: Raw SQL cannot return BaseEntity safely.
        return self.client.raw_sql(sql_query)

    def put(self, data: List[BaseEntity], max_batch_size: int = 1000) -> int:
        if not data:
            return 0

        entity_model = type(data[0])
        table_fqn = self._get_table_fqn(entity_model)

        total_inserted = 0

        for i in range(0, len(data), max_batch_size):
            batch = data[i : i + max_batch_size]
            insert_spec = QuerySpec(operation="INSERT", table=table_fqn, payload=batch)
            total_inserted += self.client.execute_query(insert_spec)

        return total_inserted

    def put_data_frame(
        self,
        df: pd.DataFrame,
        entity_model: Type[BaseEntity],
        geometry_col: Optional[str] = None,
        parse_wkt: bool = True,
        ignore_bad_geometry: bool = False,
        ignore_extra_fields: bool = False,
        max_batch_size: int = 1000,
    ) -> int:
        """
        Inserts data rows using the table name resolved from a dataframe which matches an entity model.
        Returns the number of successfully inserted rows.
        """
        self.put(
            entities_to_data_frame(
                df=df,
                entity_model=entity_model,
                geometry_col=geometry_col,
                parse_wkt=parse_wkt,
                ignore_bad_geometry=ignore_bad_geometry,
                ignore_extra_fields=ignore_extra_fields,
            ),
            max_batch_size=max_batch_size,
        )

    def put_geo_data_frame(
        self,
        gdf: gpd.GeoDataFrame,
        entity_model: Type[BaseEntity],
        geometry_col: str,
        serialize_wkt: bool = True,
        drop_geometry: bool = False,
        parse_wkt: bool = True,
        ignore_bad_geometry: bool = False,
        ignore_extra_fields: bool = False,
        max_batch_size: int = 1000,
    ) -> int:
        """
        Inserts data rows into the database from a GeoDataFrame.

        Workflow:
            GeoDataFrame → DataFrame (WKT-serialized) → Pydantic entities → INSERT

        Parameters
        ----------
        gdf : gpd.GeoDataFrame
            GeoDataFrame containing the data to insert.
        entity_model : Type[BaseEntity]
            Pydantic model representing the DB table schema.
        geometry_col : str
            Name of the geometry column in the GeoDataFrame.
            Defaults to 'geometry'.
        serialize_wkt : bool
            If True, Shapely geometries are serialized into WKT strings.
        drop_geometry : bool
            If True, the geometry column is removed entirely.
        parse_wkt : bool
            If True, WKT strings (if present) are parsed back into Shapely objects
            when building Pydantic entities.
        ignore_bad_geometry : bool
            If True, rows with invalid/missing geometry are skipped.

        Returns
        -------
        int
            Number of rows successfully inserted.
        """

        if not geometry_col:
            raise ValueError(
                "You must supply `geometry_col` when calling put_geo_data_frame().\n"
                "Example: put_geo_data_frame(gdf, MyModel, geometry_col='geometry')"
            )

        if geometry_col not in gdf.columns:
            raise ValueError(
                f"Geometry column '{geometry_col}' was not found in the GeoDataFrame.\n"
                f"Available columns: {list(gdf.columns)}\n\n"
                "Make sure you pass the correct column name. "
                "If your geometry column is actually named something else, do:\n"
                f"    put_geo_data_frame(gdf, {entity_model.__name__}, geometry_col='your_column')"
            )

        if gdf.empty:
            return 0

        # 1. Convert GeoDataFrame → regular DataFrame (with WKT if desired)
        df = geo_data_frame_to_data_frame(
            gdf=gdf,
            geometry_col=geometry_col,
            serialize_wkt=serialize_wkt,
            drop_geometry=drop_geometry,
        )

        # 2. Convert DataFrame → list of Pydantic entities
        entities = data_frame_to_entities(
            df=df,
            entity_model=entity_model,
            geometry_col=None if drop_geometry else geometry_col,
            parse_wkt=parse_wkt,
            ignore_bad_geometry=ignore_bad_geometry,
            ignore_extra_fields=ignore_extra_fields,
        )

        if not entities:
            return 0

        # 3. Insert into the backend
        return self.put(entities, max_batch_size=max_batch_size)
