
DROP SCHEMA IF EXISTS public_cds_previous CASCADE;
-- Move public_cds to public_cds_previous
ALTER SCHEMA public_cds RENAME TO public_cds_previous;
-- Move public_cds_next to public_cds
ALTER SCHEMA public_cds_next RENAME TO public_cds;

GRANT USAGE ON SCHEMA public_cds TO "cds-api";
GRANT SELECT ON ALL TABLES IN SCHEMA public_cds TO "cds-api";

ALTER DEFAULT PRIVILEGES IN SCHEMA public_cds
GRANT SELECT ON TABLES TO "cds-api";
