#!/bin/bash
set -euo pipefail

# Construct database URL from PG* env vars if EXEC_DATABASE_URL is not set.
# ECS injects PG* vars from Secrets Manager; this bridges them to our config.
if [ -z "${EXEC_DATABASE_URL:-}" ] && [ -n "${PGHOST:-}" ] && [ -n "${PGUSER:-}" ] && [ -n "${PGPASSWORD:-}" ]; then
    PGDATABASE="${PGDATABASE:-kt_execution}"
    PGPORT="${PGPORT:-5432}"
    export EXEC_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
fi

exec "$@"
