"""Utility functions for sign-loader package."""

from typing import Any

import geopandas as gpd
import pandas as pd


def read_and_reproject_gdf(path: str, output_crs: str) -> gpd.GeoDataFrame:
    """Reads in geospatial data and reprojects to output CRS if necessary.
    Assumes GeoJson or Shapefile input with known CRS.
    """
    gdf = gpd.read_file(path)
    if not gdf.crs:
        raise ValueError(f"Input geospatial data at {path} missing CRS information.")
    if gdf.crs != output_crs:
        gdf = gdf.to_crs(output_crs)
    return gdf


def filter_by_geo(
    gdf_points: gpd.GeoDataFrame,
    gdf_polygons: gpd.GeoDataFrame,
    subset_column: str,
    subset_values: list[str],
) -> gpd.GeoDataFrame:
    """Geospatial filter. Currently only supports filtering for points within polygon.
    Useful for developing geographic subsets of data. Expects both to have the same CRS.
    """
    # Enforce that both geodataframes are in the same CRS before spatial join
    if gdf_points.crs != gdf_polygons.crs:
        raise ValueError("CRS mismatch between points and polygons geodataframes.")

    # Optionally, filter for specifc subset of the polygon data first
    # Useful for selected e.g. a single neighborhood
    if subset_column:
        if not subset_values:
            raise ValueError(
                "Subset values must be provided when subset column is specified."
            )
        gdf_polygons = gdf_polygons[gdf_polygons[subset_column].isin(subset_values)]

    df = gpd.sjoin(gdf_points, gdf_polygons, predicate="within", how="inner")
    return df


def filter_by_column_values(
    df: pd.DataFrame | gpd.GeoDataFrame, column: str, values: list[Any], mode: str
) -> pd.DataFrame | gpd.GeoDataFrame:
    """Filter a dataframe based column values. Supported modes include:
    "drop": drop rows where column value is in values list.
    "keep": keep only rows where column value is in values list.
    "starts_with": keep rows where column value starts
        with any value in values list.
    """
    if values is None or len(values) == 0:
        raise ValueError("Values list cannot be empty for column filtering.")
    if mode == "drop":
        df = df[~df[column].isin(values)]
    elif mode == "keep":
        df = df[df[column].isin(values)]
    elif mode == "starts_with":
        pattern = "|".join(f"{value.lower()}" for value in values)
        df = df[df[column].str.lower().str.match(pattern, na=False)]
    else:
        raise NotImplementedError(f"Unsupported column filter mode: {mode}")
    return df


def check_required_input_columns(
    source_column_info: dict, df: pd.DataFrame | gpd.GeoDataFrame
) -> None:
    """Check that all required input columns are present in the data."""
    input_columns = []

    def extract_columns(obj) -> None:
        """Recursively extract column names from nested structures."""
        if isinstance(obj, str):
            input_columns.append(obj)
        elif isinstance(obj, list):
            for item in obj:
                extract_columns(item)
        elif isinstance(obj, dict):
            for value in obj.values():
                extract_columns(value)

    extract_columns(source_column_info)
    missing_columns = [col for col in input_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required input columns: {missing_columns}")
