# utilities/data/queries_and_contracts.py
from typing import Optional, List, Dict, Any, Union, ClassVar
from datetime import datetime
from pydantic import BaseModel, Field, RootModel, ConfigDict
from google.cloud.bigquery import SchemaField
from .geometry_support import Geometry
from .core_queries_and_contracts import *
from .auto_filters import with_auto_filter

TEST_TABLE_NAME = "test_table_for_db_accessor"

@with_auto_filter
class SimpleEntityModel(ValidatedBaseEntity):
    """Pydantic model representing a single record from the test table."""
    
    # Static metadata for the BigQuery table
    _TABLE_NAME: ClassVar[str] = TEST_TABLE_NAME
    
    # BigQuery Schema definition (using ClassVar for clarity)
    _ENTITY_SCHEMA: ClassVar[Dict[str, str]] = { 
        "id": "STRING",
        "type": "STRING",
        "time": "TIMESTAMP", 
        "location": "GEOGRAPHY",
    }
    
    # Instance Fields (data types for Python/Pydantic validation)
    id: str
    type: str
    time: datetime
    location: Geometry

SimpleEntityFilter = SimpleEntityModel.Filter

class RawData(RootModel): # Inherit from RootModel
    # Use 'root' instead of '__root__'
    root: Dict[str, Any] 

    def __getitem__(self, key):
        # Access the validated data through .root
        return self.root[key]

# --- Union Type Alias for the Get Method Signature ---
EntityModel = SimpleEntityModel
EntityFilter = SimpleEntityModel.Filter
GetReturnType = Union[List[EntityModel], EntityModel, List[RawData], RawData]





@with_auto_filter
class StreetSegmentEntityModel(ValidatedBaseEntity):
    """
    Pydantic model representing schema and table name for street segments
    """
    
    # Static metadata for the BigQuery table
    _TABLE_NAME: ClassVar[str] = "stg_street_segments"
    
    # BigQuery Schema definition (Field Name: BigQuery Data Type)
    _ENTITY_SCHEMA: ClassVar[Dict[str, str]] = { 
        "objectid": "INTEGER",
        "segment_id": "INTEGER",
        "l_f_add": "STRING",
        "l_t_add": "STRING",
        "r_f_add": "STRING",
        "r_t_add": "STRING",
        "street_id": "INTEGER",
        "pre_dir": "STRING",
        "st_name": "STRING",
        "st_type": "STRING",
        "suf_dir": "STRING",
        "alternate_name": "STRING",
        "cfcc": "STRING",
        "speed_limit": "INTEGER",
        "oneway": "STRING",
        "f_zlev": "INTEGER",
        "t_zlev": "INTEGER",
        "ft_cost": "FLOAT",
        "tf_cost": "FLOAT",
        "ft_dir": "STRING",
        "tf_dir": "STRING",
        "shield": "STRING",
        "hwy_num": "STRING",
        "mun_l": "STRING",
        "mun_r": "STRING",
        "nbhd_l": "STRING",
        "nbhd_r": "STRING",
        "state00_l": "STRING",
        "state00_r": "STRING",
        "county00_l": "STRING",
        "county00_r": "STRING",
        "mcd00_l": "STRING",
        "mcd00_r": "STRING",
        "shape_length_src": "FLOAT",
        "shape_wkt": "STRING",
        # GEOGRAPHY types are commonly handled as strings (WKT/GeoJSON) in Pydantic
        "geom": "GEOGRAPHY", 
        "batch_timestamp": "TIMESTAMP",
        "ingested_at": "TIMESTAMP",
        "batch": "STRING",
        "source_name": "STRING",
        "source_file": "STRING",
        "schema_version": "STRING",
        "length_m": "FLOAT",
    }

    # Integer Fields
    objectid: Optional[int]
    segment_id: Optional[int]
    street_id: Optional[int]
    speed_limit: Optional[int]
    f_zlev: Optional[int]
    t_zlev: Optional[int]

    # Float Fields
    ft_cost: Optional[float]
    tf_cost: Optional[float]
    shape_length_src: Optional[float]
    length_m: Optional[float]

    # Timestamp Fields
    batch_timestamp: Optional[datetime]
    ingested_at: Optional[datetime]

    # String Fields (All 26 are now Optional)
    l_f_add: Optional[str]
    l_t_add: Optional[str]
    r_f_add: Optional[str]
    r_t_add: Optional[str]
    pre_dir: Optional[str]
    st_name: Optional[str]
    st_type: Optional[str]
    suf_dir: Optional[str]
    alternate_name: Optional[str]
    cfcc: Optional[str]
    oneway: Optional[str]
    ft_dir: Optional[str]
    tf_dir: Optional[str]
    shield: Optional[str]
    hwy_num: Optional[str]
    mun_l: Optional[str]
    mun_r: Optional[str]
    nbhd_l: Optional[str]
    nbhd_r: Optional[str]
    state00_l: Optional[str]
    state00_r: Optional[str]
    county00_l: Optional[str]
    county00_r: Optional[str]
    mcd00_l: Optional[str]
    mcd00_r: Optional[str]
    shape_wkt: Optional[str]
    batch: Optional[str]
    source_name: Optional[str]
    source_file: Optional[str]
    schema_version: Optional[str]
    
    # Geography Field (Mapped to String)
    geom: Optional[Geometry]

