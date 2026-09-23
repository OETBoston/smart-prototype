"""Network failures must not expose token-bearing request URLs in logs."""

import sys
import traceback
from pathlib import Path

import pytest
import requests

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "packages/sign-loader/src/sign_loader")
)
from arcgis_client import ArcGISClient, ArcGISError  # noqa: E402


@pytest.mark.parametrize("attachment", [False, True])
def test_request_error_redacts_token(monkeypatch, attachment) -> None:
    client = ArcGISClient("https://example.test/FeatureServer", token="private-token")

    def fail(*args: object, **kwargs: object) -> None:
        raise requests.ConnectionError("https://example.test?token=private-token")

    monkeypatch.setattr(client._session, "request", fail)
    monkeypatch.setattr(client._session, "get", fail)
    with pytest.raises(ArcGISError) as error:
        if attachment:
            client.download_attachment(0, 1, 2)
        else:
            client.layer_info(0)
    assert "private-token" not in "".join(traceback.format_exception(error.value))
