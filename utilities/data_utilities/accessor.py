# utilities/data/accessor.py
from typing import Optional, Protocol, List, Dict, Any, Type, Union, Tuple, Literal
from google.cloud import bigquery
from google.oauth2 import service_account
import os 
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from google.cloud import bigquery
from google.cloud.bigquery import QueryJobConfig, SchemaField
from datetime import datetime, date


from .queries_and_contracts import BaseEntity

class BigQueryProfile(BaseModel):
    """Configuration for a specific BigQuery connection."""
    credentials_path: Optional[str] = None
    project_id: Optional[str] = None
    default_dataset: Optional[str] = None

# Model for the application's global settings
class AppSettings(BaseSettings):
    bigquery_profiles: Dict[str, BigQueryProfile] = {}
    active_profile: Optional[str] = "default" 
    # Configuration for how to load these settings
    model_config = SettingsConfigDict(
        env_file='config.toml', 
        env_file_encoding='utf-8' 
    )

DEFAULT_PROFILE = BigQueryProfile()

class QuerySpec(BaseModel):
    operation: Literal['SELECT', 'INSERT', 'DELETE']  
    
    table: str
    
    # For SELECT operations
    columns: List[str] = ['*']
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
        return 'NULL'
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
        
        # 1. Load configuration: Use the injected settings or load defaults (from toml/env).
        settings = settings if settings is not None else AppSettings()
        
        # 2. Get the specific profile config
        profile_name = settings.active_profile
        profile_config = settings.bigquery_profiles.get(
            profile_name, 
            DEFAULT_PROFILE # Use the empty default profile if name not found
        )

        client = None

        # --- 3. Try to load from the profile's specified path (Credentials) ---
        if profile_config.credentials_path:
            expanded_path = os.path.expanduser(profile_config.credentials_path)
            if os.path.exists(expanded_path):
                # Check if it's the standard user ADC file path
                is_user_adc = expanded_path.endswith('application_default_credentials.json')

                if is_user_adc:
                    # Skip loading this file explicitly and fall back to the generic ADC flow (Step 4),
                    # which is what Google recommends for user credentials.
                    print("Note: Skipping explicit load of user ADC file, relying on standard ADC flow.")
                    
                else:
                    # This must be a proper Service Account Key file (the original intent)
                    try:
                        credentials = service_account.Credentials.from_service_account_file(
                            expanded_path 
                        )
                        client = bigquery.Client(
                            credentials=credentials, 
                            project=profile_config.project_id or credentials.project_id,
                            default_dataset=profile_config.default_dataset 
                        )
                        print(f"Client initialized using Service Account from profile: '{profile_name}'")
                    except Exception as e:
                        # Log the MalformedError
                        print(f"Warning: Failed to load credentials from profile path. Falling back to ADC: {e}")
            
        # --- 4. Fallback (ADC) if client wasn't created above or was skipped (is_user_adc) ---
        if client is None:
            # Use the simple ADC call. This relies on the environment or the ADC file existing.
            client = bigquery.Client() 
            if profile_config.project_id:
                client.project = profile_config.project_id
            if profile_config.default_dataset:
                client.default_dataset = profile_config.default_dataset
            print("Client initialized using Application Default Credentials (ADC).")

        return cls(client=client)
    
    def _build_sql(self, query_spec: QuerySpec) -> str:
        """Internal: Builds BigQuery-specific SQL from QuerySpec (assumes SELECT or DELETE)."""
        
        if query_spec.operation == 'SELECT':
            
            # 1. Select Columns
            select_cols = ", ".join(query_spec.columns) if query_spec.columns else "*"
            sql = f"SELECT {select_cols} FROM `{query_spec.table}`"
            
            # 2. Add WHERE clause based on query_spec.filters 
            sql += _build_where_clause(query_spec)
            
            # 3. Add LIMIT/OFFSET
            if query_spec.limit is not None:
                sql += f" LIMIT {query_spec.limit}"

            return sql
            
        elif query_spec.operation == 'DELETE':
            sql = f"DELETE FROM `{query_spec.table}`"
            sql += _build_where_clause(query_spec)
            
            return sql

        
        # Handle unknown operations or operations not built here
        raise ValueError(f"Unsupported operation for SQL builder: {query_spec.operation}")

    def raw_sql(self, sql_query: str, parameters: Optional[Dict[str, Any]] = None) -> int | List[Dict[str, Any]]:
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
                    bigquery.ScalarQueryParameter(name, bq_type, value) # <--- FIXED
                )
            
            # Package the parameters inside a QueryJobConfig object
            job_config = QueryJobConfig(query_parameters=query_params)

        # Pass the job_config object
        query_job = self.client.query(sql_query, job_config=job_config)
        
        if query_job.num_dml_affected_rows is not None:
            return int(query_job.num_dml_affected_rows)
            
        return [dict(row) for row in query_job.result()]

    def streaming_insert(self, table_fqn: str, rows_to_insert: List[Dict], schema: List[SchemaField]) -> List[Dict[str, Any]]:
        """Inserts rows using the BigQuery streaming API. Returns list of errors."""
        table_ref = bigquery.Table.from_string(table_fqn)
        
        # This line is now correct because 'schema' is passed in the function call
        return self.client.insert_rows(
            table_ref, 
            rows_to_insert,
            selected_fields=schema
        )

    def _translate_schema(self, generic_schema_map: Dict[str, str]) -> List[SchemaField]:
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
        
        if query_spec.operation == 'SELECT' or query_spec.operation == 'DELETE':
            
            # 1. Build the SQL string (this now also populates query_spec.parameters)
            sql_query = self._build_sql(query_spec) 
            
            # 2. Then execute it using the raw_sql handler, passing the parameters
            return self.raw_sql(sql_query, parameters=query_spec.parameters)
            
        elif query_spec.operation == 'INSERT':
            
            if not query_spec.payload:
                return 0
                
            model_class = type(query_spec.payload[0]) # Get the class from the first item
            
            # 1. Retrieve the generic schema map
            try:
                generic_schema_map = query_spec.payload[0].entity_schema
            except AttributeError:
                raise ValueError(
                    f"Model '{model_class.__name__}' used in payload does not define a "
                    "working entity_schema_map." # 📝 CHANGED: Updated error message
                )
            
            # 1b. Translate the generic schema map to BQ-specific SchemaField list
            target_schema_bq = self._translate_schema(generic_schema_map)

            # 2. Convert BaseEntity models to raw dictionaries for BigQuery API
            raw_data = [d.model_dump() for d in query_spec.payload]
            
            # 3. Use the dedicated streaming API, passing the translated schema
            errors = self.streaming_insert(
                table_fqn=query_spec.table, 
                rows_to_insert=raw_data,
                schema=target_schema_bq
            )
            
            inserted_count = len(raw_data) - len(errors)
            
            if errors:
                # Log or handle the insert errors
                print(f"[ERROR] Streaming insert failed for {len(errors)} rows. First error: {errors[0]}")
                # Note: Returning the partial count might be acceptable in tests, 
                # but in production, you might want to raise an exception.

            return inserted_count
            
        else:
            raise ValueError(f"Unsupported operation type in QuerySpec: {query_spec.operation}")


