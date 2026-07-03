#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-docker/.env.lark-bot}"
PORT="${SCREENER_PORT:-18001}"
PG_URL="${KRONOS_PG_URL:-postgresql://kronos:kronos@localhost:6432/kronos}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing env file: $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

export KRONOS_PG_URL="$PG_URL"
export SCREENER_PORT="$PORT"

echo "starting screener-service on :$PORT"
python3 -m uvicorn app.main:app \
  --app-dir services/screener-service \
  --host 0.0.0.0 \
  --port "$PORT" &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" "$BRIDGE_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "waiting for screener-service health"
for _ in {1..60}; do
  if curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null; then
    break
  fi
  sleep 1
done

echo "starting lark event bridge"
python3 tools/lark_event_bridge.py \
  --endpoint "http://127.0.0.1:$PORT/api/v1/lark/events" &
BRIDGE_PID=$!

echo "lark bot stack is running"
echo "commands: /秋神午后, /毕师傅硬核科技"
wait
