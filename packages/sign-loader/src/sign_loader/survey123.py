"""Importer for Survey123 / ArcGIS Online hosted feature services.

Pulls survey location points (parent layer) and sign records (repeat table),
joins them so each sign inherits its survey point geometry, downloads photo
attachments, stores the images, and returns a sign-grain ``GeoDataFrame`` ready
for :func:`format_tables.format_sign_tbls`.

A shapefile-only fallback (no images) is provided for offline / quick loads of
the Survey123 ``.shp`` + ``.dbf`` export.
"""

from __future__ import annotations

import csv
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import geopandas as gpd
import pandas as pd
from arcgis_client import ArcGISClient
from curb_utils.logging import get_logger
from image_store import build_image_store
from shapely.geometry import Point

logger = get_logger(__name__)

GUID_FIELD_TYPES = ("esriFieldTypeGUID", "esriFieldTypeGlobalID")
DEFAULT_PROBE_SAMPLE = 25
ATTACHMENT_MAX_ATTEMPTS = 3


def _normalize_guid(val: object) -> str | None:
    """Return a canonical lowercase UUID, or ``None`` for an invalid value."""
    if val is None:
        return None
    text = str(val).strip()
    if not text:
        return None
    try:
        return str(uuid.UUID(text.strip("{}")))
    except (ValueError, AttributeError, TypeError):
        return None


def _load_parent_allowlist(survey_cfg: dict, repo_root: Path) -> set[str] | None:
    """Load and normalize a configured parent GlobalID allowlist CSV."""
    allowlist_cfg = survey_cfg.get("parent_allowlist")
    if not allowlist_cfg:
        return None

    csv_path = allowlist_cfg.get("csv_path")
    csv_column = allowlist_cfg.get("csv_column")
    if not csv_path or not csv_column:
        raise ValueError("survey123.parent_allowlist requires csv_path and csv_column.")

    path = Path(csv_path)
    if not path.is_absolute():
        path = repo_root / path
    if not path.is_file():
        raise ValueError(f"Parent allowlist CSV does not exist: {path}")

    values: list[str] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = {str(name).lower(): name for name in (reader.fieldnames or [])}
        actual_column = columns.get(str(csv_column).lower())
        if actual_column is None:
            raise ValueError(
                f"Parent allowlist column {csv_column!r} not found in {path}; "
                f"available columns: {reader.fieldnames or []}"
            )
        for row_number, row in enumerate(reader, start=2):
            raw_value = row.get(actual_column)
            normalized = _normalize_guid(raw_value)
            if normalized is None:
                raise ValueError(
                    f"Invalid or empty UUID in parent allowlist {path} "
                    f"at row {row_number}: {raw_value!r}"
                )
            values.append(normalized)

    allowlist = set(values)
    duplicate_count = len(values) - len(allowlist)
    if duplicate_count:
        logger.warning(
            "Parent allowlist %s contains %d duplicate UUID row(s); de-duplicating.",
            path,
            duplicate_count,
        )
    if not allowlist:
        raise ValueError(f"Parent allowlist CSV contains no UUIDs: {path}")
    logger.info("Loaded %d unique parent UUIDs from allowlist %s", len(allowlist), path)
    return allowlist


def _quote_sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _in_clause(field: str, values: set[str]) -> str:
    ordered = ", ".join(_quote_sql_string(value) for value in sorted(values))
    return f"{field} IN ({ordered})"


def _combine_where(*clauses: str | None) -> str:
    usable = [str(clause).strip() for clause in clauses if str(clause or "").strip()]
    if not usable:
        return "1=1"
    return " AND ".join(f"({clause})" for clause in usable)


