import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime

import pytest
from data_utils.storage_helpers import create_consistent_storage_suffix
from data_utils.storage_utilities import Storage

pytestmark = pytest.mark.integration


@pytest.fixture
def storage():
    """
    Storage fixture that supports:
    - Service account credentials via TEST_GCS_TOKEN_PATH
    - Or falls back to Google ADC (user credentials)
    """
    token_path = os.getenv("TEST_GCS_TOKEN_PATH")

    if token_path:
        return Storage(storage_options={"token": token_path})

    # Fall back to ADC (user account creds)
    return Storage(storage_options={})


@pytest.fixture
def test_prefix():
    """
    Remote prefix for test uploads, e.g. "gs://mybucket/integration-tests/"
    Must include bucket.
    """
    prefix = os.getenv("TEST_GCS_PREFIX")
    if not prefix:
        raise RuntimeError("Missing TEST_GCS_PREFIX env var")

    return prefix.rstrip("/") + "/"


def generate_random_json():
    """
    Generates a unique JSON object each test.
    """
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "value": uuid.uuid4().hex[:12],
    }


def write_temp_json(obj):
    """
    Writes JSON to a temporary file and returns its path.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.write(json.dumps(obj).encode("utf-8"))
    tmp.close()
    return tmp.name


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ---------------------------------------------------------------------------
#                             INTEGRATION TESTS
# ---------------------------------------------------------------------------


def test_upload_random_json(storage, test_prefix):
    """
    Uploads a random JSON file and verifies:
    - hash-based suffix is correct
    - remote object exists
    - can download and verify exact content
    """
    obj = generate_random_json()
    local_path = write_temp_json(obj)

    suffix = create_consistent_storage_suffix(path=local_path)
    remote_uri = f"{test_prefix}{suffix}"

    # Upload
    storage.upload(local_path, remote_uri)

    # Verify remote exists
    assert storage.exists(remote_uri), f"File not found in storage: {remote_uri}"

    # Verify round-trip integrity
    downloaded = json.loads(storage.read_bytes(remote_uri))
    assert downloaded == obj, "Uploaded JSON does not match downloaded JSON"


def test_collision_handling(storage, test_prefix):
    """
    Uploads the *same* JSON twice and ensures:
    - both uploads generate the same hash-based name
    - exists() remains true
    - content is identical
    """
    # Create JSON and write twice to two different temp files
    obj = {"collision": "test", "x": 1234}

    p1 = write_temp_json(obj)
    p2 = write_temp_json(obj)

    # Ensure hashing is deterministic
    assert sha256_file(p1) == sha256_file(p2)

    suffix = create_consistent_storage_suffix(path=p1)
    remote_uri = f"{test_prefix}{suffix}"

    # Upload twice
    storage.upload(p1, remote_uri)
    storage.upload(p2, remote_uri)

    # Verify only one remote object exists (idempotent behavior)
    assert storage.exists(remote_uri)

    # Verify correct content
    downloaded = json.loads(storage.read_bytes(remote_uri))
    assert downloaded == obj


def test_different_content_different_hash(storage, test_prefix):
    """
    Ensures different JSON produces different hash suffix.
    """
    p1 = write_temp_json({"v": 1})
    p2 = write_temp_json({"v": 2})

    s1 = create_consistent_storage_suffix(path=p1)
    s2 = create_consistent_storage_suffix(path=p2)

    assert s1 != s2, "Different JSON values should produce different storage suffixes"
