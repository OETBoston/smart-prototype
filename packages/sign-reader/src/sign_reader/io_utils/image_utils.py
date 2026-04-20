"""Utility functions for fetching images from various sources:
including URL, local file, BigQuery, or Google Cloud Storage.
"""

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from google.cloud import storage
from utilities.data_utilities.storage_helpers import (
    create_consistent_storage_suffix,
)
from utilities.data_utilities.storage_utilities import Storage


def get_image_from_url(image_url: str) -> bytes:
    """Download image bytes from a URL.

    Args:
        image_url (str): The image URL.

    Returns:
        bytes: Image data in bytes format.
    """
    response = requests.get(image_url)
    response.raise_for_status()
    return response.content


def get_image_from_file(file_path: str) -> bytes:
    """Read image bytes from a local file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    return path.read_bytes()


def get_image_from_bq(query: str) -> bytes:
    """Fetch image bytes from a BigQuery table.

    Args:
        query (str): SQL query for fetching the image data.

    Raises:
        NotImplementedError: This function is not yet implemented.
    """
    raise NotImplementedError("Fetching images from BigQuery is not yet implemented.")


def get_image_from_gs(bucket_path: str) -> bytes:
    """Fetch image bytes from Google Cloud Storage.

    Args:
        bucket_path (str): GCS path to the image.

    Returns:
        bytes: The raw image data.
    """
    # 1. Parse the URI
    parsed = urlparse(bucket_path)
    if parsed.scheme != "gs":
        raise ValueError(f"Invalid scheme. Expected 'gs', got '{parsed.scheme}'")

    bucket_name = parsed.netloc
    blob_name = parsed.path.lstrip("/")

    # 2. Initialize the client
    client = storage.Client()

    # 3. Get the bucket and the blob (file)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    # 4. Download as bytes
    image_bytes = blob.download_as_bytes()

    return image_bytes


def get_image(source: str, **kwargs: Any) -> bytes:
    """Auto-detect source type and fetch image bytes."""
    if source.startswith("http"):
        return get_image_from_url(source)
    elif source.startswith("gs://"):
        return get_image_from_gs(source)
    elif Path(source).exists():
        return get_image_from_file(source)
    else:
        raise ValueError(f"Unrecognized image source: {source}")


def upload_image(
    image_url: str, image_bytes: bytes, prefix: str, storage: Storage
) -> str:
    image_path = Path(image_url)
    ext = image_path.suffix
    suffix = create_consistent_storage_suffix(data=image_bytes, ext=ext)
    path = f"{prefix.rstrip('/')}/{suffix}"
    print(f"uploading image to {path}")
    storage.write_bytes(path, image_bytes)
    return path
