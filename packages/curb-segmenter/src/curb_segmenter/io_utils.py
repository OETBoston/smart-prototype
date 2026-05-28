"""
==============================================================================
I/O Module for Curb Segmentation Pipeline
==============================================================================
This module manages all input and output operations for the curb segmentation
workflow. It provides utility functions for reading, writing, and organizing
data used throughout the pipeline.

All I/O operations are designed to be modular, allowing easy adaptation to
different data formats or storage systems. Ensure that the functions defined
here handle file integrity checks and proper exception handling to maintain
pipeline reliability.
==============================================================================
"""

# Packages
# ==============================================================================
import os
import uuid
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
from curb_utils.db_utils import SmartCurbDB

import curb_segmenter.curb_segmentation as cs

# Functions
# ==============================================================================


def _get_asset_table_config(asset: str) -> dict:
    """
    Get table and column configuration for a given asset category.

    This centralized configuration avoids duplication across different data source loaders.

    Args:
        asset (str): Asset category ("sign_assets", "nonsign_assets", "parking_meters").

    Returns:
        dict: Configuration dict with table_name, native_id_col, native_location_id_col(s), and select_cols.

    Raises:
        ValueError: If asset type is invalid.
    """
    if asset == "sign_assets":
        return {
            "table_name": "signs",
            "native_id_col": "sign_id",
            "native_location_id_col": "sign_location_id",
            "select_cols": ["sign_id", "sign_location_id", "sign_removed_date"],
        }
    elif asset == "nonsign_assets":
        return {
            "table_name": "nonsign_features",
            "native_id_col": "feature_id",
            "native_location_id_col": "feature_location",
            "select_cols": ["feature_id", "feature_location"],
        }
    elif asset == "parking_meters":
        return {
            "table_name": "meter_policies",
            "native_id_col": "meter_policy_id",
            "native_location_id_cols": ["start_asset_location_id", "end_asset_location_id"],
            "select_cols": ["meter_policy_id", "start_asset_location_id", "end_asset_location_id"],
        }
    else:
        raise ValueError(f"Invalid asset type: {asset}")


def _process_asset_gdf(
        assets: pd.DataFrame,
        asset_locations: gpd.GeoDataFrame,
        asset: str,
        asset_type: str,
        asset_spec: dict,
        config: dict,
        target_crs: str,
) -> gpd.GeoDataFrame:
    """
    Process raw asset data into a properly formatted and projected GeoDataFrame.

    Encapsulates the common transformation logic used by both PostgreSQL and local data loaders.
    Handles column renaming, sign asset filtering, meter policy melting, location merging, and CRS validation.

    Args:
        assets (pd.DataFrame): Raw asset data retrieved from source.
        asset_locations (gpd.GeoDataFrame): Asset locations GeoDataFrame with geometries.
        asset (str): Asset category ("sign_assets", "nonsign_assets", "parking_meters").
        asset_type (str): Specific asset type identifier.
        asset_spec (dict): Asset specification dict with "new_id_col" and "job_id".
        config (dict): Asset table configuration from _get_asset_table_config().
        target_crs (str): Target coordinate reference system.

    Returns:
        gpd.GeoDataFrame: Processed and deduplicated asset GeoDataFrame.
    """
    native_id_col = config["native_id_col"]
    native_location_id_col = config.get("native_location_id_col")
    native_location_id_cols = config.get("native_location_id_cols")

    # Handle meter_policies melt operation
    if asset_type == "meter_policies":
        if assets.dropna().shape[0] == 0:
            assets = pd.DataFrame(columns=[native_id_col, "location_id"])
        else:
            assets = assets.melt(
                id_vars=native_id_col,
                value_vars=native_location_id_cols,
                var_name="location_type",
                value_name="location_id",
            )
        native_location_id_col = "location_id"

    # Rename ID columns
    assets = assets.rename(
        columns={
            native_id_col: asset_spec["new_id_col"],
            native_location_id_col: "location_id",
        }
    )

    # Filter active sign assets (sign_removed_date is null for active assets)
    if asset == "sign_assets":
        assets = assets[assets["sign_removed_date"].isna()].drop(columns=["sign_removed_date"])

    # Verify GeoDataFrame is properly formatted
    cs.confirm_gdf(asset_locations)

    # Merge assets with location geometries
    assets = assets.merge(asset_locations[["location_id", "geometry"]], on="location_id")
    assets = cs.check_and_set_crs(
        gdf=gpd.GeoDataFrame(assets, geometry="geometry", crs=asset_locations.crs),
        proj_crs=target_crs,
    )

    # Keep unique locations only; treat location IDs as asset IDs
    assets = (
        assets.drop_duplicates(subset=["location_id"])
        .drop(columns=[asset_spec["new_id_col"]])
        .rename(columns={"location_id": asset_spec["new_id_col"]})
    )

    return assets


