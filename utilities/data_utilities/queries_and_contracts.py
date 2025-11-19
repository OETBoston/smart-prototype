# utilities/data/queries_and_contracts.py
from typing import Optional, List, Dict, Any, Union, ClassVar
from datetime import datetime
from pydantic import BaseModel, Field, RootModel, ConfigDict
from google.cloud.bigquery import SchemaField

TEST_TABLE_NAME = "test_table_for_db_accessor"

class BaseEntity(BaseModel):
    """
    Custom Base Model for all project-specific Pydantic entity and filter models.
    """
    
    _ENTITY_SCHEMA: ClassVar[Dict[str, str]] 
    _TABLE_NAME: ClassVar[str]
    _SQL_QUERY: ClassVar[str] = None

    model_config = ConfigDict(extra='forbid')
    
    @property
    def table_name(self) -> str:
        """The primary, instance-friendly way to get the table name."""
        return self._TABLE_NAME

    @property
    def entity_schema(self) -> Dict[str, str]:
        """The primary, instance-friendly way to get the schema."""
        return self._ENTITY_SCHEMA
    
    @property
    def sql_query(self) -> str:
        """None in normal circumstances, will replace normal search for model data"""
        return self._SQL_QUERY

    @classmethod
    def get_table_name_cls(cls) -> str:
        """Safe getter for class-level access (e.g., DataAccessor)."""
        return cls._TABLE_NAME
    
    @classmethod
    def get_entity_schema_cls(cls) -> Dict[str, str]:
        """Safe getter for class-level access (e.g., DataAccessor)."""
        return cls._ENTITY_SCHEMA
    
    @classmethod
    def get_sql_query(cls) -> str:
        """None in normal circumstances, will replace normal search for model data"""
        return cls._SQL_QUERY


class SimpleEntityModel(BaseEntity):
    """Pydantic model representing a single record from the test table."""
    
    # Static metadata for the BigQuery table
    _TABLE_NAME: ClassVar[str] = TEST_TABLE_NAME
    
    # BigQuery Schema definition (using ClassVar for clarity)
    _ENTITY_SCHEMA: ClassVar[Dict[str, str]] = { 
        "id": "STRING",
        "type": "STRING",
        "time": "TIMESTAMP", 
        "location": "GEOGRAPHY",
    }
    
    # Instance Fields (data types for Python/Pydantic validation)
    id: str
    type: str
    time: datetime
    location: str
    
class SimpleEntityFilter(BaseEntity):
    """
    Pydantic model for filtering criteria for a SimpleEntityModel.
    """
    
    # Override config to be strict on filter inputs
    model_config = ConfigDict(extra='forbid')
    
    # --- Exact Match Filters (Maps to column = value) ---
    id: Optional[str] = Field(None, description="Filter by exact record ID (column: 'id', operator: '=').")
    type: Optional[str] = Field(None, description="Filter by the exact type value (column: 'type', operator: '=').")
    
    # --- Prefix Match Filter (Maps to column LIKE value%) ---
    id_prefix: Optional[str] = Field(None, description="Filter where 'id' starts with this string (operator: 'LIKE').")
    
    # --- Range Filters (Maps to column > value or column < value) ---
    time_after: Optional[datetime] = Field(None, description="Records created strictly after this time (column: 'time', operator: '>').")
    time_before: Optional[datetime] = Field(None, description="Records created strictly before this time (column: 'time', operator: '<').")

class RawData(RootModel): # Inherit from RootModel
    # Use 'root' instead of '__root__'
    root: Dict[str, Any] 

    def __getitem__(self, key):
        # Access the validated data through .root
        return self.root[key]

# --- Union Type Alias for the Get Method Signature ---
EntityModel = SimpleEntityModel
EntityFilter = SimpleEntityFilter
GetReturnType = Union[List[EntityModel], EntityModel, List[RawData], RawData]






