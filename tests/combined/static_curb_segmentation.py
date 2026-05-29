import os
from pathlib import Path
from typing import Optional, Union
import geopandas as gpd
import pandas as pd

import curb_segmenter.core as core
import curb_segmenter.curb_segmentation as cs
from curb_segmenter.config import CurbSegmenterConfig
from curb_utils.io_tools import load_from_yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEST_INPUT_DIR = REPO_ROOT / "tests" / "curb_segmenter" / "test_data" / "test00"


def load_config_from_local_yaml(
    config_file: Optional[Union[str, os.PathLike]] = None,
) -> CurbSegmenterConfig:
    """Load the curb-segmenter config from tests/combined/config.yaml by default."""
    local_path = Path(__file__).resolve().parent
    resolved_config = Path(config_file) if config_file else local_path / "config.yaml"
    if not resolved_config.is_absolute():
        resolved_config = local_path / resolved_config
    return CurbSegmenterConfig(**load_from_yaml(resolved_config))


def load_blockface_gdf_from_local(
    target_crs: str,
    input_dir: Union[str, os.PathLike] = "../inputs/policy-applier-test",
    table_name: str = "curb_blockfaces",
    geom_col: str = "geography",
    source_crs: Optional[str] = None,
        reproject: bool = True,
) -> gpd.GeoDataFrame:
    """
    Load curb blockfaces from local input files and verify CRS.

    Args:
        target_crs (str): EPSG code of the target projected CRS (e.g., "epsg:4326").
        input_dir (str | os.PathLike): Directory containing local input files.
        table_name (str): Logical table name, used to resolve "<table_name>.geojson".
        geom_col (str): Name of the output geometry column. Defaults to "geography".
        source_crs (str | None): Source CRS to set/override for local geometries before reprojection.
        reproject (bool): Whether to reproject to the target CRS if needed, defaults to True.

    Returns:
        gdf (GeoDataFrame): Loaded and (optionally) reprojected GeoDataFrame.

    Raises:
        FileNotFoundError: If the local curb blockface file is missing.
        ValueError: If data is empty or CRS is missing.
    """
    blockface_fp = Path(input_dir) / f"{table_name}.geojson"
    if not blockface_fp.exists():
        raise FileNotFoundError(f"Local blockface file not found: {blockface_fp}")

    gdf = gpd.read_file(blockface_fp)
    if gdf.empty:
        raise ValueError(f"'{table_name}' local file contains no features.")

    # Match DB-style output geometry column naming.
    if gdf.geometry.name != geom_col:
        gdf = gdf.rename_geometry(geom_col)

    # Set/override source CRS when local data uses a known CRS.
    if source_crs is not None:
        gdf = gdf.set_crs(source_crs, allow_override=True)

    # Check CRS
    if gdf.crs is None:
        raise ValueError(f"The GeoDataFrame from '{table_name}' local file does not have a CRS defined.")

    # Reproject, optional
    if reproject and gdf.crs != target_crs:
        gdf = gdf.to_crs(target_crs)

    return gdf

def read_in_assets(
        input_dir: Union[str, os.PathLike],
        table_name: str
) -> pd.DataFrame:
    asset_fp = Path(input_dir) / f"{table_name}.csv"
    if not asset_fp.exists():
        raise FileNotFoundError(f"Local asset file not found: {asset_fp}")
    assets_table = pd.read_csv(asset_fp)
    return assets_table