def _to_datetime(val: object) -> pd.Timestamp:
    """Convert an ArcGIS date (epoch ms or string) to a pandas Timestamp."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return pd.NaT
    if isinstance(val, (int, float)):
        return pd.to_datetime(val, unit="ms")
    return pd.to_datetime(val, errors="coerce")


def _ci_get(attrs: dict, name: str | None, default: object = None) -> object:
    """Case-insensitive lookup into an attributes dict."""
    if not name:
        return default
    if name in attrs:
        return attrs[name]
    lower = {k.lower(): k for k in attrs}
    key = lower.get(name.lower())
    return attrs.get(key, default) if key is not None else default


def _ext_from_attachment(att: dict) -> str:
    """Best-effort file extension from an attachment's name or content type."""
    ext = Path(att.get("name") or "").suffix.lstrip(".")
    if ext:
        return ext.lower()
    ctype = (att.get("contentType") or "").lower()
    if "png" in ctype:
        return "png"
    return "jpg"


def _build_client(survey_cfg: dict) -> ArcGISClient:
    token = os.getenv("ARCGIS_TOKEN")
    username = os.getenv("BMAPS_USERNAME")
    password = os.getenv("BMAPS_PASSWORD")
    if not token and not (username and password):
        raise ValueError(
            "Missing ArcGIS credentials: set BMAPS_USERNAME and BMAPS_PASSWORD "
            "(or ARCGIS_TOKEN) in your .env file."
        )
    return ArcGISClient(
        service_url=survey_cfg["service_url"],
        username=username,
        password=password,
        token=token,
        portal_url=survey_cfg.get("portal_url", "https://www.arcgis.com"),
    )


def _resolve_layer_ids(client: ArcGISClient, survey_cfg: dict) -> tuple[int, int]:
    """Determine the parent (points) and repeat (signs) layer ids."""
    parent_id = survey_cfg.get("parent_layer_id")
    repeat_id = survey_cfg.get("repeat_layer_id")
    if parent_id is not None and repeat_id is not None:
        return int(parent_id), int(repeat_id)

    layers = client.discover_layers()
    logger.info(
        "Discovered service layers/tables: %s",
        {name: meta["id"] for name, meta in layers.items()},
    )
    parent_name = (survey_cfg.get("parent_layer_name") or "").lower()
    repeat_name = (survey_cfg.get("repeat_layer_name") or "").lower()

    if parent_id is None:
        if parent_name and parent_name in layers:
            parent_id = layers[parent_name]["id"]
        else:
            geom_layers = [m for m in layers.values() if m["kind"] == "layers"]
            if not geom_layers:
                raise ValueError(
                    "Could not auto-discover the parent layer; set parent_layer_id."
                )
            parent_id = geom_layers[0]["id"]

    if repeat_id is None:
        if repeat_name and repeat_name in layers:
            repeat_id = layers[repeat_name]["id"]
        else:
            tables = [m for m in layers.values() if m["kind"] == "tables"]
            if not tables:
                raise ValueError(
                    "Could not auto-discover the repeat table; set repeat_layer_id."
                )
            repeat_id = tables[0]["id"]

    logger.info("Using parent_layer_id=%s, repeat_layer_id=%s", parent_id, repeat_id)
    return int(parent_id), int(repeat_id)


def _find_global_id_field(meta: dict) -> str | None:
    if meta.get("globalIdFieldName"):
        return meta["globalIdFieldName"]
    for field in meta.get("fields", []):
        if field.get("type") == "esriFieldTypeGlobalID":
            return field["name"]
    return None


def _find_parent_field(meta: dict, override: str | None = None) -> str | None:
    """Find the repeat table's reference to the parent GlobalID."""
    if override:
        return override
    guid_fields = [
        f["name"] for f in meta.get("fields", []) if f.get("type") in GUID_FIELD_TYPES
    ]
    for name in guid_fields:
        if name.lower().startswith("parent"):
            return name
    known = {"parentglobalid", "parentrowid", "parentglobal", "parentglobalid_1"}
    for field in meta.get("fields", []):
        if field["name"].lower() in known:
            return field["name"]
    return None


def _probe_has_attachments(
    client: ArcGISClient, layer_id: int, object_ids: list
) -> bool:
    for oid in object_ids:
        try:
            if client.get_attachments(layer_id, oid):
                return True
        except Exception as exc:  # noqa: BLE001 - probing only
            logger.debug("Attachment probe failed for %s/%s: %s", layer_id, oid, exc)
    return False