StreetSegmentFilterModel=StreetSegmentEntityModel.Filter


@with_auto_filter
class RawSignAssetEntityModel(ValidatedBaseEntity):
    """
    Pydantic model representing schema and table name for Raw Sign Asset data.
    """
    
    # --- Static metadata for the BigQuery table (following the sample structure) ---
    _TABLE_NAME: ClassVar[str] = "stg_cartegraph"  # Example table name
    
    # BigQuery Schema definition (Field Name: BigQuery Data Type)
    _ENTITY_SCHEMA: ClassVar[Dict[str, str]] = { 
        "oid": "INTEGER",
        "cartegraph_id": "STRING",
        "locator_address_number_field": "STRING",
        "locator_street_field": "STRING",
        "locator_city_field": "STRING",
        "address_number_field": "FLOAT",
        "street_field": "STRING",
        "neighborhood_field": "STRING",
        "city_field": "STRING",
        "county_field": "STRING",
        "state_field": "STRING",
        "height_field_amount": "FLOAT",
        "height_field_unit": "STRING",
        "width_field_amount": "FLOAT",
        "width_field_unit": "STRING",
        "mutcd_code_field": "STRING",
        "directionof_sign_arrow_field": "STRING",
        "sign_direction_field": "STRING",
        "sign_orientation_field": "STRING",
        "cg_last_modified_field": "TIMESTAMP",
        "entry_date_field": "TIMESTAMP",
        "replaced_field": "TIMESTAMP",
        "retired_field": "TIMESTAMP",
        "signalized_intersections_id_field": "STRING",
        "support_field": "STRING",
        "asset_status_field": "STRING",
        "special_sign_description_field": "STRING",
        "notes_field": "STRING",
        "geom": "GEOGRAPHY",
        "latitude": "FLOAT",
        "longitude": "FLOAT",
        "arrow_dir": "STRING",
        "geom_quality": "STRING",
        "address_quality": "STRING",
        "lifecycle_status": "STRING",
        "age_days": "INTEGER",
        "ingested_at": "TIMESTAMP",
        "batch_timestamp": "TIMESTAMP",
        "source_name": "STRING",
        "source_file": "STRING",
        "schema_version": "STRING",
    }


    # 1. Integer Fields (BigQuery: INTEGER)
    oid: Optional[int]
    age_days: Optional[int]

    # 2. Float Fields (BigQuery: FLOAT)
    address_number_field: Optional[float]
    height_field_amount: Optional[float]
    width_field_amount: Optional[float]
    latitude: Optional[float]
    longitude: Optional[float]

    # 3. Timestamp Fields (BigQuery: TIMESTAMP)
    cg_last_modified_field: Optional[datetime]
    entry_date_field: Optional[datetime]
    replaced_field: Optional[datetime]
    retired_field: Optional[datetime]
    ingested_at: Optional[datetime]
    batch_timestamp: Optional[datetime]

    # 4. String/Geography Fields (BigQuery: STRING, GEOGRAPHY)
    # GEOGRAPHY is typically mapped to a string (WKT/GeoJSON) in Pydantic models.
    cartegraph_id: Optional[str]
    locator_address_number_field: Optional[str]
    locator_street_field: Optional[str]
    locator_city_field: Optional[str]
    street_field: Optional[str]
    neighborhood_field: Optional[str]
    city_field: Optional[str]
    county_field: Optional[str]
    state_field: Optional[str]
    height_field_unit: Optional[str]
    width_field_unit: Optional[str]
    mutcd_code_field: Optional[str]
    directionof_sign_arrow_field: Optional[str]
    sign_direction_field: Optional[str]
    sign_orientation_field: Optional[str]
    signalized_intersections_id_field: Optional[str]
    support_field: Optional[str]
    asset_status_field: Optional[str]
    special_sign_description_field: Optional[str]
    notes_field: Optional[str]
    geom: Optional[Geometry]  # GEOGRAPHY type handled as string
    arrow_dir: Optional[str]
    geom_quality: Optional[str]
    address_quality: Optional[str]
    lifecycle_status: Optional[str]
    source_name: Optional[str]
    source_file: Optional[str]
    schema_version: Optional[str]

