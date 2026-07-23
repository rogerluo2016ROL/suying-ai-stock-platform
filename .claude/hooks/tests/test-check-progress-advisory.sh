#!/usr/bin/env bash
# test-check-progress-advisory.sh — 回归测试 check-progress-file.sh advisory 内容校验
# （superpowers.md §4 task-type ↔ Skills 匹配 advisory，ADR-011 advisory 风格）
#
# 跑法：bash .claude/hooks/tests/test-check-progress-advisory.sh
# 退出码：0 = 全部通过；1 = 至少一个 case 不符合预期
#
# 由 lint-all.sh / init-team.sh 自动发现并执行（find 递归 test-*.sh）。
#
# **测试构造纪律**：JSON 用单引号 + 字面 `\n`（合法 JSON 转义），喂 hook 用
# `printf '%s'`（禁用 echo——zsh echo 默认反转义会制造非法 JSON）。同
# test-gate-deploy-release-auth.sh 约定。

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
HOOK="$REPO_ROOT/.claude/hooks/check-progress-file.sh"

if [[ ! -x "$HOOK" ]]; then
  chmod +x "$HOOK" 2>/dev/null || true
fi

PASS=0
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ok()  { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

# run_progress_case <name> <expected_exit> <mode:has|nohas|clean> <pattern> <progress_content> [payload]
#
# mode:
#   has   — stdout+stderr merged 应含 pattern
#   nohas — 不应出现 pattern
#   clean — exit 0 且不应出现 "check-progress-file advisory"（advisory 全清）
run_progress_case() {
  local name="$1" exp_exit="$2" mode="$3" pat="$4" content="$5" payload="${6:-}"
  local prog_dir="$TMP/progress"
  local f="$prog_dir/backend-dev.md" out rc
  rm -rf "$prog_dir"; mkdir -p "$prog_dir"
  printf '%s\n' "$content" > "$f"
  out=$(cd "$TMP" && printf '%s' "$payload" | bash "$HOOK" 2>&1); rc=$?
  if [[ "$rc" -ne "$exp_exit" ]]; then
    bad "$name (exit expected=$exp_exit got=$rc) out=<<$out>>"
    return
  fi
  case "$mode" in
    has)
      echo "$out" | grep -qF "$pat" && ok "$name" || bad "$name (缺: $pat) out=<<$out>>"
      ;;
    nohas)
      echo "$out" | grep -qF "$pat" && bad "$name (不应出现: $pat) out=<<$out>>" || ok "$name"
      ;;
    clean)
      echo "$out" | grep -q "check-progress-file advisory" \
        && bad "$name (不应出现 advisory) out=<<$out>>" \
        || ok "$name"
      ;;
  esac
}

# Payload 没 team → hook 跳过 standby 检查直接走 progress 文件校验
PAYLOAD='{"teammate":{"name":"backend-dev"}}'

# 5 段齐全基线（用占位符 __STATE__ / __SKILLS__ 注入 case-specific 内容）
FULL_5SEC='## [task1] - 2026-07-07
**状态**: __STATE__
**Skills**: __SKILLS__

**SIT 证据**:
- [x] AC-1 ✅ done

**质量门**: lint ✅

**下一步**: 等 review'

inject() {
  # inject <template> <state> <skills>
  local tmpl="$1" st="$2" sk="$3"
  local out="${tmpl/__STATE__/$st}"
  out="${out/__SKILLS__/$sk}"
  printf '%s' "$out"
}

echo "=== check-progress-file.sh advisory 内容校验 test（superpowers.md §4）==="

# --- AC-1: feature 类 + Skills 段缺 test-driven-development → advisory + exit 0 ---
run_progress_case "feature缺TDD应advisory+exit0" 0 has "test-driven-development" \
  "$(inject "$FULL_5SEC" "新功能 - 实现登录" "agf-running-sit-tests")" \
  "$PAYLOAD"

# --- AC-2: complete 类 + Skills 段缺 verification-before-completion → advisory + exit 0 ---
run_progress_case "complete缺verification应advisory+exit0" 0 has "verification-before-completion" \
  "$(inject "$FULL_5SEC" "已完成" "agf-running-sit-tests")" \
  "$PAYLOAD"

# --- AC-3: feature + complete 两类并存且 Skills 含对应 skill → 无 advisory + exit 0 ---
run_progress_case "feature+complete齐全无advisory" 0 clean "" \
  "$(inject "$FULL_5SEC" "新功能 已完成" "superpowers:test-driven-development superpowers:verification-before-completion")" \
  "$PAYLOAD"

# --- AC-4: bugfix 关键词也命中 feature 类（变体覆盖）---
run_progress_case "bugfix命中feature类advisory" 0 has "test-driven-development" \
  "$(inject "$FULL_5SEC" "bugfix - 修登录回调" "agf-running-sit-tests")" \
  "$PAYLOAD"

# --- AC-5: 回归保护 — 5 段缺失仍 exit 2（hard gate 不被 advisory 削弱）---
run_progress_case "5段缺失仍exit2（回归保护）" 2 nohas "advisory" \
'## [task1] - 2026-07-07
**状态**: 新功能
**Skills**: agf-running-sit-tests' \
  "$PAYLOAD"

# --- AC-6: feature + complete 两类并存 + Skills 双缺 → 两条 advisory 各自独立判定 ---
run_progress_case "feature+complete双缺→TDD advisory" 0 has "test-driven-development" \
  "$(inject "$FULL_5SEC" "新功能 已完成" "agf-running-sit-tests")" \
  "$PAYLOAD"
run_progress_case "feature+complete双缺→verification advisory" 0 has "verification-before-completion" \
  "$(inject "$FULL_5SEC" "新功能 已完成" "agf-running-sit-tests")" \
  "$PAYLOAD"

# --- AC-7: feature 类关键词变体全覆盖（bug 修复 / 新特性 / feature，原仅测 bugfix）---
for kw in "bug 修复" "新特性" "feature"; do
  run_progress_case "关键词变体[$kw]命中feature类" 0 has "test-driven-development" \
    "$(inject "$FULL_5SEC" "$kw - 变体测试" "agf-running-sit-tests")" \
    "$PAYLOAD"
done

# --- AC-8: 「未完成」不应命中 complete 类（精确化：避免「完成」子串误匹配「未完成」）---
run_progress_case "未完成不命中complete类" 0 clean "" \
  "$(inject "$FULL_5SEC" "未完成 - 还在做" "agf-running-sit-tests")" \
  "$PAYLOAD"

echo
# 汇总行刻意不带 ✅（lint-all.sh grep '✅' 计数用例，带 ✅ 会把汇总行算进去 off-by-one）
if [[ $FAIL -eq 0 ]]; then
  echo "=> 全部 $PASS 个用例通过"
  exit 0
else
  echo "=> $FAIL 个用例失败 / $PASS 个通过"
  exit 1
fi
