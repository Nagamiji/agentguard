#!/usr/bin/env bash
# Compact, deterministic product demo for a 60–90 second screen recording.
set -euo pipefail

cd "$(dirname "$0")/.."

REPORT="agentguard-launch-report.html"
LOCAL_DB_NAME=""
LOCAL_APP_ROLE=""

cleanup() {
  case "$LOCAL_DB_NAME" in
    agentguard_demo_*) dropdb --if-exists "$LOCAL_DB_NAME" >/dev/null 2>&1 || true ;;
  esac
  case "$LOCAL_APP_ROLE" in
    agentguard_demo_app_*) dropuser --if-exists "$LOCAL_APP_ROLE" >/dev/null 2>&1 || true ;;
  esac
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required for the recording demo." >&2
  exit 1
fi

if [ ! -x .venv/bin/agentguard ]; then
  echo "Run 'make install' before recording." >&2
  exit 1
fi

if [ -t 1 ]; then
  clear 2>/dev/null || true
  printf "AgentGuard launch demo starts in 3…\n"
  sleep 1
  printf "2…\n"
  sleep 1
  printf "1…\n\n"
  sleep 1
fi

if docker info >/dev/null 2>&1; then
  DEMO_RUNNER=scripted DEMO_REPORT="$REPORT" bash scripts/demo.sh
elif command -v psql >/dev/null 2>&1 && psql -Atqc "select 1" postgres >/dev/null 2>&1; then
  printf "Docker is unavailable; using a guarded temporary database in local PostgreSQL.\n"
  LOCAL_DB_NAME="agentguard_demo_$$"
  LOCAL_APP_ROLE="agentguard_demo_app_$$"
  LOCAL_APP_PASSWORD="agentguard-demo-only"

  createuser --no-superuser --no-createdb --no-createrole "$LOCAL_APP_ROLE"
  psql -v ON_ERROR_STOP=1 -d postgres \
    -c "ALTER ROLE $LOCAL_APP_ROLE PASSWORD '$LOCAL_APP_PASSWORD'" >/dev/null
  createdb "$LOCAL_DB_NAME"

  KEEL_MIGRATION_DATABASE_URL="postgresql+psycopg:///$LOCAL_DB_NAME" \
    .venv/bin/alembic upgrade head >/dev/null
  psql -v ON_ERROR_STOP=1 -d "$LOCAL_DB_NAME" \
    -c "GRANT USAGE ON SCHEMA public TO $LOCAL_APP_ROLE" \
    -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $LOCAL_APP_ROLE" \
    -c "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO $LOCAL_APP_ROLE" >/dev/null

  KEEL_DATABASE_URL="postgresql+psycopg://$LOCAL_APP_ROLE:$LOCAL_APP_PASSWORD@127.0.0.1:5432/$LOCAL_DB_NAME" \
  KEEL_MIGRATION_DATABASE_URL="postgresql+psycopg:///$LOCAL_DB_NAME" \
  KEEL_RATE_LIMIT_ENABLED=false \
  DEMO_SKIP_INFRA=1 \
  DEMO_SKIP_MIGRATIONS=1 \
  DEMO_RUNNER=scripted \
  DEMO_REPORT="$REPORT" \
    bash scripts/demo.sh
else
  echo "Start Docker Desktop or install PostgreSQL locally, then rerun 'make demo-record'." >&2
  exit 1
fi

printf "\nReport ready: %s\n" "$REPORT"
printf "Recording tip: show the BLOCKED verdict, exit code 20, then the evidence report.\n"

if [ "${DEMO_OPEN_REPORT:-1}" = "1" ]; then
  if command -v open >/dev/null 2>&1; then
    open "$REPORT"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$REPORT"
  fi
fi
