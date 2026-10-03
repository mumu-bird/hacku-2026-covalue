#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
uv sync --locked
if [[ ! -d frontend/node_modules ]]; then (cd frontend && npm ci); fi
(cd frontend && npm run build)
exec uv run uvicorn backend.app.main:app --host 127.0.0.1 --port "${HOURLINK_PORT:-8000}"