class StreetSegmentEntityBase(BaseEntity):
    """
    Pydantic model representing schema and table name for street segments
    """
    
    # Static metadata for the BigQuery table
    _TABLE_NAME: ClassVar[str] = "stg_street_segments"
    
    # BigQuery Schema definition (Field Name: BigQuery Data Type)
    _ENTITY_SCHEMA: ClassVar[Dict[str, str]] = { 
        "objectid": "INTEGER",
        "segment_id": "INTEGER",
        "l_f_add": "STRING",
        "l_t_add": "STRING",
        "r_f_add": "STRING",
        "r_t_add": "STRING",
        "street_id": "INTEGER",
        "pre_dir": "STRING",
        "st_name": "STRING",
        "st_type": "STRING",
        "suf_dir": "STRING",
        "alternate_name": "STRING",
        "cfcc": "STRING",
        "speed_limit": "INTEGER",
        "oneway": "STRING",
        "f_zlev": "INTEGER",
        "t_zlev": "INTEGER",
        "ft_cost": "FLOAT",
        "tf_cost": "FLOAT",
        "ft_dir": "STRING",
        "tf_dir": "STRING",
        "shield": "STRING",
        "hwy_num": "STRING",
        "mun_l": "STRING",
        "mun_r": "STRING",
        "nbhd_l": "STRING",
        "nbhd_r": "STRING",
        "state00_l": "STRING",
        "state00_r": "STRING",
        "county00_l": "STRING",
        "county00_r": "STRING",
        "mcd00_l": "STRING",
        "mcd00_r": "STRING",
        "shape_length_src": "FLOAT",
        "shape_wkt": "STRING",
        # GEOGRAPHY types are commonly handled as strings (WKT/GeoJSON) in Pydantic
        "geom": "GEOGRAPHY", 
        "batch_timestamp": "TIMESTAMP",
        "ingested_at": "TIMESTAMP",
        "batch": "STRING",
        "source_name": "STRING",
        "source_file": "STRING",
        "schema_version": "STRING",
        "length_m": "FLOAT",
    }

class StreetSegmentEntityModel(StreetSegmentEntityBase):
    """
    Pydantic model representing street segments
    """
    # Integer Fields
    objectid: Optional[int]
    segment_id: Optional[int]
    street_id: Optional[int]
    speed_limit: Optional[int]
    f_zlev: Optional[int]
    t_zlev: Optional[int]

    # Float Fields
    ft_cost: Optional[float]
    tf_cost: Optional[float]
    shape_length_src: Optional[float]
    length_m: Optional[float]

    # Timestamp Fields
    batch_timestamp: Optional[datetime]
    ingested_at: Optional[datetime]

    # String Fields (All 26 are now Optional)
    l_f_add: Optional[str]
    l_t_add: Optional[str]
    r_f_add: Optional[str]
    r_t_add: Optional[str]
    pre_dir: Optional[str]
    st_name: Optional[str]
    st_type: Optional[str]
    suf_dir: Optional[str]
    alternate_name: Optional[str]
    cfcc: Optional[str]
    oneway: Optional[str]
    ft_dir: Optional[str]
    tf_dir: Optional[str]
    shield: Optional[str]
    hwy_num: Optional[str]
    mun_l: Optional[str]
    mun_r: Optional[str]
    nbhd_l: Optional[str]
    nbhd_r: Optional[str]
    state00_l: Optional[str]
    state00_r: Optional[str]
    county00_l: Optional[str]
    county00_r: Optional[str]
    mcd00_l: Optional[str]
    mcd00_r: Optional[str]
    shape_wkt: Optional[str]
    batch: Optional[str]
    source_name: Optional[str]
    source_file: Optional[str]
    schema_version: Optional[str]
    
    # Geography Field (Mapped to String)
    geom: Optional[str]



class StreetSegmentFilterModel(BaseEntity):
    """
    Pydantic model for filtering criteria for the StreetSegmentEntityModel.
    """
    
    # Override config to be strict on filter inputs
    model_config = ConfigDict(extra='forbid')
    
    # --- 1. Exact Match Filters (Maps to column = value) ---
    objectid: Optional[int] = Field(None, description="Filter by exact OBJECTID.")
    segment_id: Optional[int] = Field(None, description="Filter by exact segment_id.")
    street_id: Optional[int] = Field(None, description="Filter by exact street_id.")
    cfcc: Optional[str] = Field(None, description="Filter by exact Functional Class Code (CFCC).")
    oneway: Optional[str] = Field(None, description="Filter by exact ONESWAY status (e.g., 'Y' or 'N').")
    
    # --- 2. Numeric Range Filters (Maps to >= and <=) ---
    speed_limit_min: Optional[int] = Field(None, description="Records with speed_limit greater than or equal to this value.")
    speed_limit_max: Optional[int] = Field(None, description="Records with speed_limit less than or equal to this value.")
    
    length_m_min: Optional[float] = Field(None, description="Records with length_m greater than or equal to this value.")
    length_m_max: Optional[float] = Field(None, description="Records with length_m less than or equal to this value.")

    # --- 3. Timestamp Range Filters (Maps to > and <) ---
    batch_timestamp_after: Optional[datetime] = Field(None, description="Records batched strictly after this time.")
    batch_timestamp_before: Optional[datetime] = Field(None, description="Records batched strictly before this time.")
    
    ingested_at_after: Optional[datetime] = Field(None, description="Records ingested strictly after this time.")
    ingested_at_before: Optional[datetime] = Field(None, description="Records ingested strictly before this time.")
    
    # --- 4. Text Search Filters (Maps to LIKE) ---
    st_name_prefix: Optional[str] = Field(None, description="Filter where st_name starts with this string (LIKE value%).")
    st_name_contains: Optional[str] = Field(None, description="Filter where st_name contains this string (LIKE %value%).")

    alternate_name_contains: Optional[str] = Field(None, description="Filter where alternate_name contains this string (LIKE %value%).")
    
    # --- 5. Geography/Metadata Filters (Exact match) ---
    state00_l: Optional[str] = Field(None, description="Filter by state code on the left side.")
    county00_l: Optional[str] = Field(None, description="Filter by county code on the left side.")


