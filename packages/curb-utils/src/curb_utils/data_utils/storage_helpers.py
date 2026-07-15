# utilities/data_utils/storage_helpers.py
import hashlib
import os


def create_consistent_storage_suffix_from_path(path: str) -> str:
    """
    Returns "<sha256>.<ext>" for a file on disk.
    """
    ext = os.path.splitext(path)[1].lstrip(".")
    with open(path, "rb") as f:
        data = f.read()

    h = hashlib.sha256(data).hexdigest()
    return f"{h}.{ext}"


def create_consistent_storage_suffix_from_bytes(data: bytes, ext: str) -> str:
    """
    Returns "<sha256>.<ext>" for raw bytes.
    Extension must be provided explicitly.
    """
    ext = ext.lstrip(".")
    h = hashlib.sha256(data).hexdigest()
    return f"{h}.{ext}"


def create_consistent_storage_suffix(
    *, path: str = None, data: bytes = None, ext: str = None
) -> str:
    """
    Unified wrapper for create_consistent_storage_suffix

    Examples:
        create_consistent_storage_suffix(path="foo.png")
        create_consistent_storage_suffix(data=b"...", ext="png")
    """
    if path:
        if data or ext:
            raise ValueError("Provide either path OR (data + ext), not both.")
        return create_consistent_storage_suffix_from_path(path)

    if data:
        if not ext:
            raise ValueError("Must provide `ext` when using `data`.")
        return create_consistent_storage_suffix_from_bytes(data, ext)

    raise ValueError("Provide either path OR data.")


def create_google_storage_id_from_path(prefix: str, suffix, current_path: str) -> str:
    """
    Example:
        prefix = "users/avatar/"
        result = "users/avatar/<sha256>.<ext>"
    """
    suffix = create_consistent_storage_suffix_from_path(current_path)
    return f"{prefix.rstrip('/')}/{suffix}"