RawSignAssetFilterModel = RawSignAssetEntityModel.Filter


class RawSignAssetEntityModelWithAttachments(ValidatedBaseEntity):
    """
    Model for a single Sign Asset record, derived from a JOIN 
    between stg_cartegraph and stg_cartegraph_attachments.

    NOTE: This model uses the _SQL_QUERY class variable for reading 
    and is NOT intended for single-table INSERT/DELETE operations.
    """

    asset_status_field: Optional[str]
    attachment_public_url: Optional[str]
    cartegraph_id: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]

    attachment_cg_last_modified_field: Optional[datetime]

    _TABLE_NAME: ClassVar[str] = "JOINED_ASSET_ATTACHMENTS"
    
    _SQL_QUERY: ClassVar[str] = """
        SELECT
            t1.asset_status_field,
            t1.cartegraph_id,
            t1.latitude,
            t1.longitude,
            t2.attachment_cg_last_modified_field,
            t2.attachment_public_url
        FROM
            `{table_prefix}.stg_cartegraph` AS t1
        LEFT JOIN (
            SELECT
                cartegraph_id,
                attachment_cg_last_modified_field,
                attachment_public_url,
                ROW_NUMBER() OVER (PARTITION BY cartegraph_id ORDER BY attachment_cg_last_modified_field DESC) AS rn
            FROM
                `{table_prefix}.stg_cartegraph_attachments`
        ) AS t2
            ON t1.cartegraph_id = t2.cartegraph_id
        WHERE t2.rn = 1 OR t2.rn IS NULL
    """

    # Strict configuration
    model_config = ConfigDict(extra='forbid')












class RoadInventoryBBox(ValidatedBaseEntity):
    """
    Pydantic model for the nested BigQuery RECORD field `bbox`.
    """
    xmin: Optional[float] = None
    ymin: Optional[float] = None
    xmax: Optional[float] = None
    ymax: Optional[float] = None


