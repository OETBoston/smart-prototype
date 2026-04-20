import uuid
import pandas as pd
import geopandas as gpd
from shapely.geometry.base import BaseGeometry



def add_curb_zone(
    curb_zones: gpd.GeoDataFrame,
    curb_zone_id: uuid.UUID,
    geom: BaseGeometry,
    run_date: pd.Timestamp,
) -> gpd.GeoDataFrame:

    new_row_gdf = gpd.GeoDataFrame([
        {
            "curb_zone_id": curb_zone_id,
            "geometry": geom,
            "published_date": run_date,
            "last_updated_date": run_date,
            "start_date": run_date,
            "end_date": None,
        }
    ], crs=curb_zones.crs)

    curb_zones = pd.concat([curb_zones, new_row_gdf], ignore_index=True)

    return curb_zones


def retire_curb_zone(
        curb_zones: gpd.GeoDataFrame,
        curb_zone_id: uuid.UUID,
        run_date: pd.Timestamp,
) -> gpd.GeoDataFrame:

    mask = curb_zones['curb_zone_id'] == curb_zone_id
    curb_zones.loc[mask, ['end_date', 'last_updated_date']] = run_date

    return curb_zones
