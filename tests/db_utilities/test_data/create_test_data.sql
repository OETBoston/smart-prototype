-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Create test_data schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS test_data;

-- Delete tables if they exist so they can be created from scratch each time
-- this is run.
DROP TABLE IF EXISTS test_data.test_read;
DROP TABLE IF EXISTS test_data.test_read_geo;
DROP TABLE IF EXISTS test_data.test_write;
DROP TABLE IF EXISTS test_data.test_write_geo;


-- Create test_read in test_data schema
CREATE TABLE IF NOT EXISTS test_data.test_read (
    id UUID PRIMARY KEY,
    integer_field INTEGER NOT NULL,
    string_field VARCHAR(255) NOT NULL,
    jsonb_field JSONB
);

-- Insert sample data
INSERT INTO test_data.test_read (id, integer_field, string_field, jsonb_field) VALUES
    ('550e8400-e29b-41d4-a716-446655440001', 42, 'Sample record 1', '{"key": "value", "count": 1, "active": true}'),
    ('550e8400-e29b-41d4-a716-446655440002', 100, 'Sample record 2', '{"name": "test", "data": [1, 2, 3], "nested": {"field": "value"}}'),
    ('550e8400-e29b-41d4-a716-446655440003', 255, 'Sample record 3', '{"status": "active", "priority": "high", "tags": ["production", "critical"]}'),
    ('550e8400-e29b-41d4-a716-446655440004', 1, 'Sample record 4', '{"empty": {}, "null_value": null}'),
    ('550e8400-e29b-41d4-a716-446655440005', 999, 'Sample record 5', '{"numeric": 3.14159, "boolean": false, "text": "hello world"}');
-- Create test_read_geo table with PostGIS geometry support
CREATE TABLE IF NOT EXISTS test_data.test_read_geo (
    id UUID PRIMARY KEY,
    integer_field INTEGER NOT NULL,
    string_field VARCHAR(255) NOT NULL,
    jsonb_field JSONB,
    geometry GEOMETRY(POINT, 4326)
);

-- Create spatial index on geometry column
CREATE INDEX IF NOT EXISTS idx_test_read_geo_geometry ON test_data.test_read_geo USING GIST (geometry);

-- Insert sample data with geometries
INSERT INTO test_data.test_read_geo (id, integer_field, string_field, jsonb_field, geometry) VALUES
    ('660e8400-e29b-41d4-a716-446655440001', 10, 'City Hall', '{"location": "Boston"}',   ST_GeomFromText('POINT(-71.05796081347341 42.36041637870849)', 4326)),
    ('660e8400-e29b-41d4-a716-446655440002', 20, 'Rivers Edge', '{"location": "Medford"}',    ST_GeomFromText('POINT(-71.0743071567904 42.41042214024287)', 4326)),
    ('660e8400-e29b-41d4-a716-446655440003', 30, 'MIT', '{"location": "Cambridge"}',  ST_GeomFromText('POINT(-71.0940387442943 42.3601268800116)', 4326)),
    ('660e8400-e29b-41d4-a716-446655440004', 40, 'US History', '{"location": "Boston"}', ST_GeomFromText('POINT(-71.05347673995645 42.36373998244562)', 4326)),
    ('660e8400-e29b-41d4-a716-446655440005', 50, 'Parking Clerk', '{"location": "Boston"}', ST_GeomFromText('POINT(-71.0575510602215 42.360579396935556)', 4326));

-- Create test_write table (empty) with same schema as test_read
CREATE TABLE IF NOT EXISTS test_data.test_write (
    id UUID PRIMARY KEY,
    integer_field INTEGER NOT NULL,
    string_field VARCHAR(255) NOT NULL,
    jsonb_field JSONB
);

-- Create test_write_geo table (empty) with same schema as test_read_geo
CREATE TABLE IF NOT EXISTS test_data.test_write_geo (
    id UUID PRIMARY KEY,
    integer_field INTEGER NOT NULL,
    string_field VARCHAR(255) NOT NULL,
    jsonb_field JSONB,
    geometry GEOMETRY(POINT, 4326)
);

-- Create spatial index on geometry column for test_write_geo
CREATE INDEX IF NOT EXISTS idx_test_write_geo_geometry ON test_data.test_write_geo USING GIST (geometry);