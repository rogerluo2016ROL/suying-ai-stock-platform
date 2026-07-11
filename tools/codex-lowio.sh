#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'USAGE'
Usage:
  bash tools/codex-lowio.sh du
  bash tools/codex-lowio.sh py [pytest args...]
  bash tools/codex-lowio.sh fe-test [vitest filters...]
  bash tools/codex-lowio.sh fe-sit [vitest filters...]
  bash tools/codex-lowio.sh fe-typecheck
  bash tools/codex-lowio.sh service-test [--core|SERVICE] [pytest args...]

These wrappers reduce local writes by disabling Python bytecode/cache writes,
running frontend tests serially, avoiding watch mode, and keeping output short.
USAGE
}

pytest_bin() {
  if [[ -x "$ROOT/.venv/bin/pytest" ]]; then
    printf '%s\n' "$ROOT/.venv/bin/pytest"
  elif [[ -x "$ROOT/backend/.venv/bin/pytest" ]]; then
    printf '%s\n' "$ROOT/backend/.venv/bin/pytest"
  else
    command -v pytest
  fi
}

cmd="${1:-}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "$cmd" in
  du)
    cd "$ROOT"
    du -sh \
      .codegraph .codex .Codex node_modules frontend/node_modules \
      .venv backend/.venv .pytest_cache backend/.pytest_cache \
      frontend/dist .playwright-cli .playwright-mcp .pnpm-store \
      outputs output Kronos 2>/dev/null | sort -h
    ;;
  py)
    cd "$ROOT"
    export PYTHONDONTWRITEBYTECODE=1
    export PYTEST_DISABLE_PLUGIN_AUTOLOAD="${PYTEST_DISABLE_PLUGIN_AUTOLOAD:-1}"
    "$(pytest_bin)" -p no:cacheprovider -p pytest_asyncio.plugin --tb=short -q "$@"
    ;;
  fe-test)
    cd "$ROOT/frontend"
    npx vitest run "$@" \
      --no-file-parallelism \
      --maxWorkers=1 \
      --reporter=dot \
      --silent=passed-only
    ;;
  fe-sit)
    cd "$ROOT/frontend"
    npx vitest run tests/sit/ "$@" \
      --no-file-parallelism \
      --maxWorkers=1 \
      --reporter=dot \
      --silent=passed-only
    ;;
  fe-typecheck)
    cd "$ROOT/frontend"
    npx tsc -b --noEmit --pretty false
    ;;
  service-test)
    cd "$ROOT"
    export PYTHONDONTWRITEBYTECODE=1
    python3 tools/run_service_tests.py "$@"
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    printf 'Unknown command: %s\n\n' "$cmd" >&2
    usage >&2
    exit 2
    ;;
esac
