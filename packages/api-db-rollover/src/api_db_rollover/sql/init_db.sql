-- Initialize public_cds_next for next update
CREATE SCHEMA IF NOT EXISTS public_cds_next;
SET search_path to public_cds_next, public;

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Create tables

CREATE TABLE IF NOT EXISTS curb_zones (
    curb_zone_id UUID PRIMARY KEY,
    -- GEOMETRY (not GEOGRAPHY): matches live public_cds and is required by the
    -- api-updater export path (geopandas.to_postgis -> Find_SRID only resolves
    -- registered geometry columns; a geography column makes the write fail).
    geometry GEOMETRY(LINESTRING, 4326),
    published_date TIMESTAMP,
    last_updated_date TIMESTAMP,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    name VARCHAR,
    description TEXT,
    jurisdiction_type VARCHAR,
    owner_name VARCHAR,
    user_zone_id VARCHAR,
    street_name VARCHAR,
    address_number VARCHAR,
    cross_street_start_name VARCHAR,
    length INTEGER,
    available BOOLEAN,
    available_space_lengths INTEGER[],
    availability_time TIMESTAMP,
    width INTEGER,
    parking_angle VARCHAR,
    num_spaces INTEGER,
    street_side VARCHAR,
    median BOOLEAN,
    entire_roadway BOOLEAN
);

CREATE INDEX idx_curb_zones_geometry ON curb_zones USING gist (geometry);

CREATE TABLE IF NOT EXISTS curb_policy_colors (
    color_id UUID PRIMARY KEY,
    primary_color VARCHAR,
    primary_pattern_type VARCHAR,
    primary_border_color VARCHAR,
    primary_border_pattern_type VARCHAR,
    secondary_color VARCHAR,
    secondary_border_color VARCHAR,
    secondary_border_pattern_type VARCHAR
);

CREATE TABLE IF NOT EXISTS curb_policies (
    curb_policy_id UUID PRIMARY KEY,
    name VARCHAR,
    description TEXT,
    published_date TIMESTAMP,
    priority INTEGER,
    policy_color_id UUID REFERENCES curb_policy_colors(color_id)
);

CREATE TABLE IF NOT EXISTS curb_zone_policies (
    curb_zone_id UUID REFERENCES curb_zones(curb_zone_id),
    curb_policy_id UUID REFERENCES curb_policies(curb_policy_id),
    PRIMARY KEY (curb_zone_id, curb_policy_id)
);

CREATE TABLE IF NOT EXISTS curb_policy_rules (
    rule_id UUID PRIMARY KEY,
    curb_policy_id UUID REFERENCES curb_policies(curb_policy_id),
    name VARCHAR,
    description TEXT,
    activity VARCHAR,
    max_stay INTEGER,
    max_stay_unit VARCHAR,
    no_return INTEGER,
    no_return_unit VARCHAR,
    user_classes TEXT[],
    user_classes_except TEXT[],
    purposes TEXT[]
);

CREATE TABLE IF NOT EXISTS curb_policy_time_spans (
    time_span_id UUID PRIMARY KEY,
    curb_policy_id UUID REFERENCES curb_policies(curb_policy_id),
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    days_of_week VARCHAR[],
    days_of_month INTEGER[],
    weeks_of_month INTEGER[],
    months INTEGER[],
    time_of_day_start VARCHAR,
    time_of_day_end VARCHAR,
    designated_period VARCHAR,
    designated_period_except BOOLEAN
);

CREATE TABLE IF NOT EXISTS curb_policy_rates (
    rate_id UUID PRIMARY KEY,
    curb_policy_id UUID REFERENCES curb_policies(curb_policy_id),
    rate INTEGER,
    rate_unit rate_unit_enum,
    rate_unit_period rate_unit_period_enum default 'rolling',
    increment_duration INTEGER,
    increment_amount INTEGER,
    start_duration INTEGER,
    end_duration INTEGER,
    max_fee INTEGER
);

-- Create Views

DROP VIEW IF EXISTS vw_curb_zones;
CREATE OR REPLACE VIEW vw_curb_zones AS
SELECT
    cz.curb_zone_id,
    cz.geometry,
    ST_AsGeoJSON(cz.geometry) AS geometry_json, 
    ARRAY(
        SELECT curb_policy_id
        FROM curb_zone_policies czp
        WHERE czp.curb_zone_id = cz.curb_zone_id
    ) AS curb_policy_ids,
    cz.published_date,
    cz.last_updated_date,
    cz.start_date,
    cz.end_date,
    cz.name,
    cz.description,
    cz.jurisdiction_type,
    cz.owner_name,
    cz.user_zone_id,
    cz.street_name,
    cz.address_number,
    cz.cross_street_start_name,
    cz.length,
    cz.available,
    cz.available_space_lengths,
    cz.availability_time,
    cz.width,
    cz.parking_angle,
    cz.num_spaces,
    cz.street_side,
    cz.median,
    cz.entire_roadway
FROM curb_zones cz;

DROP VIEW IF EXISTS vw_curb_policies;
CREATE OR REPLACE VIEW vw_curb_policies AS
SELECT
    cp.curb_policy_id,
    cp.name,
    cp.description,
    cp.published_date,
    cp.priority,
    (
        SELECT jsonb_agg(to_jsonb(r))
        FROM curb_policy_rules r
        WHERE r.curb_policy_id = cp.curb_policy_id
    ) AS rules,
    (
        SELECT jsonb_agg(to_jsonb(t))
        FROM curb_policy_time_spans t
        WHERE t.curb_policy_id = cp.curb_policy_id
    ) AS time_spans,
    (
        SELECT jsonb_agg(to_jsonb(rt))
        FROM curb_policy_rates rt
        WHERE rt.curb_policy_id = cp.curb_policy_id
    ) AS rates,
    (
        SELECT to_jsonb(c)
        FROM curb_policy_colors c
        WHERE c.color_id = cp.policy_color_id
    ) AS policy_color
FROM curb_policies cp;
