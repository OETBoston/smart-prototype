import datetime
import os
from typing import Any

import geopandas as gpd
import pandas as pd


def filter_by_geo(
        df: gpd.GeoDataFrame,
        config: dict
) -> gpd.GeoDataFrame:
    """Geospatial filter. Currently only supports filtering for points within polygon.
    Useful for developing geographic subsets of data.
    """
    neighborhoods_gdf = gpd.read_file(
            config["geo_filters"]["path"],
            crs=config["geo_filters"]["crs"],
        )[["name", "geometry"]]
    spec_neighborhood = neighborhoods_gdf[
        neighborhoods_gdf["name"].isin(config["geo_filters"]["subset_values"])
    ]
    if spec_neighborhood.crs != config["output_crs"]:
        spec_neighborhood = spec_neighborhood.to_crs(config["output_crs"])
    df = gpd.sjoin(
        df, spec_neighborhood, predicate="within", how="inner"
    )
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
