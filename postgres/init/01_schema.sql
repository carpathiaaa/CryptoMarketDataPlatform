-- Business schemas (layer access rules enforced by application convention)
CREATE SCHEMA IF NOT EXISTS raw;

CREATE SCHEMA IF NOT EXISTS staging;

CREATE SCHEMA IF NOT EXISTS marts;

CREATE SCHEMA IF NOT EXISTS meta;

-- pg_partman requires its own schema
CREATE SCHEMA IF NOT EXISTS partman;

CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman;