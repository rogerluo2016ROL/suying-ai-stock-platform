#!/bin/bash
# test-agf-next-instance.sh — agf-next-instance N 算法 + A-F2 pool 上限校验回归
#
# 覆盖：
#   AC-1  deploy-engineer 首次（无实例, pool=1）→ NEXT_N=1
#   AC-2  deploy-engineer 已有 -1 → exit 2（pool=1 超限，堵 fan-out）
#   AC-3  backend-dev（pool=5）已有 -1/-2 → NEXT_N=3
#   AC-4  backend-dev 已有 -1..-5 → exit 2（超 pool=5）
#   AC-5  未知角色（无 pool.limit）→ fail-open（输出 1）
#   AC-6  feature slug 含 -r（auth-router）不误匹配 N 算法（F-13 实证 + 回归守）

set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")/../../.." && pwd)/.claude/scripts/agf-next-instance.sh"
[ -x "$SCRIPT" ] || { echo "FAIL: script 缺失 $SCRIPT"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0; FAIL_LINES=()

# AC-1 deploy-engineer 首次（pool=1，无实例）→ NEXT_N=1
mkdir -p "$TMP/progress"
cd "$TMP"
out=$(bash "$SCRIPT" deploy-engineer 2>/dev/null); rc=$?
[ "$rc" -eq 0 ] && [ "$out" = "1" ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-1 deploy 首次 rc=$rc out=$out (want rc=0 out=1)"); }

# AC-2 deploy-engineer 已有 -1 → exit 2（pool=1 超限）
touch "$TMP/progress/deploy-engineer-1.md"
out=$(bash "$SCRIPT" deploy-engineer 2>&1); rc=$?
[ "$rc" -eq 2 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-2 deploy 超限 rc=$rc (want 2) out=$out"); }

# AC-3 backend-dev（pool=5）已有 -1/-2 → NEXT_N=3
touch "$TMP/progress/backend-dev-1.md" "$TMP/progress/backend-dev-2.md"
out=$(bash "$SCRIPT" backend-dev 2>/dev/null); rc=$?
[ "$rc" -eq 0 ] && [ "$out" = "3" ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-3 backend N=3 rc=$rc out=$out"); }

# AC-4 backend-dev 已有 -1..-5 → exit 2（超 pool=5）
touch "$TMP/progress/backend-dev-3.md" "$TMP/progress/backend-dev-4.md" "$TMP/progress/backend-dev-5.md"
out=$(bash "$SCRIPT" backend-dev 2>&1); rc=$?
[ "$rc" -eq 2 ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-4 backend 超限 rc=$rc (want 2)"); }

# AC-5 未知角色（roles.yaml 无此 type，无 pool.limit）→ fail-open 输出 1
out=$(bash "$SCRIPT" some-unknown-role 2>/dev/null); rc=$?
[ "$rc" -eq 0 ] && [ "$out" = "1" ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-5 未知角色 fail-open rc=$rc out=$out"); }

# AC-6 feature slug 含 -r（auth-router）不误匹配（F-13 回归守）
rm -f "$TMP/progress/"*.md
touch "$TMP/progress/code-reviewer-1.md"
mkdir -p "$TMP/docs/reviews"
touch "$TMP/docs/reviews/auth-router-r1-2026-07-03.md"
out=$(bash "$SCRIPT" code-reviewer auth-router 2>/dev/null); rc=$?
# code-reviewer pool=5；已有 -1（progress）+ r1（review）→ MAX_N=1 → NEXT_N=2 <=5 OK
[ "$rc" -eq 0 ] && [ "$out" = "2" ] && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); FAIL_LINES+=("AC-6 auth-router -r 不误匹配 rc=$rc out=$out (want 2)"); }

echo "=========================================="
echo "test-agf-next-instance"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
[ $FAIL -gt 0 ] && { printf '  - %s\n' "${FAIL_LINES[@]}"; exit 1; }
exit 0