class AccessorSelectQueryBuilder:
    """
    Helper class responsible for translating Pydantic Models 
    (Filter, Entity) into the client's internal QuerySpec.
    """
    
    # 1. Define the Suffix-Operator Map
    _SUFFIX_MAP = {
        '_gt': '>',
        '_gte': '>=',
        '_lt': '<',
        '_lte': '<='
    }

    _CUSTOM_RANGE_MAP = {
        'time_after': 'time_gt',
        'time_before': 'time_lt',
        'id_prefix': 'id_like', # NEW: For isolating test data
    }
    
    @staticmethod
    def build_query_spec(
        table_name: str,
        entity_model: Type[BaseEntity],
        filter_instance: BaseEntity,
        limit: Optional[int] = None
    ) -> QuerySpec:
        """
        Translates Pydantic input into a database-agnostic QuerySpec.
        """
        # 1. Columns: Select all fields defined in the Entity Model
        columns = list(entity_model.model_fields.keys())

        # 2. Filters: Map non-None fields from the Filter instance to QuerySpec filters
        filters = []
        for field_name, value in filter_instance.model_dump(exclude_none=True).items():
            
            # 1. Map custom descriptive fields to standard internal fields
            if field_name in AccessorSelectQueryBuilder._CUSTOM_RANGE_MAP:
                field_name = AccessorSelectQueryBuilder._CUSTOM_RANGE_MAP[field_name]
            
            # 2. Determine Column and Operator
            column_name = field_name
            operator = '='
            
            # Handle LIKE operator for id_prefix (mapped to id_like)
            if field_name == 'id_like':
                column_name = 'id'
                operator = 'LIKE'
                value = f"{value}%" # Add SQL wildcard for prefix match
            
            # Check for range filter suffixes (_gt, _lt, etc.)
            else:
                for suffix, op in AccessorSelectQueryBuilder._SUFFIX_MAP.items():
                    if field_name.endswith(suffix):
                        # Found a range filter
                        column_name = field_name.removesuffix(suffix)
                        operator = op
                        break # Exit the suffix check loop
            
            # Final filter addition
            filters.append((column_name, operator, value))

        # 3. Handle Offset (BigQuery supports LIMIT and OFFSET)
        final_limit = limit

        return QuerySpec(
            operation='SELECT',
            table=table_name,
            columns=columns,
            filters=filters,
            limit=final_limit
        )