class RawSignAssetEntityBase(BaseEntity):
    """
    Pydantic model representing schema and table name for Raw Sign Asset data.
    """
    
    # --- Static metadata for the BigQuery table (following the sample structure) ---
    _TABLE_NAME: ClassVar[str] = "stg_cartegraph"  # Example table name
    
    # BigQuery Schema definition (Field Name: BigQuery Data Type)
    _ENTITY_SCHEMA: ClassVar[Dict[str, str]] = { 
        "oid": "INTEGER",
        "cartegraph_id": "STRING",
        "locator_address_number_field": "STRING",
        "locator_street_field": "STRING",
        "locator_city_field": "STRING",
        "address_number_field": "FLOAT",
        "street_field": "STRING",
        "neighborhood_field": "STRING",
        "city_field": "STRING",
        "county_field": "STRING",
        "state_field": "STRING",
        "height_field_amount": "FLOAT",
        "height_field_unit": "STRING",
        "width_field_amount": "FLOAT",
        "width_field_unit": "STRING",
        "mutcd_code_field": "STRING",
        "directionof_sign_arrow_field": "STRING",
        "sign_direction_field": "STRING",
        "sign_orientation_field": "STRING",
        "cg_last_modified_field": "TIMESTAMP",
        "entry_date_field": "TIMESTAMP",
        "replaced_field": "TIMESTAMP",
        "retired_field": "TIMESTAMP",
        "signalized_intersections_id_field": "STRING",
        "support_field": "STRING",
        "asset_status_field": "STRING",
        "special_sign_description_field": "STRING",
        "notes_field": "STRING",
        "geom": "GEOGRAPHY",
        "latitude": "FLOAT",
        "longitude": "FLOAT",
        "arrow_dir": "STRING",
        "geom_quality": "STRING",
        "address_quality": "STRING",
        "lifecycle_status": "STRING",
        "age_days": "INTEGER",
        "ingested_at": "TIMESTAMP",
        "batch_timestamp": "TIMESTAMP",
        "source_name": "STRING",
        "source_file": "STRING",
        "schema_version": "STRING",
    }


class RawSignAssetEntityModel(RawSignAssetEntityBase):
    """
    Pydantic model representing Raw Sign Asset data.
    """
    # --- Pydantic Field Definitions ---
    # All fields are Optional as per the 'NULLABLE' mode in the schema.

    # 1. Integer Fields (BigQuery: INTEGER)
    oid: Optional[int]
    age_days: Optional[int]

    # 2. Float Fields (BigQuery: FLOAT)
    address_number_field: Optional[float]
    height_field_amount: Optional[float]
    width_field_amount: Optional[float]
    latitude: Optional[float]
    longitude: Optional[float]

    # 3. Timestamp Fields (BigQuery: TIMESTAMP)
    cg_last_modified_field: Optional[datetime]
    entry_date_field: Optional[datetime]
    replaced_field: Optional[datetime]
    retired_field: Optional[datetime]
    ingested_at: Optional[datetime]
    batch_timestamp: Optional[datetime]

    # 4. String/Geography Fields (BigQuery: STRING, GEOGRAPHY)
    # GEOGRAPHY is typically mapped to a string (WKT/GeoJSON) in Pydantic models.
    cartegraph_id: Optional[str]
    locator_address_number_field: Optional[str]
    locator_street_field: Optional[str]
    locator_city_field: Optional[str]
    street_field: Optional[str]
    neighborhood_field: Optional[str]
    city_field: Optional[str]
    county_field: Optional[str]
    state_field: Optional[str]
    height_field_unit: Optional[str]
    width_field_unit: Optional[str]
    mutcd_code_field: Optional[str]
    directionof_sign_arrow_field: Optional[str]
    sign_direction_field: Optional[str]
    sign_orientation_field: Optional[str]
    signalized_intersections_id_field: Optional[str]
    support_field: Optional[str]
    asset_status_field: Optional[str]
    special_sign_description_field: Optional[str]
    notes_field: Optional[str]
    geom: Optional[str]  # GEOGRAPHY type handled as string
    arrow_dir: Optional[str]
    geom_quality: Optional[str]
    address_quality: Optional[str]
    lifecycle_status: Optional[str]
    source_name: Optional[str]
    source_file: Optional[str]
    schema_version: Optional[str]


