#!/usr/bin/env bash
# Start the backend in one of three modes.
#   api    — FastAPI only
#   worker — ARQ worker only
#   all    — API + worker in one container (free-tier demo hosting).
#            If either process exits, the container exits so the platform restarts it.
set -euo pipefail

MODE="${1:-api}"
PORT="${PORT:-8000}"

run_api() {
  uvicorn backend.api.main:app --host 0.0.0.0 --port "$PORT"
}

run_worker() {
  arq backend.queue.worker.WorkerSettings
}

case "$MODE" in
  api)
    exec uvicorn backend.api.main:app --host 0.0.0.0 --port "$PORT"
    ;;
  worker)
    exec arq backend.queue.worker.WorkerSettings
    ;;
  all)
    run_worker &
    WORKER_PID=$!
    run_api &
    API_PID=$!
    trap 'kill -TERM "$WORKER_PID" "$API_PID" 2>/dev/null' TERM INT
    # Exit as soon as either process stops.
    set +e
    wait -n "$WORKER_PID" "$API_PID"
    STATUS=$?
    kill -TERM "$WORKER_PID" "$API_PID" 2>/dev/null
    exit "$STATUS"
    ;;
  *)
    echo "usage: start.sh api|worker|all" >&2
    exit 2
    ;;
esac
