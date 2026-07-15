from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict


class BlockfaceCreatorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Debug mode (Set this to True for debugging) True does not write to DB.
    debug_mode: bool

    # Input settings
    roadway_path: str

    # Dictionary of values to keep
    include_filters: Dict[str, list[Any]]

    # Dictionary of values to exclude
    exclude_filters: Dict[str, list[Any]]

    # Process parameters
    ft_crs: str
    ft_diff: float

    # Geometry adjustment
    adjust_geometry: bool

    # Local output settings
    output_path: str
    output_type: Literal["GeoJSON", "Parquet"]
    output_crs: str

    # Postgres DB export settings
    db_name: str
    db_schema: str
    job_name: str
    job_description: str
