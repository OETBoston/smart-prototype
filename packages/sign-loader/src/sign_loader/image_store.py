"""Pluggable image storage for the survey importer.

Stores downloaded attachment bytes either to a local directory or to a cloud
bucket (via the shared ``curb_utils`` fsspec ``Storage`` wrapper) and returns a
URI suitable for the ``images.uri`` column (a local path or a ``gs://`` URI).
Images are content-addressed by sha256, so re-runs are idempotent and identical
photos are de-duplicated.
"""

from __future__ import annotations

import os
from pathlib import Path

from curb_utils.data_utils.storage_helpers import create_consistent_storage_suffix
from curb_utils.data_utils.storage_utilities import Storage
from curb_utils.logging import get_logger

logger = get_logger(__name__)


class ImageStore:
    """Abstract image store."""

    def store(self, data: bytes, ext: str) -> str:
        raise NotImplementedError


class LocalImageStore(ImageStore):
    """Writes images to a local directory; returns the absolute file path."""

    def __init__(self, base_dir: str | os.PathLike) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Storing survey images locally under %s", self.base_dir)

    def store(self, data: bytes, ext: str) -> str:
        suffix = create_consistent_storage_suffix(data=data, ext=ext)
        path = self.base_dir / suffix
        if not path.exists():
            path.write_bytes(data)
        return str(path.resolve())


class CloudImageStore(ImageStore):
    """Writes images to an fsspec-supported bucket; returns the full URI."""

    def __init__(self, prefix: str, token_path: str | None = None) -> None:
        if not prefix:
            raise ValueError(
                "Cloud image store requires a prefix (e.g. gs://bucket/path). "
                "Set image_storage.prefix or GCS_PREFIX."
            )
        self.prefix = prefix.rstrip("/")
        storage_options = {"token": token_path} if token_path else {}
        self.storage = Storage(storage_options=storage_options)
        logger.info("Storing survey images in cloud storage under %s", self.prefix)

    def store(self, data: bytes, ext: str) -> str:
        suffix = create_consistent_storage_suffix(data=data, ext=ext)
        uri = f"{self.prefix}/{suffix}"
        if not self.storage.exists(uri):
            self.storage.write_bytes(uri, data)
        return uri


def build_image_store(survey_cfg: dict, repo_root: Path) -> ImageStore:
    """Construct an ImageStore from the survey123 ``image_storage`` config.

    Local relative paths are resolved against the repository root.
    """
    storage_cfg = survey_cfg.get("image_storage", {}) or {}
    backend = (storage_cfg.get("backend") or "local").lower()

    if backend == "local":
        local_dir = Path(storage_cfg.get("local_dir", "inputs/survey_images"))
        if not local_dir.is_absolute():
            local_dir = repo_root / local_dir
        return LocalImageStore(local_dir)

    if backend in ("gcs", "gs", "cloud"):
        prefix = storage_cfg.get("prefix") or os.getenv("GCS_PREFIX")
        token_path = os.getenv("GCS_TOKEN_PATH")
        return CloudImageStore(prefix=prefix, token_path=token_path)

    raise ValueError(f"Unsupported image_storage backend: {backend!r}")
