"""
==============================================================================
Main Script for Curb Segmentation Pipeline
==============================================================================
This script serves as the primary entry point for executing the curb segmentation
workflow. It orchestrates the complete process, including data loading,
preprocessing, inference, and post-processing. Configuration parameters
are loaded from `config.yaml` to ensure consistency and reproducibility across
runs.

Usage:
    python main.py

Ensure that all dependencies are installed and configuration paths are correctly
set before running the script.
==============================================================================
"""

# Packages
import warnings

from curb_utils.io_tools import load_from_yaml
from curb_utils.logging import get_logger
from dotenv import load_dotenv

import curb_segmenter.curb_segmentation as cs
from curb_segmenter import io_utils
from curb_segmenter.config import CurbSegmenterConfig

warnings.filterwarnings("ignore")


def curb_segmenter(config: CurbSegmenterConfig) -> None:
    # Session settings
    load_dotenv()
    logger = get_logger(__name__)
    logger.info("Running Curb Segmentation Pipeline...")

    segment_id_cols = []

    # Read curb lines
    curbs = io_utils.load_blockface_gdf_from_pg(
        dbname=config.db_name,
        schema=config.db_schema,
        table_name=config.bf_table_name,
        geom_col=config.bf_geom_col,
        target_crs=config.proj_crs,
        filter_string=f"job_id = '{config.bf_job_id}'",
    )

    # Read asset locations
    asset_dict = io_utils.load_asset_gdfs_from_pg(
        dbname=config.db_name,
        schema=config.db_schema,
        asset_dict=config.assets.model_dump(),
        target_crs=config.proj_crs,
    )

    # Clean curb lines
    clean_curbs_gdf = cs.clean_curb_geometries(
        curb_lines=curbs,
        min_curb_len_ft=config.min_curb_len_ft,
        eps_fraction=float(config.eps_fraction),
    )

    # Run segmentation by bus stops
    curb_segments_by_bs = cs.run_segmentation_by_bus_stops(
        configuration=config.model_dump(),
        asset_dict=asset_dict,
        clean_curbs=clean_curbs_gdf,
        segment_id_cols=segment_id_cols,
    )

    # Run segmentation by fire hydrants
    curb_segments_by_fh = cs.run_segmentation_by_fire_hydrants(
        configuration=config.model_dump(),
        asset_dict=asset_dict,
        clean_curbs=curb_segments_by_bs,
        segment_id_cols=segment_id_cols,
    )

    # Run segmentation by parking signs
    curb_segments_by_ps = cs.run_segmentation_by_parking_signs(
        configuration=config.model_dump(),
        asset_dict=asset_dict,
        clean_curbs=curb_segments_by_fh,
        segment_id_cols=segment_id_cols,
    )
    # Run segmentation by parking meters
    curb_segments_by_pm = cs.run_segmentation_by_parking_meters(
        configuration=config.model_dump(),
        asset_dict=asset_dict,
        clean_curbs=curb_segments_by_ps,
        segment_id_cols=segment_id_cols,
    )

    # Format and create a GeoDataFrame consistent with the `curb_segments` table schema
    curb_segments, job_id, ts = cs.create_curb_segments_table(
        curb_segments_by_pm, output_crs=config.output_crs
    )

    # Merge tiny segments
    curb_segments = cs.merge_tiny_curb_segments(
        gdf=curb_segments,
        length_threshold=config.tiny_seg_threshold_ft,
        asset_dict=asset_dict,
    )

    # Write curb segments to database
    io_utils.write_curb_segments_to_db(
        gdf=curb_segments,
        dbname=config.db_name,
        schema=config.db_schema,
        job_id=job_id,
        job_name=config.job_name,
        job_description=config.job_description,
        ts=ts,
        debug_mode=config.debug_mode,
    )

    # Write curb segments to a local file (for QA)
    io_utils.write_curb_segments_to_file(
        output_gdf=curb_segments,
        job_id=job_id,
        timestamp=ts,
        output_path=config.final_output_dir,
        output_file_name=config.output_file_name,
        file_type=config.output_file_format,
        output_crs=config.output_crs,
    )


if __name__ == "__main__":
    # TODO: Remove this
    config_yaml = load_from_yaml(
        "packages/curb-segmenter/src/curb_segmenter/config.yaml"
    )
    config = CurbSegmenterConfig(**config_yaml)
    curb_segmenter(config)
