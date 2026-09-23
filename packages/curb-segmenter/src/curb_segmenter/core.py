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

import geopandas as gpd
from curb_utils.logging import get_logger
from dotenv import load_dotenv

import curb_segmenter.curb_segmentation as cs
from curb_segmenter import io_utils
from curb_segmenter.config import CurbSegmenterConfig

warnings.filterwarnings("ignore")


def load_data(config: CurbSegmenterConfig) -> tuple:
    # Read curb lines
    curbs = io_utils.load_blockface_gdf_from_pg(
        dbname=config.db_name,
        schema=config.db_schema,
        table_name=config.bf_table_name,
        geom_col=config.bf_geom_col,
        target_crs=config.proj_crs,
        filter_string=f"job_id = '{config.source_jobs.blockface_creator}'",
    )

    # Read asset locations
    asset_dict = io_utils.load_asset_gdfs_from_pg(
        config=config.model_dump(),
        target_crs=config.proj_crs,
    )
    return curbs, asset_dict


def run_curb_segmentation_pipeline(
    config: CurbSegmenterConfig,
    curbs: gpd.GeoDataFrame,
    asset_dict: dict,
    test_mode: bool = False,
) -> None:
    segment_id_cols = []
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
        gdf=curb_segments_by_pm, output_crs=config.output_crs, test=test_mode
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
        test=test_mode,
    )


def curb_segmenter(config: CurbSegmenterConfig) -> None:
    # Session settings
    load_dotenv()
    logger = get_logger(__name__)
    logger.info("Running Curb Segmentation Pipeline...")

    # Autodetection of job ids must be resolved upstream
    for job_name, job_id in config.source_jobs:
        if job_id == "auto":
            raise RuntimeError(
                f"Failed to resolve auto-detection of job id for {job_name}"
            )

    # Load in data
    curbs, asset_dict = load_data(config)
    run_curb_segmentation_pipeline(config, curbs, asset_dict)