@with_auto_filter
class RoadInventoryEntityModel(ValidatedBaseEntity):
    """
    Pydantic base model representing schema and table name for road inventory.
    """

    # Static metadata for the BigQuery table
    _TABLE_NAME: ClassVar[str] = "stg_road_inventory"

    # BigQuery Schema definition (Field Name: BigQuery Data Type)
    _ENTITY_SCHEMA: ClassVar[Dict[str, str]] = {
        "objectid": "INTEGER",
        "route_id": "STRING",
        "from_measure": "FLOAT",
        "to_measure": "FLOAT",
        "route_system": "STRING",
        "route_number": "STRING",
        "route_direction": "STRING",
        "rd_seg_id": "INTEGER",
        "facility": "FLOAT",
        "mile_count": "FLOAT",
        "urban_area": "STRING",
        "urban_type": "FLOAT",
        "f_f_class": "INTEGER",
        "jurisdictn": "STRING",
        "nhs": "FLOAT",
        "fd_aid_rd": "FLOAT",
        "control": "FLOAT",
        "num_lanes": "FLOAT",
        "opp_lanes": "FLOAT",
        "surface_tp": "FLOAT",
        "surface_wd": "FLOAT",
        "shldr_lt_w": "FLOAT",
        "shldr_lt_t": "FLOAT",
        "shldr_rt_w": "FLOAT",
        "shldr_rt_t": "FLOAT",
        "shldr_ul_w": "FLOAT",
        "shldr_ul_t": "FLOAT",
        "med_width": "FLOAT",
        "med_type": "FLOAT",
        "curb": "FLOAT",
        "lt_sidewlk": "FLOAT",
        "rt_sidewlk": "FLOAT",
        "pd_sf_type": "FLOAT",
        "pd_fc_type": "FLOAT",
        "path_width": "INTEGER",
        "operation": "FLOAT",
        "speed_lim": "FLOAT",
        "op_dir_sl": "FLOAT",
        "speed_reg": "FLOAT",
        "t_exc_type": "FLOAT",
        "t_exc_time": "FLOAT",
        "trk_permit": "STRING",
        "trk_netwrk": "FLOAT",
        "truck_rte": "FLOAT",
        "row_width": "FLOAT",
        "toll_road": "FLOAT",
        "mhs": "FLOAT",
        "city": "INTEGER",
        "mun_type": "INTEGER",
        "county": "INTEGER",
        "hwy_dist": "INTEGER",
        "rpa": "STRING",
        "rta": "STRING",
        "mpo": "INTEGER",
        "st_name": "STRING",
        "city_maint": "FLOAT",
        "length": "FLOAT",
        "created_user": "STRING",
        "created_date": "TIMESTAMP",
        "last_edited_user": "STRING",
        "last_edited_date": "TIMESTAMP",
        "record_id": "STRING",
        "globalid": "STRING",
        "oneway": "STRING",
        "shape_length": "FLOAT",
        "geometry": "GEOGRAPHY",
        "bbox": "RECORD",  # nested RECORD with xmin/ymin/xmax/ymax
        "measure_length": "FLOAT",
        "total_lanes": "FLOAT",
        "road_classification": "STRING",
        "is_nhs": "BOOLEAN",
        "is_toll_road": "BOOLEAN",
        "is_oneway": "BOOLEAN",
        "centroid": "GEOGRAPHY",
        "geometry_length_miles": "FLOAT",
        "batch_timestamp": "TIMESTAMP",
        "ingested_at": "TIMESTAMP",
        "batch": "STRING",
        "source_name": "STRING",
        "source_file": "STRING",
        "schema_version": "STRING",
    }


    # Integer fields
    objectid: Optional[int] = None
    rd_seg_id: Optional[int] = None
    path_width: Optional[int] = None
    city: Optional[int] = None
    mun_type: Optional[int] = None
    county: Optional[int] = None
    hwy_dist: Optional[int] = None
    mpo: Optional[int] = None
    f_f_class: Optional[int] = None

    # Float fields
    from_measure: Optional[float] = None
    to_measure: Optional[float] = None
    facility: Optional[float] = None
    mile_count: Optional[float] = None
    urban_type: Optional[float] = None
    nhs: Optional[float] = None
    fd_aid_rd: Optional[float] = None
    control: Optional[float] = None
    num_lanes: Optional[float] = None
    opp_lanes: Optional[float] = None
    surface_tp: Optional[float] = None
    surface_wd: Optional[float] = None
    shldr_lt_w: Optional[float] = None
    shldr_lt_t: Optional[float] = None
    shldr_rt_w: Optional[float] = None
    shldr_rt_t: Optional[float] = None
    shldr_ul_w: Optional[float] = None
    shldr_ul_t: Optional[float] = None
    med_width: Optional[float] = None
    med_type: Optional[float] = None
    curb: Optional[float] = None
    lt_sidewlk: Optional[float] = None
    rt_sidewlk: Optional[float] = None
    pd_sf_type: Optional[float] = None
    pd_fc_type: Optional[float] = None
    operation: Optional[float] = None
    speed_lim: Optional[float] = None
    op_dir_sl: Optional[float] = None
    speed_reg: Optional[float] = None
    t_exc_type: Optional[float] = None
    t_exc_time: Optional[float] = None
    trk_netwrk: Optional[float] = None
    truck_rte: Optional[float] = None
    row_width: Optional[float] = None
    toll_road: Optional[float] = None
    mhs: Optional[float] = None
    city_maint: Optional[float] = None
    length: Optional[float] = None
    shape_length: Optional[float] = None
    measure_length: Optional[float] = None
    total_lanes: Optional[float] = None
    geometry_length_miles: Optional[float] = None

    # String fields
    route_id: Optional[str] = None
    route_system: Optional[str] = None
    route_number: Optional[str] = None
    route_direction: Optional[str] = None
    urban_area: Optional[str] = None
    jurisdictn: Optional[str] = None
    trk_permit: Optional[str] = None
    rpa: Optional[str] = None
    rta: Optional[str] = None
    st_name: Optional[str] = None
    created_user: Optional[str] = None
    last_edited_user: Optional[str] = None
    record_id: Optional[str] = None
    globalid: Optional[str] = None
    oneway: Optional[str] = None
    road_classification: Optional[str] = None
    batch: Optional[str] = None
    source_name: Optional[str] = None
    source_file: Optional[str] = None
    schema_version: Optional[str] = None

    # Timestamp fields
    created_date: Optional[datetime] = None
    last_edited_date: Optional[datetime] = None
    batch_timestamp: Optional[datetime] = None
    ingested_at: Optional[datetime] = None

    # Boolean fields
    is_nhs: Optional[bool] = None
    is_toll_road: Optional[bool] = None
    is_oneway: Optional[bool] = None

    # Geography fields (handled as strings, e.g. WKT/GeoJSON)
    geometry: Optional[Geometry] = None
    centroid: Optional[Geometry] = None

    # RECORD field
    bbox: Optional[RoadInventoryBBox] = None



