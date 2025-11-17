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
    
    _ENTITY_SCHEMA: ClassVar[list[SchemaField]]
    _TABLE_NAME: ClassVar[str]

    model_config = ConfigDict(extra='forbid')


    @property
    def table_name(self) -> str:
        """The primary, instance-friendly way to get the table name."""
        return self._TABLE_NAME

    @property
    def entity_schema(self) -> list[SchemaField]:
        """The primary, instance-friendly way to get the schema."""
        return self._ENTITY_SCHEMA
    
    @classmethod
    def get_table_name_cls(cls) -> str:
        """Safe getter for class-level access (e.g., DataAccessor)."""
        return cls._TABLE_NAME
    
    @classmethod
    def get_entity_schema_cls(cls) -> list[SchemaField]:
        """Safe getter for class-level access (e.g., DataAccessor)."""
        return cls._ENTITY_SCHEMA


class SimpleEntityModel(BaseEntity):
    """Pydantic model representing a single record from the test table."""
    
    # Static metadata for the BigQuery table
    _TABLE_NAME: ClassVar[str] = TEST_TABLE_NAME
    
    # BigQuery Schema definition (using ClassVar for clarity)
    _ENTITY_SCHEMA: ClassVar[list[SchemaField]] = [
        SchemaField("id", "STRING"),
        SchemaField("type", "STRING"),
        SchemaField("time", "TIMESTAMP"), 
        SchemaField("location", "GEOGRAPHY"),
    ]
    
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