def _resolve_link_level(
    client: ArcGISClient,
    survey_cfg: dict,
    parent_id: int,
    repeat_id: int,
    signs_df: pd.DataFrame,
) -> str:
    """Decide whether attachments live on the repeat or parent layer."""
    configured = (survey_cfg.get("attachments") or {}).get("link_level") or "auto"
    configured = str(configured).lower()
    if configured in ("parent", "repeat"):
        return configured

    repeat_oids = (
        signs_df["_repeat_oid"].dropna().unique().tolist()[:DEFAULT_PROBE_SAMPLE]
    )
    if _probe_has_attachments(client, repeat_id, repeat_oids):
        return "repeat"
    parent_oids = (
        signs_df["_parent_oid"].dropna().unique().tolist()[:DEFAULT_PROBE_SAMPLE]
    )
    if _probe_has_attachments(client, parent_id, parent_oids):
        return "parent"
    logger.warning(
        "No attachments found on a sample of either layer; defaulting to 'parent'."
    )
    return "parent"


def _attach_images(
    client: ArcGISClient,
    signs_df: pd.DataFrame,
    link_level: str,
    parent_id: int,
    repeat_id: int,
    image_store,
    survey_cfg: dict,
) -> None:
    """Download attachments and populate an ``attachments`` list column in place."""
    max_workers = int((survey_cfg.get("attachments") or {}).get("max_workers", 8) or 8)
    if link_level == "repeat":
        layer_id, oid_col = repeat_id, "_repeat_oid"
    else:
        layer_id, oid_col = parent_id, "_parent_oid"

    unique_oids = signs_df[oid_col].dropna().unique().tolist()
    logger.info(
        "Fetching attachments for %d %s objects (max_workers=%d)",
        len(unique_oids),
        link_level,
        max_workers,
    )

    def fetch_for_oid(oid: object) -> tuple[object, list[dict]]:
        results: list[dict] = []
        infos: list[dict] | None = None
        for attempt in range(1, ATTACHMENT_MAX_ATTEMPTS + 1):
            try:
                infos = client.get_attachments(layer_id, oid)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Attachment listing attempt %d/%d failed for %s/%s (%s).",
                    attempt,
                    ATTACHMENT_MAX_ATTEMPTS,
                    layer_id,
                    oid,
                    type(exc).__name__,
                )
                if attempt < ATTACHMENT_MAX_ATTEMPTS:
                    time.sleep(2 ** (attempt - 1))
        if infos is None:
            return oid, results
        for att in infos:
            for attempt in range(1, ATTACHMENT_MAX_ATTEMPTS + 1):
                try:
                    data = client.download_attachment(layer_id, oid, att["id"])
                    uri = image_store.store(data, _ext_from_attachment(att))
                    results.append(
                        {
                            "uri": uri,
                            "source_image_id": str(
                                att.get("globalId") or att.get("id")
                            ),
                        }
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Attachment download attempt %d/%d failed for "
                        "%s/%s attachment %s (%s).",
                        attempt,
                        ATTACHMENT_MAX_ATTEMPTS,
                        layer_id,
                        oid,
                        att.get("id"),
                        type(exc).__name__,
                    )
                    if attempt < ATTACHMENT_MAX_ATTEMPTS:
                        time.sleep(2 ** (attempt - 1))
        return oid, results

    oid_to_atts: dict[object, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_for_oid, oid) for oid in unique_oids]
        for future in as_completed(futures):
            oid, results = future.result()
            oid_to_atts[oid] = results

    signs_df["attachments"] = signs_df[oid_col].map(
        lambda o: list(oid_to_atts.get(o, []))
    )
    total = sum(len(v) for v in oid_to_atts.values())
    n_with = int((signs_df["attachments"].map(len) > 0).sum())
    logger.info(
        "Downloaded %d images; %d/%d sign rows have at least one image",
        total,
        n_with,
        len(signs_df),
    )