RoadInventoryFilterModel = RoadInventoryEntityModel.Filter



@with_auto_filter
class CurbLineEntityModel(ValidatedBaseEntity):
    """
    Base model defining schema + table for curb line data.
    """

    _TABLE_NAME: ClassVar[str] = "stg_curb_lines"

    _ENTITY_SCHEMA: ClassVar[Dict[str, str]] = {
        "curb_id": "INTEGER",
        "roadway_id": "INTEGER",
        "street_name": "STRING",
        "route_id": "STRING",
        "route_direction": "STRING",
        "ff_class": "INTEGER",
        "side": "STRING",
        "buffer_left": "INTEGER",
        "buffer_right": "INTEGER",
        "start_lon": "FLOAT",
        "start_lat": "FLOAT",
        "end_lon": "FLOAT",
        "end_lat": "FLOAT",
        "curb_length_ft": "FLOAT",
        "geometry": "STRING",
        "processed_timestamp": "TIMESTAMP",
        "schema_version": "STRING",
    }

    model_config = ConfigDict(extra="forbid")

    @property
    def table_name(self) -> str:
        return self._TABLE_NAME

    @property
    def entity_schema(self) -> Dict[str, str]:
        return self._ENTITY_SCHEMA

    curb_id: Optional[int]= None
    roadway_id: Optional[int]= None
    street_name: Optional[str]= None
    route_id: Optional[str]= None
    route_direction: Optional[str]= None
    ff_class: Optional[int]= None
    side: Optional[str]= None
    buffer_left: Optional[int]= None
    buffer_right: Optional[int]= None
    start_lon: Optional[float]= None
    start_lat: Optional[float]= None
    end_lon: Optional[float]= None
    end_lat: Optional[float]= None
    curb_length_ft: Optional[float]= None
    geometry: Optional[Geometry]= None
    processed_timestamp: Optional[datetime]= None
    schema_version: Optional[str] = None


CurbLineFilterModel = CurbLineEntityModel.Filter
