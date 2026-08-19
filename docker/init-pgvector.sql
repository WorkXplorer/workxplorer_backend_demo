-- Runs automatically on first startup of the `db` container in
-- docker-compose.dev.yml (via /docker-entrypoint-initdb.d).
CREATE EXTENSION IF NOT EXISTS vector;