def load_survey123(config: dict, base_path: Path) -> gpd.GeoDataFrame:
    """Load survey signs + images from the ArcGIS feature service."""
    survey_cfg = config["survey123"]
    repo_root = base_path.parent.parent
    output_crs = config.get("output_crs", "EPSG:4326")
    # The date/attribute filter applies to the parent survey records (matching the
    # Survey123 "0.CreationDate" filter). Repeat signs follow their parents, so the
    # repeat query is unfiltered and rows are kept only if their parent matched.
    parent_where = survey_cfg.get("parent_where") or survey_cfg.get("where") or "1=1"
    repeat_where = survey_cfg.get("repeat_where") or "1=1"
    field_map = survey_cfg.get("field_map", {}) or {}
    excluded_sign_types = {
        str(value).strip().casefold()
        for value in (survey_cfg.get("exclude_sign_types") or [])
        if str(value).strip()
    }

    client = _build_client(survey_cfg)
    parent_id, repeat_id = _resolve_layer_ids(client, survey_cfg)

    # Read field metadata up front so a potentially long GlobalID filter can
    # be applied to both layers before records cross the network.
    parent_info = client.layer_info(parent_id)
    repeat_info = client.layer_info(repeat_id)
    parent_gid_field = _find_global_id_field(parent_info)
    parent_field = _find_parent_field(repeat_info, field_map.get("repeat_parent_field"))
    if not parent_gid_field:
        raise ValueError("Could not determine the GlobalID field on the parent layer.")
    if not parent_field:
        raise ValueError(
            "Could not determine the parent-reference field on the repeat table; "
            "set survey123.field_map.repeat_parent_field."
        )

    parent_allowlist = _load_parent_allowlist(survey_cfg, repo_root)
    if parent_allowlist:
        parent_where = _combine_where(
            parent_where, _in_clause(parent_gid_field, parent_allowlist)
        )
        repeat_where = _combine_where(
            repeat_where, _in_clause(parent_field, parent_allowlist)
        )

    sign_type_field = field_map.get("sign_type", "sign_type")
    if excluded_sign_types:
        server_exclusion = ", ".join(
            _quote_sql_string(value) for value in sorted(excluded_sign_types)
        )
        repeat_where = _combine_where(
            repeat_where, f"{sign_type_field} NOT IN ({server_exclusion})"
        )

    # --- parent survey points ---
    logger.info("Querying parent layer %s with where: %s", parent_id, parent_where)
    parent_meta = client.query_layer(
        parent_id, where=parent_where, return_geometry=True
    )
    parent_oid_field = parent_meta.get("objectIdFieldName")

    parents: dict[str, dict] = {}
    for feat in parent_meta["features"]:
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry")
        gid = _normalize_guid(attrs.get(parent_gid_field))
        if geom is None or gid is None:
            continue
        parents[gid] = {
            "geometry": Point(geom["x"], geom["y"]),
            "oid": attrs.get(parent_oid_field),
        }
    logger.info("Queried %d parent survey points", len(parents))
    if not parents:
        raise ValueError("No parent records returned from the feature service.")
    if parent_allowlist is not None:
        returned_ids = set(parents)
        missing = parent_allowlist - returned_ids
        unexpected = returned_ids - parent_allowlist
        if (
            missing
            or unexpected
            or len(parent_meta["features"]) != len(parent_allowlist)
        ):
            raise ValueError(
                "Live parent records do not exactly match the configured allowlist: "
                f"expected={len(parent_allowlist)}, returned_features="
                f"{len(parent_meta['features'])}, normalized_unique="
                f"{len(returned_ids)}, "
                f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
            )

    # --- repeat sign records ---
    repeat_meta = client.query_layer(
        repeat_id, where=repeat_where, return_geometry=False
    )
    repeat_gid_field = _find_global_id_field(repeat_meta)
    repeat_oid_field = repeat_meta.get("objectIdFieldName")
    added_date_field = field_map.get("added_date", "CreationDate")

    rows: list[dict] = []
    for feat in repeat_meta["features"]:
        attrs = feat.get("attributes", {})
        parent_gid = _normalize_guid(_ci_get(attrs, parent_field))
        sign_type = _ci_get(attrs, sign_type_field)
        if str(sign_type or "").strip().casefold() in excluded_sign_types:
            logger.warning(
                "Defensively excluding repeat record %s with sign type %r.",
                attrs.get(repeat_gid_field),
                sign_type,
            )
            continue
        parent = parents.get(parent_gid)
        if parent is None:
            logger.warning(
                "Repeat record %s references unknown parent %s; skipping.",
                attrs.get(repeat_gid_field),
                parent_gid,
            )
            continue
        rows.append(
            {
                "source_sign_id": _normalize_guid(attrs.get(repeat_gid_field)),
                "source_location_id": parent_gid,
                "sign_type_code": sign_type,
                "added_date": _to_datetime(_ci_get(attrs, added_date_field)),
                "geometry": parent["geometry"],
                "_parent_oid": parent["oid"],
                "_repeat_oid": attrs.get(repeat_oid_field),
            }
        )
    logger.info("Queried %d sign (repeat) records", len(rows))

    signs_df = pd.DataFrame(rows)
    if signs_df.empty:
        raise ValueError("No sign records returned from the feature service.")

    limit = survey_cfg.get("limit")
    if limit:
        signs_df = signs_df.head(int(limit)).copy()
        logger.info("Limiting to first %d sign records for this run", len(signs_df))

    link_level = _resolve_link_level(client, survey_cfg, parent_id, repeat_id, signs_df)
    logger.info("Resolved attachment link level: %s", link_level)
    image_store = build_image_store(survey_cfg, repo_root)
    _attach_images(
        client, signs_df, link_level, parent_id, repeat_id, image_store, survey_cfg
    )

    signs_df = signs_df.drop(columns=["_parent_oid", "_repeat_oid"])
    signs_df["added_date"] = signs_df["added_date"].fillna(pd.Timestamp.now())

    gdf = gpd.GeoDataFrame(signs_df, geometry="geometry", crs="EPSG:4326")
    if str(gdf.crs) != output_crs:
        gdf = gdf.to_crs(output_crs)
    return gdf