class RawSignAssetFilterModel(BaseEntity):
    """
    Pydantic model for filtering criteria for the RawSignAsset entity.
    
    Uses standard suffixes for automatic mapping to SQL operators (e.g., LIKE, >=).
    """
    
    # Override config to be strict on filter inputs
    model_config = ConfigDict(extra='forbid')
    
    # --- 1. Exact Match Filters (Maps to column = value) ---
    oid: Optional[int] = Field(None, description="Filter by exact unique ID.")
    asset_status_field: Optional[str] = Field(None, description="Filter by exact asset status.")
    lifecycle_status: Optional[str] = Field(None, description="Filter by exact lifecycle status.")
    sign_direction_field: Optional[str] = Field(None, description="Filter by exact sign direction.")
    support_field: Optional[str] = Field(None, description="Filter by exact support type.")
    
    # --- 2. Numeric Range Filters (Maps to >= and <=) ---
    age_days_min: Optional[int] = Field(None, description="Assets older than or equal to this many days.")
    age_days_max: Optional[int] = Field(None, description="Assets newer than or equal to this many days.")
    
    height_field_amount_min: Optional[float] = Field(None, description="Minimum sign height amount.")
    width_field_amount_max: Optional[float] = Field(None, description="Maximum sign width amount.")

    latitude_min: Optional[float] = Field(None, description="Minimum latitude bound.")
    latitude_max: Optional[float] = Field(None, description="Maximum latitude bound.")
    longitude_min: Optional[float] = Field(None, description="Minimum longitude bound.")
    longitude_max: Optional[float] = Field(None, description="Maximum longitude bound.")

    # --- 3. Timestamp Range Filters (Maps to > and <) ---
    cg_last_modified_field_after: Optional[datetime] = Field(None, description="Records last modified strictly after this time.")
    cg_last_modified_field_before: Optional[datetime] = Field(None, description="Records last modified strictly before this time.")
    
    entry_date_field_after: Optional[datetime] = Field(None, description="Records entered strictly after this time.")
    entry_date_field_before: Optional[datetime] = Field(None, description="Records entered strictly before this time.")
    
    # --- 4. Text Search Filters (Maps to LIKE) ---
    cartegraph_id_prefix: Optional[str] = Field(None, description="Filter where cartegraph_id starts with this string (LIKE value%).")
    
    mutcd_code_field_contains: Optional[str] = Field(None, description="Filter where MUTCD code contains this substring (LIKE %value%).")
    
    locator_street_field_contains: Optional[str] = Field(None, description="Filter where street name contains this substring (LIKE %value%).")
    
    notes_field_contains: Optional[str] = Field(None, description="Filter where notes contain this substring (LIKE %value%).")


class RawSignAssetEntityModelWithAttachments(BaseEntity):
    """
    Model for a single Sign Asset record, derived from a JOIN 
    between stg_cartegraph and stg_cartegraph_attachments.

    NOTE: This model uses the _SQL_QUERY class variable for reading 
    and is NOT intended for single-table INSERT/DELETE operations.
    """

    asset_status_field: Optional[str]
    attachment_public_url: Optional[str]
    cartegraph_id: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]

    attachment_cg_last_modified_field: Optional[datetime]

    _TABLE_NAME: ClassVar[str] = "JOINED_ASSET_ATTACHMENTS"
    
    _SQL_QUERY: ClassVar[str] = """
        SELECT
            t1.asset_status_field,
            t1.cartegraph_id,
            t1.latitude,
            t1.longitude,
            t2.attachment_cg_last_modified_field,
            t2.attachment_public_url
        FROM
            `{table_prefix}.stg_cartegraph` AS t1
        LEFT JOIN (
            SELECT
                cartegraph_id,
                attachment_cg_last_modified_field,
                attachment_public_url,
                ROW_NUMBER() OVER (PARTITION BY cartegraph_id ORDER BY attachment_cg_last_modified_field DESC) AS rn
            FROM
                `{table_prefix}.stg_cartegraph_attachments`
        ) AS t2
            ON t1.cartegraph_id = t2.cartegraph_id
        WHERE t2.rn = 1 OR t2.rn IS NULL
    """

    # Strict configuration
    model_config = ConfigDict(extra='forbid')