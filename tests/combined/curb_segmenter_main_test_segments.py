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
from curb_segmenter.main import main as main_module
from curb_utils.io_tools import load_from_yaml
warnings.filterwarnings("ignore")

BASE_TEST_DIR = "tests/combined/test_data/"

def main(test_lst=None):
    """Main function for the Curb Segmentation Pipeline."""
    # Session settings
    logger = cs.get_logger()
    logger.info("Running Curb Segmentation Pipeline...")

    # Read config
    config = load_from_yaml(Path(__file__).resolve().parent / "config.yaml")
    for test in Path(BASE_TEST_DIR).iterdir():
        if not test.is_dir():
            continue
        if test_lst and str(test.name) not in test_lst:
            continue
        run_one_test(test, config, logger)


def run_one_test(test, config, logger):
    logger.info("Processing test data in: %s", test)
    config['input_dir'] = f"{test}/"
    config['final_output_dir'] = f"{test}/"
    main_module(config)


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
