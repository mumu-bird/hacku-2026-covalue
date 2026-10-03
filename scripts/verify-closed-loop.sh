#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p tmp/closed-loop artifacts/browser/closed-loop
run_dir=$(mktemp -d "$PWD/tmp/closed-loop/run.XXXXXX")
test_port=${HOURLINK_TEST_PORT:-8001}
export HOURLINK_TEST_URL="http://127.0.0.1:$test_port"
export HOURLINK_TEST_DATA="$run_dir/data"
if curl --silent --fail --max-time 1 "$HOURLINK_TEST_URL/api/v1/health" >/dev/null; then
  echo "Test port $test_port is occupied; choose HOURLINK_TEST_PORT or stop its test server." >&2
  exit 1
fi
uv sync --locked
if [[ ! -d frontend/node_modules ]]; then (cd frontend && npm ci); fi
uv run ruff check backend scripts/reset.py scripts/audit_closed_loop.py scripts/mechanism_experiments.py
uv run pytest -q | tee artifacts/browser/closed-loop/pytest.log
(cd frontend && npm run build) | tee artifacts/browser/closed-loop/build.log
HOURLINK_DATA_DIR="$HOURLINK_TEST_DATA" DEMO_MODE=true uv run uvicorn backend.app.main:app --host 127.0.0.1 --port "$test_port" --log-level warning > "$run_dir/server.log" 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT
ready=false
for attempt in {1..30}; do
  if curl --silent --fail --max-time 1 "$HOURLINK_TEST_URL/api/v1/health" > artifacts/browser/closed-loop/health.json; then ready=true; break; fi
  if ! kill -0 "$server_pid" 2>/dev/null; then cat "$run_dir/server.log" >&2; exit 1; fi
  sleep 0.2
done
if [[ "$ready" != true ]]; then cat "$run_dir/server.log" >&2; exit 1; fi
unset HOURLINK_SCENARIO
HOURLINK_UI_URL="$HOURLINK_TEST_URL" node scripts/ui-review.cjs | tee artifacts/browser/closed-loop/ui-review.log
node scripts/closed-loop-check.cjs | tee artifacts/browser/closed-loop/browser.log
uv run python -m scripts.audit_closed_loop | tee artifacts/browser/closed-loop/audit.log
uv run python -m scripts.mechanism_experiments | tee artifacts/browser/closed-loop/mechanism.log
