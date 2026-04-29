"""
==============================================================================
Main Script for Curb Segmentation Pipeline for Making Test Data
==============================================================================
This script serves as the primary entry point for executing the curb segmentation
workflow for test data. This is used in making curb segment test data for
testing curb-segmentation and smart-curb-policy-handling
workflows. Static data files are read in and processed to generate curb
segments. If no parameters are provided on the command line, the script will
run for all tests in the test data directory. Some configuration parameters
are loaded from `config.yaml`.

Ensure that all dependencies are installed and configuration paths are correctly
set before running the script.
==============================================================================
"""
# Packages
import argparse
from pathlib import Path
import warnings

import curb_segmenter.curb_segmentation as cs
from curb_segmenter import io_utils
from curb_utils.io_tools import load_config
warnings.filterwarnings("ignore")

BASE_TEST_DIR = "tests/combined/test_data/"

def main(test_lst=None):
    """Main function for the Curb Segmentation Pipeline."""
    # Session settings
    logger = cs.get_logger()
    logger.info("Running Curb Segmentation Pipeline...")

    # Read config
    config = load_config("packages/curb-segmenter/src/curb_segmenter/config.yaml")
    config["debug_mode"] = True  # Override debug mode to True for test data generation
    for test in Path(BASE_TEST_DIR).iterdir():
        if not test.is_dir():
            continue
        if test_lst and str(test.name) not in test_lst:
            continue
        run_one_test(test, config, logger)


def run_one_test(test, config, logger):
    full_input_dir = str(test)
    logger.info("Processing test data in: %s", full_input_dir)
    segment_id_cols = []
    # Read curb lines
    curbs = io_utils.load_blockface_gdf_from_local(
        input_dir=full_input_dir,
        table_name=config["bf_table_name"],
        geom_col=config["bf_geom_col"],
        source_crs=config["proj_crs"],
        target_crs=config["proj_crs"],
    )

    # Read asset locations
    asset_dict = io_utils.load_asset_gdfs_from_local(
        asset_dict=config["assets"],
        target_crs=config["proj_crs"],
        input_dir=full_input_dir
    )

    # Clean curb lines
    clean_curbs_gdf = cs.clean_curb_geometries(
        curb_lines=curbs,
        min_curb_len_ft=config["min_curb_len_ft"],
        eps_fraction=float(config["eps_fraction"]),
        logger_obj=logger,
        verbose=True,
    )

    # Run segmentation by bus stops
    curb_segments_by_bs = cs.run_segmentation_by_bus_stops(
        configuration=config,
        asset_dict=asset_dict,
        clean_curbs=clean_curbs_gdf,
        segment_id_cols=segment_id_cols,
        logger_obj=logger,
        verbose=True
    )

    # Run segmentation by fire hydrants
    curb_segments_by_fh = cs.run_segmentation_by_fire_hydrants(
        configuration=config,
        asset_dict=asset_dict,
        clean_curbs=curb_segments_by_bs,
        segment_id_cols=segment_id_cols,
        logger_obj=logger,
        verbose=True
    )

    # Run segmentation by parking signs
    curb_segments_by_ps = cs.run_segmentation_by_parking_signs(
        configuration=config,
        asset_dict=asset_dict,
        clean_curbs=curb_segments_by_fh,
        segment_id_cols=segment_id_cols,
        logger_obj=logger,
        verbose=True
    )

    # Run segmentation by parking meters
    curb_segments_by_pm = cs.run_segmentation_by_parking_meters(
        configuration=config,
        asset_dict=asset_dict,
        clean_curbs=curb_segments_by_ps,
        segment_id_cols=segment_id_cols,
        logger_obj=logger,
        verbose=True,
    )

    # Format and create a GeoDataFrame consistent with the
    # `curb_segments` table schema
    curb_segments, job_id, ts = cs.create_curb_segments_table(
        curb_segments_by_pm,
        output_crs=config["output_crs"],
        test=True
    )

    # Merge tiny segments
    merged_curb_segments = cs.merge_tiny_curb_segments(
        gdf=curb_segments,
        length_threshold=config["tiny_seg_threshold_ft"],
        asset_dict=asset_dict,
        logger_obj=logger,
    )

    # Write curb segments to a local file (to run tests)
    io_utils.write_curb_segments_to_file(
        output_gdf=merged_curb_segments,
        job_id=job_id,
        timestamp=ts,
        output_path=f"tests/combined/test_data/{test.name}",
        output_file_name=config["output_file_name"],
        file_type=config["output_file_format"],
        output_crs=config["proj_crs"],
        test=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Curb Segmentation Pipeline for Test Data."
    )
    parser.add_argument(
        "--tests",
        default=None,
        required=False,
        help="tests: comma-separated list of tests for which curb segments" \
            "should be generated. If not provided, the pipeline will run" + \
                "for all tests in the test data directory."
    )
    args = parser.parse_args()

    if args.tests:
        # Parse tests as comma-separated values
        tests = [t.strip() for t in args.tests.split(',')]
        print(f"Running pipeline for specified tests: {tests}")
        main(tests)
    else:
        print("No tests specified. Running pipeline for all tests in the test data directory.")
        main()