class DataAccessor:
    def __init__(
        self, 
        table_prefix_map: Dict[Type[BaseEntity], str], 
        client: Optional[DataClient] = None, 
        config_path: Optional[str] = None
    ):
        """
        Initializes the accessor with the table prefix map and a BQ client.
        """
        self.table_prefix_map = table_prefix_map 
        
        if client:
            self.client = client
        elif config_path:
            # Assuming BigQueryClient has an appropriate class method for loading config
            self.client = BigQueryClient.initialize()
        else:
            self.client = BigQueryClient.initialize()
            
    def _get_table_fqn(self, entity_model: Type[BaseEntity]) -> str:
        """Internal helper to resolve the FQN from the provided model type."""
        
        # 1. Get the prefix (project.dataset) from the accessor's configuration
        try:
            prefix = self.table_prefix_map[entity_model]
        except KeyError:
            raise ValueError(
                f"Table prefix not found for model type: {entity_model.__name__}. "
                "Ensure it is included in the table_prefix_map dictionary."
            )
        
        # 2. Get the logical table name from the Pydantic model class
        # Note: We access the class attribute defined on the Pydantic model
        table_name = entity_model.get_table_name_cls()

        # 3. Stitch them together to form the FQN (e.g., project.dataset.table_name)
        return f"{prefix}.{table_name}"


    # --- 1. PRIMARY TYPE-SAFE GET METHOD ---
    def get(
        self, 
        entity_model: Type[BaseEntity],
        filter: BaseEntity,
        limit: Optional[int] = None
    ) -> Union[List[BaseEntity], BaseEntity]:
        """
        Retrieves data by translating the filter into a query, ensuring results 
        are validated against the specified entity_model.
        """
        # 1. Resolve table FQN
        table_fqn = self._get_table_fqn(entity_model)
        
        # 2. Build QuerySpec from Pydantic inputs
        query_spec = AccessorSelectQueryBuilder.build_query_spec(
            table_fqn,
            entity_model,
            filter,
            limit
        )
        
        # 3. Execute query (BigQueryClient handles the translation from QuerySpec to SQL)
        raw_results: List[Dict[str, Any]] = self.client.execute_query(query_spec)
        
        # 4. Validate and return 
        pydantic_results = [entity_model.model_validate(row) for row in raw_results]
        
        # Simple logic for single vs. list return (could be expanded later)
        if limit == 1 and pydantic_results:
            return pydantic_results[0]
            
        return pydantic_results


    # --- 2. RAW SQL ESCAPE HATCH ---
    def get_raw_sql(self, sql_query: str) -> List[Dict[str, Any]]:
        """
        Fetches raw data using a custom SQL query. 
        Returns a list of raw dictionaries (no Pydantic validation is performed).
        """
        # The client already has the raw_sql method defined. We just wrap it.
        # Note: Raw SQL cannot return BaseEntity safely.
        return self.client.raw_sql(sql_query)


    # --- 3. PUT METHOD ---
    def put(self, data: List[BaseEntity]) -> int:
        """
        Inserts data rows using the table name resolved from the entity model. 
        Returns the number of successfully inserted rows.
        """
        if not data:
            return 0
        
        # 1. Determine the target table and entity model
        entity_model = type(data[0])
        table_fqn = self._get_table_fqn(entity_model)
        
        # 2. Create the QuerySpec object for INSERT (using the data models as payload)
        # The client's execute_query method will handle the Pydantic-to-BigQuery translation.
        insert_spec = QuerySpec(
            operation='INSERT',
            table=table_fqn,
            payload=data
        )
        
        # ACT: Execute the insert operation
        # Use execute_query(), which handles the QuerySpec translation.
        affected_rows = self.client.execute_query(insert_spec)
        
        # The client returns the number of affected rows on success
        return affected_rows