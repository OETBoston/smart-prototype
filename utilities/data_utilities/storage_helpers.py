# utilities/data_utilities/storage_helpers.py
import hashlib
import os

def create_consistent_storage_suffix(current_path: str) -> str:
    """
    Returns: "<sha256>.<ext>"
    """
    ext = os.path.splitext(current_path)[1].lstrip(".")
    h = hashlib.sha256(open(current_path, "rb").read()).hexdigest()
    return f"{h}.{ext}"


def create_google_storage_id(prefix: str, current_path: str) -> str:
    """
    Example:
        prefix = "users/avatar/"
        result = "users/avatar/<sha256>.<ext>"
    """
    suffix = create_consistent_storage_suffix(current_path)
    return f"{prefix.rstrip('/')}/{suffix}"
