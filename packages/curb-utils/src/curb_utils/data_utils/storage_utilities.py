# utilities/data_utils/storage_utilities.py

from typing import IO, Any, Dict, Optional

import fsspec


class Storage:
    """
    Minimal, provider-agnostic wrapper for object storage using fsspec.

    - Supports any provider (GCS, S3, Azure, local, etc.)
    - Accepts explicit credentials through `storage_options`
    - Falls back to ADC for GCP if no credentials provided
    """

    def __init__(self, storage_options: Optional[Dict[str, Any]] = None):
        """
        Parameters
        ----------
        storage_options : dict, optional
            Credentials or configuration to pass through to fsspec.
            Examples:
                {"token": "/path/key.json"}           (GCS)
                {"token": sa_dict}                    (GCS)
                {"key": "...", "secret": "..."}       (S3)
                {"connection_string": "..."}          (Azure)
        """
        self.storage_options = storage_options or {}

    def open(self, uri: str, mode: str = "rb", **kwargs) -> IO:
        """
        Opens a storage URI for reading or writing.

        Example:
            storage.open("gs://bucket/file.png")
            storage.open("s3://bucket/file.png", "wb")
        """
        return fsspec.open(
            uri,
            mode,
            storage_options=self.storage_options,
            **kwargs,
        )

    def exists(self, uri: str) -> bool:
        """
        Returns True if the object exists.
        """
        fs, path = fsspec.core.url_to_fs(
            uri, **{"storage_options": self.storage_options}
        )
        return fs.exists(path)

    def upload(self, local_path: str, remote_uri: str) -> None:
        """
        Simple upload utility (local filesystem → storage URL).
        """
        with open(local_path, "rb") as src:
            with self.open(remote_uri, "wb") as dst:
                dst.write(src.read())

    def download(self, remote_uri: str, local_path: str) -> None:
        """
        Simple download utility (storage URL → local filesystem).
        """
        with self.open(remote_uri, "rb") as src:
            with open(local_path, "wb") as dst:
                dst.write(src.read())

    def read_bytes(self, uri: str) -> bytes:
        """
        Convenience: read object as raw bytes.
        """
        with self.open(uri, "rb") as f:
            return f.read()

    def write_bytes(self, uri: str, data: bytes) -> None:
        """
        Convenience: write raw bytes.
        """
        with self.open(uri, "wb") as f:
            f.write(data)