def load_survey_shapefile(config: dict, base_path: Path) -> gpd.GeoDataFrame:
    """Load survey signs (no images) from the local Survey123 shapefile export."""
    from pyogrio import read_dataframe

    survey_cfg = config["survey123"]
    repo_root = base_path.parent.parent
    output_crs = config.get("output_crs", "EPSG:4326")

    shp_dir = Path(survey_cfg.get("shapefile_dir", "inputs/shp"))
    if not shp_dir.is_absolute():
        shp_dir = repo_root / shp_dir
    parent_file = survey_cfg.get("parent_shapefile", "Form_2.shp")
    repeat_file = survey_cfg.get("repeat_dbf", "sign_repeat.dbf")

    form = read_dataframe(str(shp_dir / parent_file))
    repeat = read_dataframe(str(shp_dir / repeat_file))
    logger.info(
        "Read %d survey points and %d sign records from %s",
        len(form),
        len(repeat),
        shp_dir,
    )

    form["_gid"] = form["globalid"].map(_normalize_guid)
    geom_lookup = dict(zip(form["_gid"], form.geometry, strict=False))

    source_location_id = repeat["parentglob"].map(_normalize_guid)
    geometry = source_location_id.map(geom_lookup)

    out = gpd.GeoDataFrame(
        {
            "source_sign_id": repeat["globalid"].map(_normalize_guid),
            "source_location_id": source_location_id,
            "sign_type_code": repeat.get("sign_type"),
            "added_date": pd.to_datetime(repeat.get("CreationDa"), errors="coerce"),
            "geometry": geometry,
        },
        geometry="geometry",
        crs=form.crs or "EPSG:4326",
    )
    missing = out["geometry"].isna().sum()
    if missing:
        logger.warning(
            "Dropping %d sign records with no matching parent point", missing
        )
    out = out[out["geometry"].notna()].copy()
    out["added_date"] = out["added_date"].fillna(pd.Timestamp.now())

    if out.crs is None:
        out = out.set_crs("EPSG:4326")
    if str(out.crs) != output_crs:
        out = out.to_crs(output_crs)
    return out
