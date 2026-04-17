# utilities/data/queries_and_contracts.py
from typing import ClassVar, Dict

from pydantic import BaseModel, ConfigDict

TEST_TABLE_NAME = "test_table_for_db_accessor"


class BaseEntity(BaseModel):
    """
    Custom Base Model for all project-specific Pydantic entity and filter models.
    """

    _ENTITY_SCHEMA: ClassVar[Dict[str, str]]
    _TABLE_NAME: ClassVar[str]
    _SQL_QUERY: ClassVar[str] = None

    model_config = ConfigDict(extra="forbid")

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


class ValidatedBaseEntity(BaseEntity):
    """BaseEntity which will preserve the typing of your pydantic model as variables are assigned"""

    model_config = {"validate_assignment": True}
