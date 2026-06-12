#!/usr/bin/env bash
# validate-review-verdict.sh
#
# SubagentStop / TeammateIdle hook · 校验 code-reviewer 的 verdict **必从 findings 推出**
# （全局优化 #1 / ADR-003 · 学 iLovePPT 的 verdict-from-scores 原则，用 AGF 自己的 severity 词表）。
#
# 原理：reviewer 在报告/完成回报末尾输出一个机读块（字段名 = AGF 报告段的 severity 词表）：
#   <!-- agf-verdict
#   verdict: block | approve with changes | approve
#   critical: <int>     # = 报告 ## Critical 段条目数
#   warning: <int>      # = 中间档条目数；miniapp-code-reviewer 用 `important:`（hook 两者都认）
#   suggestion: <int>   # = 最低档条目数（不参与推导，仅记录）
#   -->
# 推导规则（AGF verdict 词表）：
#   critical > 0           → block
#   else warning > 0       → approve with changes
#   else                   → approve
# 声明的 verdict ≠ 推导结果 → exit 2 打回（逼 reviewer 改 verdict 或复查 findings），堵的正是
# "有 Critical 却写 approve" 这个失败模式（本仓库 session 实际踩过：bug 拿到 validate pass 却有 Critical）。
#
# 极保守 fail-open：非 reviewer / 无块 / 没声明 verdict / 解析异常 / stop_hook_active 一律 exit 0，绝不误杀；
# 每个 fail-open 分支带一行 stderr WARN（说明因何放行，便于事后审计），不影响 exit code。
# SubagentStop 而非 PostToolUse：后者对 subagent/Task 不触发（anthropics/claude-code#34692）；
# 同挂 TeammateIdle 兼顾 Agent Team teammate 形态。
#
# 注册：.claude/settings.json → hooks.SubagentStop / hooks.TeammateIdle（matcher: code-reviewer / miniapp-code-reviewer / apple-code-reviewer）
# 词表 SSOT：.claude/standards/workflow.md §Verdict 词表 + review-checklist.md

set -uo pipefail
INPUT=$(cat || true)
# 无 jq → 放行（fail-open 各分支留一行 WARN 便于事后审计为何没拦；不改 exit code）
if ! command -v jq >/dev/null 2>&1; then
  echo "[validate-review-verdict] WARN — no jq, fail-open 放行" >&2
  exit 0
fi

# loop guard：已在 stop-hook 续跑中不再拦（最多自纠一轮）
if [[ "$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // empty' 2>/dev/null)" == "true" ]]; then
  echo "[validate-review-verdict] WARN — stop_hook_active loop guard, fail-open 放行（本轮不再复验）" >&2
  exit 0
fi

# role（多路径防御）+ 剥 pool 后缀 -N
ROLE=$(printf '%s' "$INPUT" | jq -r '
  [.agent_type, .subagent_type, .teammate.name, .agent.name, .name, .role]
  | map(select(. != null and . != "")) | .[0] // ""' 2>/dev/null)
BASE="$ROLE"; [[ "$ROLE" =~ ^(.+)-([0-9]+)$ ]] && BASE="${BASH_REMATCH[1]}"
case "$BASE" in
  code-reviewer|miniapp-code-reviewer|apple-code-reviewer) ;;
  *)
    echo "[validate-review-verdict] WARN — role='${ROLE:-?}' 非 reviewer, fail-open 放行" >&2
    exit 0 ;;
esac

# 取 agent 最后一段文本（优先内联，缺则读 transcript 末尾）
TEXT=$(printf '%s' "$INPUT" | jq -r '.last_assistant_message // empty' 2>/dev/null)
if [[ -z "$TEXT" ]]; then
  TP=$(printf '%s' "$INPUT" | jq -r '.agent_transcript_path // .transcript_path // empty' 2>/dev/null)
  [[ -n "$TP" && -f "$TP" ]] && TEXT=$(tail -80 "$TP" 2>/dev/null || true)
fi

# 抽最后一个 <!-- agf-verdict ... --> 块：先从 agent 末条消息，缺则从最新 review 报告文件兜底
# （reviewer 的块主要落在 docs/reviews/ 报告文件里，末条消息未必含 → 文件兜底是主力来源）
extract_block() {
  awk '
    /<!--[[:space:]]*agf-verdict/ { f=1; b=""; next }
    f && /-->/ { last=b; f=0; next }
    f { b = b $0 "\n" }
    END { printf "%s", last }'
}
BLOCK=$(printf '%s\n' "$TEXT" | extract_block)
if [[ -z "$BLOCK" ]]; then
  DIR="${CLAUDE_PROJECT_DIR:-.}"
  RPT=$(ls -t "$DIR"/docs/reviews/*.md 2>/dev/null | head -1)
  [[ -n "$RPT" && -f "$RPT" ]] && BLOCK=$(extract_block < "$RPT")
fi
if [[ -z "$BLOCK" ]]; then   # 两处都无块 → fail-open 放行
  echo "[validate-review-verdict] WARN — 无 agf-verdict 块（末条消息与最新 docs/reviews/ 报告都没有）, fail-open 放行" >&2
  exit 0
fi

getf() { printf '%s' "$BLOCK" | grep -iE "^[[:space:]]*$1[[:space:]]*:" | head -1 | sed -E "s/^[^:]*:[[:space:]]*//; s/[[:space:]]*$//"; }
DECL=$(getf verdict | tr 'A-Z' 'a-z')
CRIT=$(getf critical)
WARN=$(getf warning); [[ -z "$WARN" ]] && WARN=$(getf important)  # 中间档：code-reviewer 用 warning / miniapp 用 important
[[ "$CRIT" =~ ^[0-9]+$ ]] || CRIT=0   # 非数字 → 0（保守）
[[ "$WARN" =~ ^[0-9]+$ ]] || WARN=0
if [[ -z "$DECL" ]]; then             # 没声明 verdict → 放行
  echo "[validate-review-verdict] WARN — agf-verdict 块内未声明 verdict 字段, fail-open 放行" >&2
  exit 0
fi

# 推导
if   (( CRIT > 0 )); then EXPECT="block"
elif (( WARN > 0 )); then EXPECT="approve with changes"
else                     EXPECT="approve"
fi

if [[ "$DECL" != "$EXPECT" ]]; then
  cat >&2 <<EOF
❌ [validate-review-verdict] verdict 与 findings 不符 — 退出被阻断
   你声明 verdict: "$DECL"
   但 findings: critical=$CRIT warning=$WARN → 按规则应为 "$EXPECT"
   规则：critical>0 → block；否则 warning>0 → approve with changes；否则 approve。
   请改 verdict 或复查 findings（若把 Critical 误记成 Important 等），改完重出报告末尾的 agf-verdict 块。
EOF
  exit 2
fi
exit 0
