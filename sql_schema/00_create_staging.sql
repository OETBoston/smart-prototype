 -- This SQL script will create a new schema called `staging_next` and populate 
 -- it with empty tables.

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Create the schema and set the search path
DROP SCHEMA IF EXISTS staging_next CASCADE;
CREATE SCHEMA staging_next AUTHORIZATION "camsys-dev";

-- Set the search path FOR THIS SESSION
SET search_path TO public, staging_next;

-- Add relevant tables 
CREATE TABLE staging_next.asset_jobs (
	job_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	job_name varchar NOT NULL,
	job_description varchar NULL,
	CONSTRAINT asset_jobs_pkey PRIMARY KEY (job_id)
);


CREATE TABLE staging_next.blockface_jobs (
	job_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	job_name varchar NOT NULL,
	job_description varchar NULL,
	CONSTRAINT blockface_jobs_pkey PRIMARY KEY (job_id)
);


CREATE TABLE staging_next.curb_segment_jobs (
	job_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	job_name varchar NOT NULL,
	job_description varchar NULL,
	CONSTRAINT curb_segment_jobs_pkey PRIMARY KEY (job_id)
);


CREATE TABLE staging_next.data_sources (
	data_source_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	source_name varchar NOT NULL,
	CONSTRAINT data_sources_pkey PRIMARY KEY (data_source_id)
);


CREATE TABLE staging_next.policies (
	policy_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	policy_json jsonb NOT NULL,
	priority int4 NOT NULL,
	CONSTRAINT policies_pkey PRIMARY KEY (policy_id)
);


CREATE TABLE staging_next.policy_handling_jobs (
	job_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	job_name varchar NOT NULL,
	job_description varchar NULL,
	CONSTRAINT policy_handling_jobs_pkey PRIMARY KEY (job_id)
);


CREATE TABLE staging_next.sign_reader_jobs (
	job_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	job_name varchar NOT NULL,
	job_description varchar NULL,
	CONSTRAINT sign_reader_jobs_pkey PRIMARY KEY (job_id)
);


CREATE TABLE staging_next.asset_locations (
	asset_location_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	data_source_id uuid NOT NULL,
	job_id uuid NOT NULL,
	source_location_id varchar NULL,
	"location" public.geometry(point, 4326) NOT NULL,
	CONSTRAINT asset_locations_pkey PRIMARY KEY (asset_location_id),
	CONSTRAINT asset_locations_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES staging_next.data_sources(data_source_id),
	CONSTRAINT asset_locations_job_id_fkey FOREIGN KEY (job_id) REFERENCES staging_next.asset_jobs(job_id)
);
CREATE INDEX idx_asset_locations_data_source ON staging_next.asset_locations USING btree (data_source_id);
CREATE INDEX idx_asset_locations_geometry ON staging_next.asset_locations USING gist (location);
CREATE INDEX idx_asset_locations_job ON staging_next.asset_locations USING btree (job_id);


CREATE TABLE staging_next.curb_blockfaces (
	blockface_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	job_id uuid NOT NULL,
	geography public.geometry(linestring, 4326) NOT NULL,
	direction_of_flow varchar NOT NULL,
	CONSTRAINT curb_blockfaces_direction_of_flow_check CHECK (((direction_of_flow)::text = ANY ((ARRAY['forward'::character varying, 'reverse'::character varying])::text[]))),
	CONSTRAINT curb_blockfaces_pkey PRIMARY KEY (blockface_id),
	CONSTRAINT curb_blockfaces_job_id_fkey FOREIGN KEY (job_id) REFERENCES staging_next.blockface_jobs(job_id)
);
CREATE INDEX idx_curb_blockfaces_geometry ON staging_next.curb_blockfaces USING gist (geography);
CREATE INDEX idx_curb_blockfaces_job ON staging_next.curb_blockfaces USING btree (job_id);


