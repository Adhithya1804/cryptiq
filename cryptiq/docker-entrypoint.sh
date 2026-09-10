#!/bin/sh
# Backend container entrypoint.
#
#   1. (SQLite only) seed the database file from an optional read-only mount the
#      very first time, so a demo can start with the cached acceptance scan.
#   2. bring the schema to head with Alembic — the single source of schema truth.
#   3. hand off (exec) to the app process so it is PID 1 and receives SIGTERM
#      directly for a graceful shutdown.
#
# No secret is ever written here; configuration arrives only as environment
# variables injected at runtime.

set -eu

DATABASE_URL="${DATABASE_URL:-sqlite:///./cryptiq.db}"

case "$DATABASE_URL" in
  sqlite*)
    # Resolve the sqlite file path from the URL (sqlite:////data/cryptiq.db).
    db_path=$(printf '%s' "$DATABASE_URL" | sed -e 's#^sqlite:////#/#' -e 's#^sqlite:///##')
    seed_path="${SEED_DB_PATH:-/seed/cryptiq.db}"
    if [ ! -f "$db_path" ] && [ -f "$seed_path" ]; then
      echo "entrypoint: seeding $db_path from $seed_path"
      cp "$seed_path" "$db_path"
    fi
    ;;
esac

echo "entrypoint: applying database migrations (alembic upgrade head)"
alembic upgrade head

echo "entrypoint: starting: $*"
exec "$@"
