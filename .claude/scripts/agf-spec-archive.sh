#!/usr/bin/env bash
# agf-spec-archive.sh — 薄包装，委托 agf-spec-archive.py（沿用 validate-verdict.sh → agf-verdict.py 先例）。
# delta merge 进活规格 + 归档 change。确定性 merge 在 .py 里（block 级 markdown 手术，bash 不可靠）。
#
# 用法: bash .claude/scripts/agf-spec-archive.sh <change> <YYYY-MM-DD> [--dry-run]
# 决策/契约: ADR-012 决策 3 + docs/changes/README.md。
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ 需要 python3" >&2
  exit 1
fi
exec python3 "$DIR/agf-spec-archive.py" "$@"
