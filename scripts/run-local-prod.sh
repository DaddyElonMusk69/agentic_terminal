#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8101}"
BACKEND_ENV_FILE="${BACKEND_ENV_FILE:-$BACKEND_DIR/.env.8101}"
FRONTEND_DIST_DIR="${FRONTEND_DIST_DIR:-$FRONTEND_DIR/dist}"
LOCAL_PROD_CAFFEINATE="${LOCAL_PROD_CAFFEINATE:-1}"

if [[ "$LOCAL_PROD_CAFFEINATE" != "0" && -z "${LOCAL_PROD_CAFFEINATED:-}" ]] && command -v caffeinate >/dev/null 2>&1; then
  export LOCAL_PROD_CAFFEINATED=1
  exec caffeinate -dimsu "$0" "$@"
fi

if [[ ! -f "$BACKEND_ENV_FILE" ]]; then
  echo "Missing backend env file: $BACKEND_ENV_FILE" >&2
  echo "Set BACKEND_ENV_FILE=/path/to/env or create backend/.env.8101." >&2
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Missing frontend/node_modules. Run: cd frontend && npm ci" >&2
  exit 1
fi

echo "Building frontend..."
(
  cd "$FRONTEND_DIR"
  npm run build
)

export BACKEND_FRONTEND_DIST_PATH="$FRONTEND_DIST_DIR"
export PYTHONPATH="$BACKEND_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

echo "Starting local production app at http://$BACKEND_HOST:$BACKEND_PORT"
echo "Using backend env file: $BACKEND_ENV_FILE"
echo "Database is not modified by this launcher."

cd "$BACKEND_DIR"
exec uvicorn \
  --env-file "$BACKEND_ENV_FILE" \
  --app-dir "$BACKEND_DIR/src" \
  app.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  --proxy-headers
