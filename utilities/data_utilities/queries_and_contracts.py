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

    model_config = ConfigDict(extra='forbid')
    
    @property
    def table_name(self) -> str:
        """The primary, instance-friendly way to get the table name."""
        return self._TABLE_NAME

    @property
    def entity_schema(self) -> Dict[str, str]:
        """The primary, instance-friendly way to get the schema."""
        return self._ENTITY_SCHEMA
    
    @classmethod
    def get_table_name_cls(cls) -> str:
        """Safe getter for class-level access (e.g., DataAccessor)."""
        return cls._TABLE_NAME
    
    @classmethod
    def get_entity_schema_cls(self) -> Dict[str, str]:
        """Safe getter for class-level access (e.g., DataAccessor)."""
        return cls._ENTITY_SCHEMA


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
    
# --- 2. Filter Model (No Change Needed for Table FQN) ---
# Filters apply to an EntityModel, so they don't need the table FQN themselves.
class SimpleEntityFilter(BaseEntity):
    """Pydantic model for filtering criteria for the SimpleEntityModel."""
    
    # We still need to inherit from BaseEntity to get the config/setup
    # but we don't need _table_name here.
    id_prefix: Optional[str] = None
    
    # Override config to be strict on filter inputs
    model_config = ConfigDict(extra='forbid')
    
    id: Optional[str] = Field(None, description="Filter by unique record ID.")
    type: Optional[str] = Field(None, description="Filter by the 'type' field.")
    time_after: Optional[datetime] = Field(None, description="Records created after this time.")
    time_before: Optional[datetime] = Field(None, description="Records created before this time.")

# --- 3. Raw Data Model (No Change) ---
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






class StreetSegmentEntityModel(BaseEntity):
    """
    Pydantic model representing street segments
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
    
    # Instance Fields (data types for Python/Pydantic validation)
    # Mapping BigQuery types to Python types: INTEGER -> int, STRING -> str, 
    # FLOAT -> float, TIMESTAMP -> datetime, GEOGRAPHY -> str
    objectid: int
    segment_id: int
    l_f_add: str
    l_t_add: str
    r_f_add: str
    r_t_add: str
    street_id: int
    pre_dir: str
    st_name: str
    st_type: str
    suf_dir: str
    alternate_name: str
    cfcc: str
    speed_limit: int
    oneway: str
    f_zlev: int
    t_zlev: int
    ft_cost: float
    tf_cost: float
    ft_dir: str
    tf_dir: str
    shield: str
    hwy_num: str
    mun_l: str
    mun_r: str
    nbhd_l: str
    nbhd_r: str
    state00_l: str
    state00_r: str
    county00_l: str
    county00_r: str
    mcd00_l: str
    mcd00_r: str
    shape_length_src: float
    shape_wkt: str
    geom: str # GEOGRAPHY type mapped to Python string
    batch_timestamp: datetime
    ingested_at: datetime
    batch: str
    source_name: str
    source_file: str
    schema_version: str
    length_m: float



class StreetSegmentFilterModel(BaseEntity):
    """
    Pydantic model for filtering criteria for the StreetSegmentEntityModel.

    Filters apply to an EntityModel, so they don't need the table FQN themselves.
    """
    
    # We still need to inherit from BaseEntity to get the config/setup
    # but we don't need _table_name or _ENTITY_SCHEMA here.
    
    # Override config to be strict on filter inputs
    model_config = ConfigDict(extra='forbid')
    
    # --- Exact Match Filters (for primary identifiers) ---
    objectid: Optional[int] = Field(None, description="Filter by exact OBJECTID.")
    segment_id: Optional[int] = Field(None, description="Filter by exact segment_id.")
    street_id: Optional[int] = Field(None, description="Filter by exact street_id.")

    # --- String/Text Filters (for name and type fields) ---
    st_name: Optional[str] = Field(None, description="Filter by exact street name (st_name).")
    st_name_contains: Optional[str] = Field(None, description="Filter where street name contains this substring (LIKE %value%).")
    st_type: Optional[str] = Field(None, description="Filter by exact street type (st_type).")
    cfcc: Optional[str] = Field(None, description="Filter by exact CFCC code.")
    oneway: Optional[str] = Field(None, description="Filter by ONESWAY status ('Y', 'N', etc.).")
    
    # --- Numeric Range Filters (for speed limit and length) ---
    speed_limit_min: Optional[int] = Field(None, description="Records with speed_limit greater than or equal to this value.")
    speed_limit_max: Optional[int] = Field(None, description="Records with speed_limit less than or equal to this value.")
    length_m_min: Optional[float] = Field(None, description="Records with length_m greater than or equal to this value.")
    length_m_max: Optional[float] = Field(None, description="Records with length_m less than or equal to this value.")

    # --- Timestamp Range Filters (for audit fields) ---
    batch_timestamp_after: Optional[datetime] = Field(None, description="Records batched after this time.")
    batch_timestamp_before: Optional[datetime] = Field(None, description="Records batched before this time.")
    ingested_at_after: Optional[datetime] = Field(None, description="Records ingested after this time.")
    ingested_at_before: Optional[datetime] = Field(None, description="Records ingested before this time.")
    
    # --- Spatial/Boundary Filters (common BigQuery/GIS pattern) ---
    # Although the geometry itself is a complex field, filters often involve
    # bounding box coordinates or spatial relationships.
    # A simple example: filtering by state/county names on the left side
    state00_l: Optional[str] = Field(None, description="Filter by state code on the left side.")
    county00_l: Optional[str] = Field(None, description="Filter by county code on the left side.")