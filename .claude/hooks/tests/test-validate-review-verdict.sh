#!/usr/bin/env bash
# test-validate-review-verdict.sh — validate-review-verdict.sh 单元测试
# 喂构造的 SubagentStop payload，断言 exit code（0=放行 / 2=拦）。lint-all 全量模式链调。
set -uo pipefail
HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/validate-review-verdict.sh"
command -v jq >/dev/null 2>&1 || { echo "需要 jq" >&2; exit 1; }
PASS=0; FAIL=0
EMPTY=$(mktemp -d)   # run() 用的空 CLAUDE_PROJECT_DIR：避免消息内无块时误读真实 docs/reviews/
trap 'rm -rf "$EMPTY"' EXIT

# 构造报告文本：summary + 末尾 agf-verdict 机读块（字段名用 AGF 词表 critical/warning/suggestion）
mkmsg() { printf '审查完成，详见报告。\n\n<!-- agf-verdict\nverdict: %s\ncritical: %s\nwarning: %s\nsuggestion: 0\n-->\n' "$1" "$2" "$3"; }
# 构造 payload JSON
payload() { jq -nc --arg r "$1" --arg m "$2" --argjson s "${3:-false}" '{agent_type:$r, last_assistant_message:$m, stop_hook_active:$s}'; }

run() { # name expected_exit payload —— 默认空 PROJECT_DIR（隔离文件兜底）
  local name="$1" exp="$2" got
  printf '%s' "$3" | CLAUDE_PROJECT_DIR="$EMPTY" bash "$HOOK" >/dev/null 2>&1; got=$?
  if [[ "$got" == "$exp" ]]; then echo "  ✅ $name (exit $got)"; PASS=$((PASS+1))
  else echo "  ❌ $name：期望 exit $exp，实际 $got" >&2; FAIL=$((FAIL+1)); fi
}

echo "=== validate-review-verdict.sh 单元测试 ==="
run "block + critical=1 → 放行"              0 "$(payload code-reviewer "$(mkmsg block 1 0)")"
run "approve + critical=1 → 拦【核心防线】"   2 "$(payload code-reviewer "$(mkmsg approve 1 0)")"
run "approve with changes + warn=2 → 放行"    0 "$(payload code-reviewer "$(mkmsg 'approve with changes' 0 2)")"
run "approve + warn=2 → 拦"                   2 "$(payload code-reviewer "$(mkmsg approve 0 2)")"
run "approve + clean → 放行"                  0 "$(payload code-reviewer "$(mkmsg approve 0 0)")"
run "block + clean → 拦"                      2 "$(payload code-reviewer "$(mkmsg block 0 0)")"
run "非 reviewer(backend-dev) → 放行(fail-open)" 0 "$(payload backend-dev "$(mkmsg approve 1 0)")"
run "pool 后缀 code-reviewer-2 → 拦"          2 "$(payload code-reviewer-2 "$(mkmsg approve 1 0)")"
run "miniapp-code-reviewer + crit → 拦"       2 "$(payload miniapp-code-reviewer "$(mkmsg approve 1 0)")"
run "miniapp important 别名 + approve → 拦"    2 "$(payload miniapp-code-reviewer "$(printf '审查完成。\n\n<!-- agf-verdict\nverdict: approve\ncritical: 0\nimportant: 3\nsuggestion: 0\n-->\n')")"
run "无 agf-verdict 块 → 放行(fail-open)"      0 "$(payload code-reviewer "审查完成，无结构化块。")"
run "loop guard(stop_hook_active=true) → 放行" 0 "$(payload code-reviewer "$(mkmsg approve 1 0)" true)"

# --- 文件兜底路径：块在 docs/reviews 报告文件而非消息里 ---
filecase() { # name expected_exit report_block_content message
  local name="$1" exp="$2" got TMPD; TMPD=$(mktemp -d); mkdir -p "$TMPD/docs/reviews"
  printf '%s' "$3" > "$TMPD/docs/reviews/feat-2026-05-30.md"
  printf '%s' "$(payload code-reviewer "$4")" | CLAUDE_PROJECT_DIR="$TMPD" bash "$HOOK" >/dev/null 2>&1; got=$?
  rm -rf "$TMPD"
  if [[ "$got" == "$exp" ]]; then echo "  ✅ $name (exit $got)"; PASS=$((PASS+1))
  else echo "  ❌ $name：期望 exit $exp，实际 $got" >&2; FAIL=$((FAIL+1)); fi
}
filecase "文件兜底：报告 critical=2 却 approve → 拦" 2 \
  "$(printf '# 报告\n\n<!-- agf-verdict\nverdict: approve\ncritical: 2\nwarning: 0\nsuggestion: 0\n-->\n')" "审查完成（消息内无块）。"
filecase "文件兜底：报告 critical=0 approve → 放行" 0 \
  "$(printf '# 报告\n\n<!-- agf-verdict\nverdict: approve\ncritical: 0\nwarning: 0\nsuggestion: 0\n-->\n')" "审查完成（消息内无块）。"

echo "─────────"
if (( FAIL )); then echo "❌ $FAIL 用例失败 / $PASS 通过" >&2; exit 1; fi
echo "✅ 全部 $PASS 用例通过"
