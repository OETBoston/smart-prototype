"""Storage utilities for reading and saving Sign Reader data."""

from pathlib import Path

# import streamlit as st

# @st.cache_data
# def read_image_urls(source: str) -> list[str]:
#    """Read a list of image URLs from a text file or a GCP table.
#
#    Each line in the file or each row in the table should contain one URL.
#    Empty lines or rows are ignored.
#
#    Args:
#        source (str): Path to the text file or GCP table ID containing image URLs.
#
#    Returns:
#        list[str]: List of image URLs.
#
#    Raises:
#        FileNotFoundError: If the file does not exist (when source is a file path).
#        ValueError: If no valid URLs are found.
#    """
#
#    path = Path(source)
#    if not path.exists():
#        raise FileNotFoundError(f"URL file not found: {source}")
#
#    with path.open("r", encoding="utf-8") as f:
#        urls = [line.strip() for line in f if line.strip()]
#
#    if not urls:
#        raise ValueError(f"No URLs found in source: {source}")
#
#    return urls


def save_parsed_output(
    parsed_image, output_dir: Path, image_uri: str, sign_id: str | None
) -> None:
    """Save structured parsed output to a JSON file."""
    print(f"Debug output for {image_uri}")

    # Assign a filename, icnluding the sign_id if present
    stem = Path(image_uri).stem
    if sign_id:
        image_name = f"{str(sign_id)[:8]}_{stem}"
    else:
        image_name = stem

    file_path = output_dir / f"{image_name}.json"

    # Use a counter to increment output
    counter = 1
    while file_path.exists():
        file_path = output_dir / f"{image_name}_v{counter}.json"
        counter += 1

    with file_path.open("w", encoding="utf-8") as f:
        f.write(parsed_image.model_dump_json(indent=2))


# def get_storage(token_path) -> Storage:
#     """returns a gcp storage obj"""
#     storage = Storage(storage_options={"token": token_path})
#     return storage
