#!/usr/bin/env bash
# tools/team-dashboard/start.sh — one-shot launcher for the team-dashboard.
#
# Usage:
#   ./start.sh           # dev mode:  uvicorn :8765 + Vite dev :5173
#   ./start.sh --prod    # prod mode: pnpm build → uvicorn :8765 only (FastAPI static-serves dist/)
#   ./start.sh -h        # help
#
# Behavior:
#   - Probes port :8765 first; if occupied, prints to stderr and exits 1 (AC-8 fail-fast).
#   - In dev mode, also probes :5173 and exits 1 if occupied.
#   - In dev mode, removes web/dist/ if present so backend doesn't auto-serve a stale build.
#   - On Ctrl-C, kills both child processes cleanly.
#
# This script is the ONLY entry point. The launcher (agf-team-start.sh) is not modified
# and never imports anything from here — AC-6 zero-touch.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="${HERE}/server"
WEB_DIR="${HERE}/web"
BACKEND_PORT=8765
FRONTEND_PORT=5173
MODE=dev

# ---------- arg parse ----------
usage() {
  cat <<'EOF'
Usage: ./start.sh [--prod] [-h]

  (no flag)   Dev mode:  uvicorn :8765 + Vite dev :5173
  --prod      Prod mode: pnpm build → uvicorn :8765 only
  -h, --help  Show this help

Open http://localhost:5173/ (dev) or http://localhost:8765/ (prod).

See ./README.md for full docs (ports, limitations, /clear behavior).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prod) MODE=prod; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# ---------- helpers ----------
red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

probe_port() {
  # macOS-friendly port probe via lsof (returns 0 if port is in use)
  local port=$1
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

fail_port() {
  local port=$1 svc=$2
  red "Error: port $port in use (needed by $svc)."
  red "Stop the existing process or free the port, then retry."
  red "(v1 is fail-fast by design — auto-find next free port is a v2 feature.)"
  exit 1
}

# ---------- dependency checks ----------
command -v lsof >/dev/null 2>&1 || { red "Need lsof (preinstalled on macOS)."; exit 1; }
command -v uvicorn >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1 \
  || { red "Need uvicorn or python3 (pip install -e $SERVER_DIR)."; exit 1; }

# ---------- port probes ----------
probe_port "$BACKEND_PORT" && fail_port "$BACKEND_PORT" "dashboard backend (uvicorn)"
if [[ "$MODE" == "dev" ]]; then
  probe_port "$FRONTEND_PORT" && fail_port "$FRONTEND_PORT" "Vite dev server"
fi

# ---------- dev/prod prep ----------
if [[ "$MODE" == "dev" ]]; then
  # Force dev semantics: backend won't auto-prod-serve a stale dist.
  if [[ -d "$WEB_DIR/dist" ]]; then
    bold "[dev] removing stale $WEB_DIR/dist/ so backend falls back to Vite redirect"
    rm -rf "$WEB_DIR/dist"
  fi
  command -v pnpm >/dev/null 2>&1 || { red "Need pnpm for dev mode (npm install -g pnpm)."; exit 1; }
else
  # Prod: ensure a fresh build exists.
  command -v pnpm >/dev/null 2>&1 || { red "Need pnpm to build dist/ (npm install -g pnpm)."; exit 1; }
  bold "[prod] running pnpm build → $WEB_DIR/dist/"
  ( cd "$WEB_DIR" && pnpm install --frozen-lockfile && pnpm build )
fi

# ---------- start backend ----------
bold "Starting uvicorn on :$BACKEND_PORT ..."
(
  cd "$SERVER_DIR"
  exec uvicorn main:app --port "$BACKEND_PORT" --host 127.0.0.1
) &
BACKEND_PID=$!

# ---------- start frontend (dev only) ----------
FRONTEND_PID=""
if [[ "$MODE" == "dev" ]]; then
  bold "Starting Vite dev on :$FRONTEND_PORT ..."
  ( cd "$WEB_DIR" && pnpm dev --port "$FRONTEND_PORT" ) &
  FRONTEND_PID=$!
fi

# ---------- cleanup trap ----------
cleanup() {
  echo ""
  bold "Shutting down ..."
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  kill "$BACKEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ---------- ready banner ----------
sleep 1
echo ""
green "==================================================================="
green "  Team Dashboard is up (mode: $MODE)"
green "  Backend SSE:  http://localhost:$BACKEND_PORT"
if [[ "$MODE" == "dev" ]]; then
  green "  Frontend SPA: http://localhost:$FRONTEND_PORT   ← open this"
else
  green "  Dashboard:    http://localhost:$BACKEND_PORT     ← open this"
fi
green "  Ctrl-C to stop both."
green "==================================================================="
echo ""

wait "$BACKEND_PID"
