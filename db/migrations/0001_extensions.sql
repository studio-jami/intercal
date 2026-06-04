-- 0001_extensions.sql
-- Enable required Postgres extensions.
-- Must run first; subsequent migrations depend on gen_random_uuid() and the vector type.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";       -- pgvector: vector, halfvec, hnsw indexes