def load_asset_gdfs_from_local(
        asset_dict: dict,
        target_crs: str,
        input_dir: str | os.PathLike,
) -> dict:
    """
    Loads asset GeoDataFrames from local CSV files based on asset type specifications.

    This function mirrors the output format of `load_asset_gdfs_from_pg` by reading:
    - signs.csv
    - nonsign_features.csv
    - asset_locations.csv

    Geometry for asset locations is built from `location_x` and `location_y`.

    Args:
        asset_dict (dict): Dictionary defining the mapping of asset types to their specifications.
        target_crs (str): Target coordinate reference system (CRS) for the output GeoDataFrames.
        input_dir (str | os.PathLike): Directory containing local CSV files.
        location_crs (str): CRS for asset location x/y coordinates.
        asset_locations (pd.DataFrame): df version of csv data to be transformed.
        signs (pd.DataFrame): df version of csv data to be transformed.
        aonsign_features (pd.DataFrame): df version of csv data to be transformed.

    Returns:
        dict: A dictionary where keys are asset types from the asset_dict and values are
            GeoDataFrames containing the asset IDs and geometries.
    """
    input_dir = Path(input_dir)
    asset_locations_fp = input_dir / "asset_locations.geojson"
    if not asset_locations_fp.exists():
        raise FileNotFoundError(f"Local asset location file not found: {asset_locations_fp}")

    asset_locations = gpd.read_file(asset_locations_fp)
    job_id = "test-job"

    # Define an empty collector dictionary to store the GeoDataFrames
    asset_gdfs = {}
    # Loop through asset types and load the GeoDataFrames
    for asset, asset_info in asset_dict.items():
        # Match the table/column selection used in load_asset_gdfs_from_pg
        if asset == "parking_sign":
            table_name = "signs"
            native_id_col = "sign_id"
            native_location_id_col = "sign_location_id"
            select_cols = [native_id_col, native_location_id_col, "sign_removed_date"]
        elif asset in ["bus_stop", "fire_hydrant"]:
            table_name = "nonsign_features"
            native_id_col = "feature_id"
            native_location_id_col = "feature_location"
            select_cols = [native_id_col, native_location_id_col]
        elif asset == "parking_meters":
            table_name = "meter_policies"
            native_id_col = "meter_policy_id"
            native_location_id_cols = [
                "start_asset_location_id",
                "end_asset_location_id",
            ]
            select_cols = [native_id_col] + native_location_id_cols
        else:
            raise ValueError(f"Invalid asset type: {asset}")
    

        assets_table = read_in_assets(input_dir, table_name)
        asset_type = asset_info.get("asset_type", None)
        assets = assets_table.copy()
        if asset_type == "nonsign_asset":
            assets = assets[assets["feature_type"] == asset]

        # Mirror DB select behavior
        if asset_type == "sign_asset" and "sign_removed_date" not in assets.columns:
            assets["sign_removed_date"] = pd.NA
        assets = assets[select_cols]

        if asset_type == "parking_meter":
            if assets.dropna().shape[0] == 0:
                assets = pd.DataFrame(columns=[native_id_col, 'location_id'])
            else:
                assets = assets.melt(
                    id_vars=native_id_col,
                    value_vars=native_location_id_cols,
                    var_name="location_type",
                    value_name="location_id"
                )
            native_location_id_col = "location_id"

        assets = assets.rename(
            columns={
                native_id_col: asset_info.get("new_id_col", None),
                native_location_id_col: "location_id",
            }
        )

        # Select active sign assets: sign_removed_date is null for them
        if asset == "parking_sign":
            assets = assets[assets["sign_removed_date"].isna()].drop(columns=["sign_removed_date"])

        # Mirror DB location query: filter by job_id; if no match in local test data, fallback to all.
        job_id = asset_info.get("job_id", None)
        current_locations = asset_locations[asset_locations["job_id"] == job_id].copy()
        if current_locations.empty:
            current_locations = asset_locations.copy()
        current_locations = current_locations.rename(
            columns={
                "asset_location_id": "location_id",
            }
        )
        current_locations = gpd.GeoDataFrame(
            current_locations,
            geometry="geometry",
            crs=asset_locations.crs
        )
        # Check if curb dataset is already in GeoDataFrame
        cs.confirm_gdf(current_locations)
        # Merge assets and asset locations and store GeoDataFrames in the collector dictionary
        assets = assets.merge(current_locations[["location_id", "geometry"]], on="location_id")
        assets = cs.check_and_set_crs(
            gdf=gpd.GeoDataFrame(assets, geometry="geometry", crs=current_locations.crs),
            proj_crs=target_crs,
        )
        # Keep unique locations only. Consider location IDs as asset IDs.
        assets = (
            assets.drop_duplicates(subset=["location_id"])
            .drop(columns=[asset_info.get("new_id_col", None)])
            .rename(columns={"location_id": asset_info.get("new_id_col", None)})
        )
        asset_gdfs[asset] = assets

    return asset_gdfs


def load_data(
    config: CurbSegmenterConfig,
    input_dir: Optional[Union[str, os.PathLike]] = None,
) -> tuple:
    config_data = config.model_dump()
    full_input_dir: Path = (
        Path(input_dir).resolve() if input_dir is not None else DEFAULT_TEST_INPUT_DIR
    )

    # Read curb lines
    curbs = load_blockface_gdf_from_local(
        input_dir=full_input_dir,
        table_name=config_data["bf_table_name"],
        geom_col=config_data["bf_geom_col"],
        source_crs=config_data["proj_crs"],
        target_crs=config_data["proj_crs"],
    )

    # Read asset locations
    asset_dict = load_asset_gdfs_from_local(
        asset_dict=config_data["assets"],
        target_crs=config_data["proj_crs"],
        input_dir=full_input_dir
    )
    return curbs, asset_dict


def run_static_curb_segmentation_pipeline(
    input_dir: Optional[Union[str, os.PathLike]] = None,
) -> None:
    resolved_input_dir = (
        Path(input_dir).resolve() if input_dir is not None else DEFAULT_TEST_INPUT_DIR
    )
    config = load_config_from_local_yaml().model_copy(
        update={
            "proj_dir": str(resolved_input_dir),
            "final_output_dir": str(resolved_input_dir),
        }
    )

    curbs, asset_dict = load_data(config, input_dir=resolved_input_dir)
    core.run_curb_segmentation_pipeline(
        config,
        curbs,
        asset_dict,
        test_mode=True
    )


if __name__ == "__main__":
    run_static_curb_segmentation_pipeline()
