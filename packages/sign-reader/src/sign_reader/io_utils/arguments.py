"""Command-line argument parsing for Sign Reader."""

import argparse
import uuid


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the Sign Reader script.

    This function defines the input sources for the Gemini API analysis,
    allowing the user to provide image URIs via a local text file or
    by fetching them directly from a Google Cloud Postgres database.

    Returns:
        argparse.Namespace: Parsed arguments containing:
            - file (str): Optional path to a text file of URIs.
            - db (bool): Flag to trigger a database fetch
            - temperature (float): Controls the randomness of the model output.
    """
    parser = argparse.ArgumentParser(description="Sign Reader using Gemini API")

    input_group = parser.add_argument_group("Input Sources")

    input_group.add_argument(
        "--file", type=str, help="Path to a local text file containing image URIs/URLs"
    )

    input_group.add_argument(
        "--db",
        action="store_true",
        help="Flag to fetch URIs from the Google Cloud Postgres table",
    )

    input_group.add_argument(
        "--job-id",
        type=str,
        help="Specific Job UUID to filter database records (requires --db)",
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help=(
            "Model temperature (default: 0.0, range is between 0.0 and 2.0). "
            "Higher values increase creativity. "
        ),
    )

    args = parser.parse_args()

    # Basic Validation: Ensure at least one source is provided
    if not args.file and not args.db:
        parser.error("No input source provided. Please use --file [PATH] or --db.")

    if args.job_id and not args.db:
        parser.error("The --job-id argument can only be used when --db flag is set.")

    if args.job_id:
        try:
            uuid.UUID(args.job_id)
        except ValueError:
            parser.error(f"Invalid UUID format for --job-id: '{args.job_id}'")

    return args
