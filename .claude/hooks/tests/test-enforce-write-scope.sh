#!/bin/bash
# test-enforce-write-scope.sh — enforce-write-scope PreToolUse hook 回归
#
# 覆盖：
#   AC-1  主线程（无 agent_type）写任意 → 放行
#   AC-2  code-reviewer 写 docs/reviews/ → 放行
#   AC-3  code-reviewer 写源码 → block（核心：堵越界）
#   AC-4  backend-dev（无 boundary）写源码 → 放行
#   AC-5  qa-engineer 写 docs/qa/ → 放行
#   AC-6  qa-engineer 写源码 → block
#   AC-7  deploy-engineer 写 docs/deploy/ → 放行
#   AC-8  相对路径（docs/reviews/x.md）→ 放行
#   AC-9  未知角色（无 boundary）→ 放行（fail-open）
#   AC-13/14 Pool 实例名（<type>-<N>，ADR-001）剥后缀后仍受 boundary 约束

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$HOOK_DIR/enforce-write-scope.sh"
[ -x "$HOOK" ] || { echo "FAIL: hook 缺失/不可执行 $HOOK"; exit 1; }

PROJECT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"

PASS=0; FAIL=0; FAIL_LINES=()

# run <agent_type|""> <file_path> → exit code
run() {
  local at="$1" fp="$2" payload
  if [ -z "$at" ]; then
    payload=$(jq -nc --arg f "$fp" '{tool_input:{file_path:$f}}')
  else
    payload=$(jq -nc --arg a "$at" --arg f "$fp" '{agent_type:$a, tool_input:{file_path:$f}}')
  fi
  printf '%s' "$payload" | CLAUDE_PROJECT_DIR="$PROJECT_DIR" bash "$HOOK" >/dev/null 2>&1
  echo $?
}
check_block() {
  local desc="$1" at="$2" fp="$3" rc; rc=$(run "$at" "$fp")
  [ "$rc" -eq 2 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("$desc rc=$rc (want 2)"); }
}
check_pass() {
  local desc="$1" at="$2" fp="$3" rc; rc=$(run "$at" "$fp")
  [ "$rc" -eq 0 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("$desc rc=$rc (want 0)"); }
}
# run_raw <payload_json> → exit code（喂任意 payload，覆盖 teammate 等多字段形态）
run_raw() {
  printf '%s' "$1" | CLAUDE_PROJECT_DIR="$PROJECT_DIR" bash "$HOOK" >/dev/null 2>&1
  echo $?
}

# AC-1 主线程写源码 → 放行（PL 全路径）
check_pass "AC-1 main writes source"        ""                 "$PROJECT_DIR/backend/app/x.py"
# AC-2 reviewer 写 reviews → 放行
check_pass "AC-2 reviewer writes reviews"   "code-reviewer"    "$PROJECT_DIR/docs/reviews/x.md"
# AC-3 reviewer 写源码 → block（核心）
check_block "AC-3 reviewer writes src blocked" "code-reviewer"  "$PROJECT_DIR/backend/app/x.py"
# AC-4 dev 写源码 → 放行（无 boundary）
check_pass "AC-4 dev writes source"          "backend-dev"      "$PROJECT_DIR/backend/app/x.py"
# AC-5 qa 写 qa → 放行
check_pass "AC-5 qa writes qa dir"           "qa-engineer"      "$PROJECT_DIR/docs/qa/x.md"
# AC-6 qa 写源码 → block
check_block "AC-6 qa writes src blocked"     "qa-engineer"      "$PROJECT_DIR/backend/app/x.py"
# AC-7 deploy 写 deploy → 放行
check_pass "AC-7 deploy writes deploy"       "deploy-engineer"  "$PROJECT_DIR/docs/deploy/x.md"
# AC-8 相对路径 reviewer → 放行
check_pass "AC-8 reviewer relative path"     "code-reviewer"    "docs/reviews/x.md"
# AC-9 未知角色（无 boundary）→ 放行
check_pass "AC-9 unknown agent fail-open"    "some-unknown"     "$PROJECT_DIR/any/x"

# AC-10 C1: reviewer 用 .. 穿越 write_scope → 必须 block（堵 docs/reviews/../../backend）
check_block "AC-10 C1 traversal .. blocked" "code-reviewer" "$PROJECT_DIR/docs/reviews/../../backend/app/x.py"

# AC-11 C3: teammate 形态（.teammate.name 带 role，无 .agent_type）写源码 → block
rc=$(run_raw "$(jq -nc --arg f "$PROJECT_DIR/backend/app/x.py" \
  '{teammate:{name:"code-reviewer"}, tool_input:{file_path:$f}}')")
[ "$rc" -eq 2 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-11 C3 teammate scoped-role blocked rc=$rc (want 2)"); }

# AC-12 C3: 主线程（6 字段全空）仍放行 —— 防多字段提取误伤 PL 全路径
rc=$(run_raw "$(jq -nc --arg f "$PROJECT_DIR/backend/app/x.py" '{tool_input:{file_path:$f}}')")
[ "$rc" -eq 0 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-12 C3 main no-role pass rc=$rc (want 0)"); }

# AC-13 Pool 实例名（code-reviewer-2）写源码 → block（剥 -N 后缀查 boundary，堵 fan-out 形态 fail-open）
check_block "AC-13 pool instance writes src blocked" "code-reviewer-2" "$PROJECT_DIR/backend/app/x.py"
# AC-14 Pool 实例名写自己 write_scope → 放行
check_pass  "AC-14 pool instance writes reviews"     "code-reviewer-2" "$PROJECT_DIR/docs/reviews/x.md"

echo "=========================================="
echo "test-enforce-write-scope"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
[ $FAIL -gt 0 ] && { printf '  - %s\n' "${FAIL_LINES[@]}"; exit 1; }
exit 0