CREATE TABLE staging_next.curb_segments (
	segment_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	blockface_id uuid NOT NULL,
	job_id uuid NOT NULL,
	run_date timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	geography public.geometry(linestring, 4326) NOT NULL,
	upstream_location uuid NULL,
	downstream_location uuid NULL,
	CONSTRAINT curb_segments_pkey PRIMARY KEY (segment_id),
	CONSTRAINT curb_segments_blockface_id_fkey FOREIGN KEY (blockface_id) REFERENCES staging_next.curb_blockfaces(blockface_id),
	CONSTRAINT curb_segments_downstream_location_fkey FOREIGN KEY (downstream_location) REFERENCES staging_next.asset_locations(asset_location_id),
	CONSTRAINT curb_segments_job_id_fkey FOREIGN KEY (job_id) REFERENCES staging_next.curb_segment_jobs(job_id),
	CONSTRAINT curb_segments_upstream_location_fkey FOREIGN KEY (upstream_location) REFERENCES staging_next.asset_locations(asset_location_id)
);
CREATE INDEX idx_curb_segments_blockface ON staging_next.curb_segments USING btree (blockface_id);
CREATE INDEX idx_curb_segments_downstream ON staging_next.curb_segments USING btree (downstream_location);
CREATE INDEX idx_curb_segments_geometry ON staging_next.curb_segments USING gist (geography);
CREATE INDEX idx_curb_segments_job ON staging_next.curb_segments USING btree (job_id);
CREATE INDEX idx_curb_segments_upstream ON staging_next.curb_segments USING btree (upstream_location);


CREATE TABLE staging_next.nonsign_features (
	feature_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	feature_location uuid NOT NULL,
	feature_type varchar NOT NULL,
	feature_description varchar NULL,
	CONSTRAINT nonsign_features_pkey PRIMARY KEY (feature_id),
	CONSTRAINT nonsign_features_feature_location_fkey FOREIGN KEY (feature_location) REFERENCES staging_next.asset_locations(asset_location_id)
);
CREATE INDEX idx_nonsign_features_location ON staging_next.nonsign_features USING btree (feature_location);
CREATE INDEX idx_nonsign_features_type ON staging_next.nonsign_features USING btree (feature_type);


CREATE TABLE staging_next.signs (
	sign_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	sign_location_id uuid NOT NULL,
	data_source_id uuid NOT NULL,
	job_id uuid NOT NULL,
	source_sign_id varchar NULL,
	added_date timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	sign_removed_date timestamp NULL,
	sign_type_code varchar NULL,
	sign_notes varchar NULL,
	CONSTRAINT signs_pkey PRIMARY KEY (sign_id),
	CONSTRAINT signs_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES staging_next.data_sources(data_source_id),
	CONSTRAINT signs_job_id_fkey FOREIGN KEY (job_id) REFERENCES staging_next.asset_jobs(job_id),
	CONSTRAINT signs_sign_location_id_fkey FOREIGN KEY (sign_location_id) REFERENCES staging_next.asset_locations(asset_location_id)
);
CREATE INDEX idx_signs_data_source ON staging_next.signs USING btree (data_source_id);
CREATE INDEX idx_signs_job ON staging_next.signs USING btree (job_id);
CREATE INDEX idx_signs_location ON staging_next.signs USING btree (sign_location_id);
CREATE INDEX idx_signs_removed_date ON staging_next.signs USING btree (sign_removed_date);


CREATE TABLE staging_next.curb_segment_policies (
	segment_id uuid NOT NULL,
	job_id uuid NOT NULL,
	policy_list jsonb DEFAULT '[]'::jsonb NULL,
	CONSTRAINT curb_segment_policies_pkey PRIMARY KEY (segment_id, job_id),
	CONSTRAINT fk_job FOREIGN KEY (job_id) REFERENCES staging_next.policy_handling_jobs(job_id) ON DELETE CASCADE,
	CONSTRAINT fk_segment FOREIGN KEY (segment_id) REFERENCES staging_next.curb_segments(segment_id) ON DELETE CASCADE
);


