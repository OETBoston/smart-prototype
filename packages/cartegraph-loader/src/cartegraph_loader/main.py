import datetime
import math
import uuid
from dotenv import load_dotenv
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import Point

from curb_utils.io_tools import load_config
from curb_utils.db_utils import SmartCurbDB


def preprocess_signs(
        signs_df,
        neighborhoods_gdf,
        config
    ):
    # filter out signs with missing lat/long
    no_nulls = signs_df[
        (signs_df["longitude"].notnull()) & \
                signs_df["latitude"].notnull() & \
                (signs_df["mutcd_code_field"].notnull())
    ]
    no_nulls["geometry"] = [
        Point(xy) for xy in zip(no_nulls["longitude"], no_nulls["latitude"])
    ]

    # filter for known parking signs
    sign_filter = "|".join(
        f"{code.lower()}*" for code in config["parking_mutcd_codes"]
    )

    parking_df = no_nulls[
        no_nulls["mutcd_code_field"].str.lower().str.match(sign_filter)
    ]

    # filter for duplicates by keeping the most recently modified record
    no_dupes = parking_df.sort_values(
        ["cg_last_modified_field", "attachment_cg_last_modified_field"],
        ascending=False
    ).drop_duplicates(subset="oid", keep="first")

    # filter out based on status
    valid_signs = no_dupes[~no_dupes["asset_status_field"].isin(config["status_filters"])]

    # make gdf
    signs_gdf = gpd.GeoDataFrame(valid_signs, geometry="geometry", crs="EPSG:4326")

    # filter for specific neighboorhood if specified
    if config["neighborhoods"]:
        spec_neighborhood = neighborhoods_gdf[
            neighborhoods_gdf["name"].isin(config["neighborhoods"])
        ]
        signs_gdf = gpd.sjoin(
            signs_gdf,
            spec_neighborhood,
            predicate="within",
            how="inner"
        )

    # group nearby signs together by truncating lat/long to the nearest grouping distance
    grouping_distance = config["grouping_distance_ft"]
    signs_gdf["truncated_geometry"] = signs_gdf["geometry"].to_crs("epsg:2249").apply(
        lambda p: Point(
            math.floor(p.x / grouping_distance) * grouping_distance,
            math.floor(p.y / grouping_distance) * grouping_distance,
        )
    ).to_crs(config["output_crs"])

    date_cols = ["entry_date_field", "cg_last_modified_field"]
    signs_gdf[date_cols] = signs_gdf[date_cols].apply(pd.to_datetime)
    signs_gdf.set_geometry("truncated_geometry", inplace=True)

    output_cols = [
        "oid",
        "entry_date_field",
        "mutcd_code_field",
        "asset_status_field",
        "attachment_public_url",
        "cg_last_modified_field",
        "truncated_geometry",
        "attachment_oid"
    ]
    return signs_gdf[output_cols]


def format_sign_tbls(
        signs_gdf,
        config
    ):
    # Format for asset_jobs table
    job_id = uuid.uuid4()
    asset_jobs = pd.DataFrame(
        {
            "job_id": [job_id],
            "job_name": [config["job_name"]],
            "job_description": [config["job_description"]]
        }
    )

    # Format for data_sources table
    data_source_id = uuid.uuid4()
    data_sources = pd.DataFrame(
        {
            "data_source_id": [data_source_id],
            "source_name": [config["data_source_name"]]
        }
    )

    # Format for asset_locations table
    asset_locations = signs_gdf.groupby(
        ['truncated_geometry'],
        as_index=False
    )['oid'].apply(lambda x: "oid: " + ', '.join(str(v) for v in x if pd.notna(v)))
    asset_locations["asset_location_id"] = [
        uuid.uuid4() for _ in range(len(asset_locations))
    ]
    asset_locations["data_source_id"] = data_source_id
    asset_locations["job_id"] = job_id
    asset_locations = asset_locations.rename(
        columns={
            "oid": "source_location_id",
            "truncated_geometry": "location"
        }
    )[
        [
            "asset_location_id",
            "data_source_id",
            "job_id",
            "source_location_id",
            "location"
        ]
    ]

    # Format for signs table
    signs_gdf["sign_id"] = [uuid.uuid4() for _ in range(len(signs_gdf))]
    signs_gdf["data_source_id"] = data_source_id
    signs_gdf["job_id"] = job_id
    signs_gdf["sign_notes"] = None
    signs_gdf["sign_removed_date"] = np.where(
        signs_gdf["asset_status_field"] == "Removed",
        signs_gdf["cg_last_modified_field"],
        None
    )
    signs = signs_gdf.merge(
        asset_locations[['location', 'asset_location_id']],
        left_on='truncated_geometry',
        right_on='location'
    ).rename(
        columns={
            "oid": "source_sign_id",
            "mutcd_code_field": "sign_type_code",
            "entry_date_field": "date_added",
            "asset_location_id": "sign_location_id"
        }
    )[
        [
            'sign_id',
            'sign_location_id',
            'data_source_id',
            'job_id',
            'source_sign_id',
            'date_added',
            'sign_removed_date',
            'sign_type_code',
            'sign_notes'
        ]
    ]

    # Format for images table
    images = signs_gdf[signs_gdf["attachment_public_url"].notnull()]
    images["image_id"] = [uuid.uuid4() for _ in range(len(images))]
    images["image_date"] = datetime.datetime.now()
    images = images.rename(
        columns={
            'attachment_public_url': 'uri',
            'attachment_oid': 'source_image_id'
        }
    )[
        [
            'image_id',
            'sign_id',
            'data_source_id',
            'job_id',
            'uri',
            'image_date',
            'source_image_id'
        ]
    ]
    to_upload_dict = {
        "asset_jobs": asset_jobs,
        "data_sources": data_sources,
        "asset_locations": asset_locations,
        "signs": signs,
        "images": images
    }
    return to_upload_dict


def upload_sign_tbls(
        upload_dict,
        dbname,
        schema,
        debug_mode=False
):
    load_dotenv()
    with SmartCurbDB(dbname=dbname, schema=schema) as db:
        for tbl_name, df in upload_dict.items(): 
            if not bool(debug_mode):
                db.append_data(tbl_name, df)



def main():
    # Read in config & files
    config = load_config(
        "packages/cartegraph-loader/src/cartegraph_loader/config.yaml"
    )
    signs_df = pd.read_csv(config["signs_path"])
    neighborhoods_gdf = gpd.read_file(
        config["neighborhoods_path"],
        crs="EPSG:4326"
    )[["name", "geometry"]]

    # Clean for relevant signs
    cleaned_signs_gdf = preprocess_signs(
        signs_df=signs_df,
        neighborhoods_gdf=neighborhoods_gdf,
        config=config
    )

    # Format signs for database tbls
    to_upload_dict = format_sign_tbls(
        signs_gdf=cleaned_signs_gdf,
        config=config
    )

    # Upload signs to database
    upload_sign_tbls(
        to_upload_dict,
        config["dbname"],
        config["schema"],
        config["debug_mode"]
    )


if __name__ == "__main__":
    main()
