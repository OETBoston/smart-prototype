"""Lightweight client for reading an ArcGIS Online hosted feature service.

Handles named-user token generation (Boston Maps / BMAPS credentials),
layer/table discovery, paged feature queries, and attachment listing and
downloading. Talks to the REST API directly with ``requests`` to avoid the
heavy ``arcgis`` SDK dependency.
"""

from __future__ import annotations

from typing import Any

import requests
from curb_utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_PORTAL_URL = "https://www.arcgis.com"
DEFAULT_TIMEOUT = 60
DEFAULT_PAGE_SIZE = 1000
TOKEN_EXPIRATION_MINUTES = 120


class ArcGISError(RuntimeError):
    """Raised when the ArcGIS REST API returns an error payload."""


class ArcGISClient:
    """Minimal REST client for an ArcGIS hosted FeatureServer.

    Args:
        service_url: Base FeatureServer URL (without a trailing layer index).
        username/password: Named-user credentials used to mint a token.
        token: A pre-generated token. If supplied, username/password are unused.
        portal_url: Portal used for token generation (ArcGIS Online by default).
    """

    def __init__(
        self,
        service_url: str,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        portal_url: str = DEFAULT_PORTAL_URL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.service_url = service_url.rstrip("/")
        self.portal_url = (portal_url or DEFAULT_PORTAL_URL).rstrip("/")
        self.timeout = timeout
        self._username = username
        self._password = password
        self._token = token
        self._session = requests.Session()
        # Referer-based tokens must be used with a matching Referer header.
        self._session.headers.update({"Referer": self.portal_url})

    @property
    def token(self) -> str | None:
        """Return the active token, generating one on first use if needed."""
        if self._token is None and self._username and self._password:
            self._token = self._generate_token()
        return self._token

    def _generate_token(self) -> str:
        url = f"{self.portal_url}/sharing/rest/generateToken"
        data = {
            "username": self._username,
            "password": self._password,
            "referer": self.portal_url,
            "expiration": TOKEN_EXPIRATION_MINUTES,
            "f": "json",
        }
        logger.info("Generating ArcGIS token for '%s' via %s", self._username, url)
        resp = self._session.post(url, data=data, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ArcGISError(
                f"ArcGIS request failed with HTTP {resp.status_code}: {url}"
            ) from exc
        payload = resp.json()
        if "token" not in payload:
            raise ArcGISError(f"Failed to generate ArcGIS token: {payload}")
        return payload["token"]

    def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        data: dict | None = None,
    ) -> dict:
        params = dict(params or {})
        data = dict(data or {})
        params.setdefault("f", "json")
        tok = self.token
        if tok:
            if method.upper() == "POST":
                data["token"] = tok
            else:
                params["token"] = tok
        resp = self._session.request(
            method,
            url,
            params=params,
            data=data or None,
            timeout=self.timeout,
        )
        try:
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ArcGISError(
                f"ArcGIS request failed with HTTP {resp.status_code}: {url}"
            ) from exc
        payload = resp.json()
        if isinstance(payload, dict) and "error" in payload:
            raise ArcGISError(f"ArcGIS error from {url}: {payload['error']}")
        return payload

    def _get(self, url: str, params: dict | None = None) -> dict:
        return self._request("GET", url, params=params)

    def service_info(self) -> dict:
        """Return the FeatureServer service description JSON."""
        return self._get(self.service_url)

    def discover_layers(self) -> dict[str, dict]:
        """Map lowercase layer/table name -> metadata for all layers and tables."""
        info = self.service_info()
        out: dict[str, dict] = {}
        for kind in ("layers", "tables"):
            for lyr in info.get(kind) or []:
                out[str(lyr["name"]).lower()] = {
                    "id": lyr["id"],
                    "name": lyr["name"],
                    "kind": kind,
                    "type": lyr.get("type"),
                }
        return out

    def layer_info(self, layer_id: int) -> dict:
        """Return the description JSON for a single layer/table."""
        return self._get(f"{self.service_url}/{layer_id}")

    def query_layer(
        self,
        layer_id: int,
        where: str = "1=1",
        out_fields: str = "*",
        return_geometry: bool = True,
        out_sr: int = 4326,
    ) -> dict[str, Any]:
        """Query all features of a layer, paging through the transfer limit.

        Returns a dict with ``features`` plus the layer's ``objectIdFieldName``,
        ``globalIdFieldName``, ``fields``, and ``geometryType``.
        """
        url = f"{self.service_url}/{layer_id}/query"
        features: list[dict] = []
        meta: dict[str, Any] = {}
        offset = 0
        while True:
            params = {
                "where": where,
                "outFields": out_fields,
                "returnGeometry": str(return_geometry).lower(),
                "outSR": out_sr,
                "resultOffset": offset,
                "resultRecordCount": DEFAULT_PAGE_SIZE,
            }
            # Feature filters can contain hundreds of GlobalIDs. Keep the
            # query parameters in the request body so those filters are not
            # constrained by URL-length limits.
            payload = self._request("POST", url, data=params)
            if not meta:
                meta = {
                    "objectIdFieldName": payload.get("objectIdFieldName"),
                    "globalIdFieldName": payload.get("globalIdFieldName"),
                    "fields": payload.get("fields", []),
                    "geometryType": payload.get("geometryType"),
                }
            batch = payload.get("features", []) or []
            features.extend(batch)
            if payload.get("exceededTransferLimit") and batch:
                offset += len(batch)
            else:
                break
        meta["features"] = features
        return meta

    def query_count(self, layer_id: int, where: str = "1=1") -> int:
        """Return the number of features matching ``where`` (fetches no records)."""
        url = f"{self.service_url}/{layer_id}/query"
        payload = self._request(
            "POST", url, data={"where": where, "returnCountOnly": "true"}
        )
        return int(payload.get("count", 0))

    def get_attachments(self, layer_id: int, object_id: object) -> list[dict]:
        """Return attachment info dicts for a single feature (by OBJECTID)."""
        url = f"{self.service_url}/{layer_id}/{object_id}/attachments"
        payload = self._get(url)
        return payload.get("attachmentInfos", []) or []

    def download_attachment(
        self, layer_id: int, object_id: object, attachment_id: object
    ) -> bytes:
        """Download the raw bytes of a single attachment."""
        url = f"{self.service_url}/{layer_id}/{object_id}/attachments/{attachment_id}"
        params = {}
        tok = self.token
        if tok:
            params["token"] = tok
        resp = self._session.get(url, params=params, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ArcGISError(
                "ArcGIS attachment download failed for "
                f"layer={layer_id}, object={object_id}, attachment={attachment_id}, "
                f"HTTP {resp.status_code}"
            ) from exc
        return resp.content