CREATE TABLE staging_next.images (
	image_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	sign_id uuid NOT NULL,
	data_source_id uuid NOT NULL,
	job_id uuid NOT NULL,
	uri varchar NOT NULL,
	image_date timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	source_image_id varchar NULL,
	CONSTRAINT images_pkey PRIMARY KEY (image_id),
	CONSTRAINT images_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES staging_next.data_sources(data_source_id),
	CONSTRAINT images_job_id_fkey FOREIGN KEY (job_id) REFERENCES staging_next.asset_jobs(job_id),
	CONSTRAINT images_sign_id_fkey FOREIGN KEY (sign_id) REFERENCES staging_next.signs(sign_id)
);
CREATE INDEX idx_images_data_source ON staging_next.images USING btree (data_source_id);
CREATE INDEX idx_images_job ON staging_next.images USING btree (job_id);
CREATE INDEX idx_images_sign ON staging_next.images USING btree (sign_id);


CREATE TABLE staging_next.sign_policies (
	sign_policy_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	sign_id uuid NOT NULL,
	job_id uuid NOT NULL,
	run_date timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	policy_json jsonb NOT NULL,
	policy_arrow varchar NULL,
	ai_confidence_score int4 NULL,
	ai_commentary varchar NULL,
	cds_override varchar NULL,
	cds_override_commentary varchar NULL,
	CONSTRAINT sign_policies_ai_confidence_score_check CHECK (((ai_confidence_score >= 0) AND (ai_confidence_score <= 100))),
	CONSTRAINT sign_policies_pkey PRIMARY KEY (sign_policy_id),
	CONSTRAINT sign_policies_policy_arrow_check CHECK (((policy_arrow)::text = ANY ((ARRAY['left'::character varying, 'right'::character varying, 'both'::character varying])::text[]))),
	CONSTRAINT sign_policies_job_id_fkey FOREIGN KEY (job_id) REFERENCES staging_next.sign_reader_jobs(job_id),
	CONSTRAINT sign_policies_sign_id_fkey FOREIGN KEY (sign_id) REFERENCES staging_next.signs(sign_id)
);
CREATE INDEX idx_sign_policies_job ON staging_next.sign_policies USING btree (job_id);
CREATE INDEX idx_sign_policies_json ON staging_next.sign_policies USING gin (policy_json);
CREATE INDEX idx_sign_policies_run_date ON staging_next.sign_policies USING btree (run_date);
CREATE INDEX idx_sign_policies_sign ON staging_next.sign_policies USING btree (sign_id);


-- Create a view for browsing policy segments

CREATE OR REPLACE VIEW staging_next.curb_segment_policies_geom
AS SELECT t1.segment_id,
    t1.job_id,
    t1.policy_list,
    t2.geography
   FROM staging_next.curb_segment_policies t1
     LEFT JOIN staging_next.curb_segments t2 ON t1.segment_id = t2.segment_id;


CREATE TABLE staging_next.parking_meter_jobs (
	job_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	job_name varchar NOT NULL,
	job_description varchar NULL,
	CONSTRAINT parking_meter_jobs_pkey PRIMARY KEY (job_id)
);

CREATE TABLE staging_next.meter_policies (
	meter_policy_id uuid DEFAULT uuid_generate_v4() NOT NULL,
	name VARCHAR NOT NULL,
	job_id uuid NOT NULL,
	run_date timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	policy_json jsonb NOT NULL,

	CONSTRAINT meter_policies_pkey PRIMARY KEY (meter_policy_id),
	CONSTRAINT meter_policies_job_id_fkey FOREIGN KEY (job_id) REFERENCES staging_next.parking_meter_jobs(job_id)
);
CREATE INDEX idx_meter_policies_job ON staging_next.meter_policies USING btree (job_id);
CREATE INDEX idx_meter_policies_json ON staging_next.meter_policies USING gin (policy_json);

CREATE TABLE staging_next.curb_segments_meter_zones (
	curb_segment_id uuid NOT NULL,
	meter_zone_id VARCHAR NOT NULL,

	CONSTRAINT curb_segments_meter_zones_segment_fkey FOREIGN KEY (curb_segment_id) REFERENCES staging_next.curb_segments(segment_id)
);
CREATE INDEX idx_curb_segments_meter_zones_segment ON staging_next.curb_segments_meter_zones USING btree (curb_segment_id);
CREATE INDEX idx_curb_segments_meter_zones_zone_id ON staging_next.curb_segments_meter_zones USING btree (meter_zone_id);

RESET search_path;