def load_blockface_gdf_from_pg(
    dbname: str,
    schema: str,
    table_name: str,
    geom_col: str,
    filter_string: str | None,
    target_crs: str,
    reproject: bool = True,
) -> gpd.GeoDataFrame:
    """
    Load a GeoDataFrame from a PostgreSQL database and verify CRS.

    Args:
        dbname (str): Name of the database, e.g., "cds".
        schema (str): Name of the schema, e.g., "public" or "staging".
        table_name (str): Name of the table, e.g., "curb_blockfaces" or "curb_segments".
        geom_col (str): Name of the geometry column.
        filter_string (str | None): SQL-like filter string.
        target_crs (str): EPSG code of the target projected CRS (e.g., "epsg:4326").
        reproject (bool): Whether to reproject to the target CRS if the input is geographic,
            defaults to True.

    Returns:
        gdf (GeoDataFrame): Loaded and (optionally) reprojected GeoDataFrame.

    Raises:
        ValueError: If CRS is missing or invalid.
    """
    # Read the file
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        if filter_string:
            gdf = db.get_data(table_name, geom_col=geom_col, filter=filter_string)
        else:
            gdf = db.get_data(
                table_name,
                geom_col=geom_col,
            )

    if gdf.empty:
        raise ValueError(f"'{table_name}' table contains no features.")

    # Check CRS
    if gdf.crs is None:
        raise ValueError(
            f"The GeoDataFrame from '{table_name}' table does not have a CRS defined."
        )

    # Reproject, optional
    if reproject:
        if gdf.crs != target_crs:
            gdf = gdf.to_crs(target_crs)

    return gdf


def load_asset_gdfs_from_pg(
    config: dict,
    target_crs: str,
):
    """
    Loads asset GeoDataFrames from a PostgreSQL database based on asset type specifications.

    This function retrieves spatial data for specified asset types and their associated locations
    from a PostgreSQL database and organizes them into GeoDataFrames. The GeoDataFrames are
    structured according to the provided asset type specifications and coordinate reference settings.

    Args:
        config (dict): Configuration dictionary containing database and asset settings.
        target_crs (str): Target coordinate reference system (CRS) for the output GeoDataFrames.

    Returns:
        dict: A dictionary where keys are asset types from the asset_dict and values are
            GeoDataFrames containing the IDs, location IDs, and geometries for these assets.
    """
    # set the db parameters from config
    dbname = config["db_name"]
    schema = config["db_schema"]

    # get asset specifications from config
    asset_dict = config["assets"]

    # Define an empty collector dictionary to store the GeoDataFrames
    asset_gdfs = {}

    # Loop through the nonsign asset types and load the GeoDataFrames
    for asset, asset_config in asset_dict.items():
        # Get the relevant DB Job ID
        job_id = config["source_jobs"][asset]
        # Specify table names and column names based on an asset type
        if asset == "parking_sign":
            print(f"Loading parking signs...{job_id}")
            table_name = "signs"
            native_id_col = "sign_id"
            native_location_id_col = "sign_location_id"
            select_cols = [native_id_col, native_location_id_col, "sign_removed_date"]
        elif asset == "fire_hydrant":
            print(f"Loading fire hydrants...{job_id}")
            table_name = "nonsign_features"
            native_id_col = "feature_id"
            native_location_id_col = "feature_location"
            select_cols = [native_id_col, native_location_id_col]
        elif asset == "bus_stop":
            print(f"Loading bus stops...{job_id}")
            table_name = "nonsign_features"
            native_id_col = "feature_id"
            native_location_id_col = "feature_location"
            select_cols = [native_id_col, native_location_id_col]
        elif asset == "parking_meters":
            print(f"Loading parking meters...{job_id}")
            table_name = "meter_policies"
            native_id_col = "meter_policy_id"
            native_location_id_cols = [
                "start_asset_location_id",
                "end_asset_location_id",
            ]
            select_cols = [native_id_col] + native_location_id_cols
        else:
            raise ValueError(f"Invalid asset type: {asset}")

        with SmartCurbDB(dbname=dbname, schema=schema) as db:
            if asset == "parking_meters":
                pass
            assets = db.get_data(
                table_name=table_name,
                columns=select_cols,
                filter=f"feature_type = '{asset}'"
                if asset_config["asset_type"] == "nonsign_asset"
                else None,
            )
            if asset == "parking_meters":
                assets = assets.melt(native_id_col)
                native_location_id_col = "value"
            assets = assets.rename(
                columns={
                    native_id_col: asset_config["new_id_col"],
                    native_location_id_col: "location_id",
                }
            )
            # Select active sign assets: "sign_removed_date" column is null for them
            if asset == "parking_sign":
                assets = assets[assets["sign_removed_date"].isna()].drop(
                    columns=["sign_removed_date"]
                )

            # Get asset location geometry
            asset_locations = db.get_data(
                table_name="asset_locations",
                geom_col="location",
                columns=["asset_location_id", "location"],
                filter=f"job_id = '{job_id}'",
            )
            asset_locations = asset_locations.rename(
                columns={"asset_location_id": "location_id", "location": "geometry"}
            )
            # Check if curb dataset is already in GeoDataFrame
            cs.confirm_gdf(asset_locations)

            # Merge assets and asset locations and store GeoDataFrames in the collector dictionary
            assets = assets.merge(asset_locations, on="location_id")
            assets = cs.check_and_set_crs(
                gdf=gpd.GeoDataFrame(assets, geometry="geometry"),
                proj_crs=target_crs,
            )
            # Keep unique locations only. Consider location IDs as asset IDs.
            assets = (
                assets.drop_duplicates(subset=["location_id"])
                .drop(columns=[asset_config["new_id_col"]])
                .rename(columns={"location_id": asset_config["new_id_col"]})
            )
            asset_gdfs[asset] = assets
    return asset_gdfs


