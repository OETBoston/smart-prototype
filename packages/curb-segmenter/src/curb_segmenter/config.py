from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


def to_lowercase(value: str) -> str:
    """Pydantic validator to convert string values to lowercase"""
    return value.lower()


class AssetsConfig(BaseModel):
    """Configuration for assets to be processed by curb segmenter"""

    class AssetConfig(BaseModel):
        """Base configuration for assets. May be extended for specific asset types."""

        new_id_col: str
        job_id: str

    class FireHydrantConfig(AssetConfig):
        """Extended AssetConfig for fire hydrants"""

        buffer_distance_ft: float

    class BusStopConfig(AssetConfig):
        """Extended AssetConfig for bus stops"""

        class StopTypesConfig(BaseModel):
            class StopTypeConfig(BaseModel):
                range: list[float] = Field(min_length=2, max_length=2)
                inclusive: bool
                buffer_multiplier: float

            near_side: StopTypeConfig
            far_side: StopTypeConfig
            mid_block: StopTypeConfig

        stop_types: StopTypesConfig

    parking_sign: AssetConfig
    bus_stop: BusStopConfig
    fire_hydrant: FireHydrantConfig
    parking_meters: AssetConfig


class CurbSegmenterConfig(BaseModel):
    """Configuration settings for curb segmenter"""

    # Postgres DB export settings
    db_name: str
    db_schema: str
    job_name: str
    job_description: str

    # Debug mode (Set this to True for debugging) True does not write to DB.
    debug_mode: bool

    # Project settings
    proj_crs: str

    # Input Blockface data settings
    bf_table_name: str
    bf_geom_col: str
    bf_job_id: str

    # Input Asset Table Specifications
    assets: AssetsConfig

    # Process parameters
    curb_id_col: str
    min_curb_len_ft: float
    eps_fraction: float
    snap_tolerance_ft: float
    min_segment_len_ft: float
    tiny_seg_threshold_ft: float

    # Local export settings
    # =====================
    # Directories
    proj_dir: str
    final_output_dir: str

    # Output settings
    output_file_name: str
    output_file_format: Annotated[
        Literal["geojson", "parquet"], BeforeValidator(to_lowercase)
    ]
    output_crs: str


# TODO: DELETE BELOW - FOR TESTING ONLY
if __name__ == "__main__":
    from pathlib import Path

    from curb_utils.io_tools import load_from_yaml

    local_path = Path(__file__).parent
    cfg = load_from_yaml(local_path / "config.yaml")
    config = CurbSegmenterConfig(**cfg)
    pass
