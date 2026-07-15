"""Command-line argument parsing for Sign Reader."""

import argparse
import uuid


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the Policy Applier script.

    This function defines the input source for filtering database records
    based on a specific Curb Segment Job UUID.

    Returns:
        argparse.Namespace: Parsed arguments containing:
            - job_id (str): Optional Curb Segment Job UUID to filter database records.
    """
    parser = argparse.ArgumentParser(description="Policy Applier")

    input_group = parser.add_argument_group("Input Sources")

    input_group.add_argument(
        "--job-id",
        type=str,
        help="Specific Curb Segment Job UUID to filter database records",
    )

    input_group.add_argument(
        "--schema",
        type=str,
        default="staging",
        help="Database schema for input and output tables. Defaults to 'staging'.",
    )

    args = parser.parse_args()

    if args.job_id:
        try:
            uuid.UUID(args.job_id)
        except ValueError:
            parser.error(f"Invalid UUID format for --job-id: '{args.job_id}'")

    return args