def write_curb_segments_to_db(
    gdf: gpd.GeoDataFrame,
    dbname: str,
    schema: str,
    job_id: uuid.UUID,
    job_name: str,
    job_description: str,
    ts: str,
    debug_mode: bool = True,
) -> None:
    """
    Writes curb segment data to a database and creates a curb segment job record for the data.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame object containing the curb segment data to be stored in the database.
        dbname (str): Name of the database where the data will be stored.
        schema (str): Name of the database schema where the data will be saved.
        job_id (uuid.UUID): Unique identifier for the job that generated the data.
        job_name (str): Name of the job to add as metadata in the `curb_segment_jobs` table.
        job_description (str): A description of the job, providing additional context about the data
            being stored.
        ts (str): Timestamp of the job execution.
        debug_mode (bool): If True, then it will not write the blockface data to the database.

    Returns:
        None
    """

    # Add a record to the table blockface_jobs
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        cs_job = pd.DataFrame(
            {
                "job_id": [job_id],
                "job_name": [f"[{ts}] {job_name}"],
                "job_description": [f"[{ts}] {job_description}"],
                "job_timestamp": [datetime.strptime(ts, "%Y%m%d-%H%M%S")],
            }
        )

        if not bool(debug_mode):
            db.append_data("curb_segment_jobs", cs_job)
            db.append_data("curb_segments", gdf)

        return None
    
def _convert_pg_uuid_array_to_list(values: object) -> object:
    """
    Convert PostgreSQL UUID array format back to Python lists.
    
    Converts strings like "{uuid1,uuid2,uuid3}" or "{}" back to lists.
    
    Args:
        values (object): Value that may be a postgres array string format
        
    Returns:
        object: List if values was a postgres array string, otherwise original value
    """
    if values is None:
        return None
    if not isinstance(values, str):
        return values
    if values == "{}":
        return []
    # Remove outer braces and split by comma
    if values.startswith("{") and values.endswith("}"):
        inner = values[1:-1]
        if inner:
            return inner.split(",")
        return []
    return values


def write_curb_segments_to_file(
    output_gdf: gpd.GeoDataFrame,
    job_id: uuid.UUID,
    timestamp: str,
    output_path: str,
    output_file_name: str,
    file_type: str = "GeoJSON",
    output_crs: str = "epsg:4326",
    test: bool = False,
) -> None:
    """
    Write the curb GeoDataFrame to a file in the specified format.

    Args:
        output_gdf (gpd.GeoDataFrame): GeoDataFrame to write
        job_id (uuid.UUID): Job ID for the curb segment dataset creation job
        timestamp (str): Timestamp for the curb segment dataset creation job
        output_path (str): Location to write file
        output_file_name (str): Name of the spatial file to write (without extension)
        file_type (str): Output format
        output_crs (str): Output CRS

    Returns:
        None

    Raises:
        ValueError: If File Type specified is not either `GeoJSON` or `Parquet`
    """
    # Convert postgres UUID array format back to lists for file output
    for col in ("upstream_loc_list", "downstream_loc_list"):
        if col in output_gdf.columns:
            output_gdf[col] = output_gdf[col].map(_convert_pg_uuid_array_to_list)

    # Ensure appropriate CRS is set
    try:
        if output_gdf.crs:
            output_gdf = output_gdf.to_crs(output_crs)
        else:
            output_gdf = output_gdf.set_crs(output_crs)
    except ValueError as e:
        raise ValueError(
            f"Output CRS {output_crs} was incorrect or unsupported: {e}"
        ) from e

    # Create the output path if it does not exist
    Path(output_path).mkdir(parents=True, exist_ok=True)
    if not test:
        output_file_name = f"{output_file_name}_job_id_{job_id}_{timestamp}"

    # Export
    if file_type.lower() == "geojson":
        output_gdf.to_file(
            Path(os.path.join(output_path, f"{output_file_name}.geojson")),
            driver="GeoJSON",
        )
    elif file_type.lower() == "parquet":
        output_gdf.to_parquet(
            Path(os.path.join(output_path, f"{output_file_name}.parquet"))
        )
    else:
        raise ValueError(f"File Type must be GeoJSON or Parquet, got '{file_type}'.")
