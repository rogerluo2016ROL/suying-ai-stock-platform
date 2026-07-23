#!/bin/bash
# test-block-config-edit.sh — block-config-edit PreToolUse hook 回归
#
# 覆盖：
#   AC-1  已存在保护配置 → block (exit 2)
#   AC-2  首次创建保护配置（不存在）→ pass (exit 0)
#   AC-3  不在保护清单 → pass
#   AC-4  保护清单全覆盖（ESLint/Prettier/Biome/Ruff/shellcheck/SwiftFormat 各代表）
#   AC-5  无 file_path（非 Edit/Write）→ pass

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$HOOK_DIR/block-config-edit.sh"
[ -x "$HOOK" ] || { echo "FAIL: hook 缺失/不可执行 $HOOK"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CLAUDE_PROJECT_DIR="$TMP"

PASS=0; FAIL=0; FAIL_LINES=()

# run_hook <json_payload> → exit code
run_hook() {
  printf '%s' "$1" | bash "$HOOK" >/dev/null 2>&1
  echo $?
}
payload() { jq -nc --arg p "$1" '{tool_input: {file_path: $p}}'; }

# AC-1 已存在保护配置 → block
touch "$TMP/.eslintrc.json"
rc=$(run_hook "$(payload "$TMP/.eslintrc.json")")
[ "$rc" -eq 2 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-1 已存在 .eslintrc.json 应 block rc=$rc"); }

# AC-2 首次创建保护配置（不存在）→ pass
rc=$(run_hook "$(payload "$TMP/.prettierrc")")
[ "$rc" -eq 0 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-2 首次创建 .prettierrc 应 pass rc=$rc"); }

# AC-3 不在保护清单 → pass（已存在的非配置文件）
touch "$TMP/foo.js"
rc=$(run_hook "$(payload "$TMP/foo.js")")
[ "$rc" -eq 0 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-3 foo.js 应 pass rc=$rc"); }

# AC-4 保护清单全覆盖（各代表，已存在 → block）
for f in .eslintrc.cjs eslint.config.js .eslintrc.yml prettier.config.js biome.json biome.jsonc ruff.toml .ruff.toml .shellcheckrc .swiftformat .swiftformat.yml; do
  touch "$TMP/$f"
  rc=$(run_hook "$(payload "$TMP/$f")")
  [ "$rc" -eq 2 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-4 $f 应 block rc=$rc"); }
done

# AC-5 无 file_path（非 Edit/Write payload）→ pass
rc=$(run_hook '{"tool_input":{}}')
[ "$rc" -eq 0 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-5 无 file_path 应 pass rc=$rc"); }

echo "=========================================="
echo "test-block-config-edit"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
[ $FAIL -gt 0 ] && { printf '  - %s\n' "${FAIL_LINES[@]}"; exit 1; }
exit 0
