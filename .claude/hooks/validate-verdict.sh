#!/usr/bin/env bash
# validate-verdict.sh
#
# SubagentStop / TeammateIdle hook · 校验 reviewer / qa 的 verdict **必从原子事实推导**
# （ADR-003 → ADR-010 · 结构化 verdict 数据契约。原 validate-review-verdict.sh 泛化：
#  从「只守 code review」扩到「reviewer + qa 6 role」）。
#
# 本 hook 是**薄 bash 包装**：自己只做 role gating + 定位「本角色 session verdict 报告」（见下方
# 候选选择三重收紧），把「解析 frontmatter
# + 三套推导 + 比对」全部委托给 .claude/scripts/agf-verdict.py（单处推导 SSOT，spec §5/§7），
# 透传它的 exit code（0 一致 / 2 声明≠推导 或 QA 底线违规）。推导逻辑不再在本文件里。
#
# role → kind 映射：
#   code-reviewer | miniapp-code-reviewer | apple-code-reviewer → kind=review
#       报告目录 docs/reviews/，排除文件名含 _TEMPLATE / retro-
#   qa-engineer   | miniapp-qa-engineer   | apple-qa-engineer   → kind=qa
#       报告目录 docs/qa/，排除文件名含 _TEMPLATE / process-log / uat-cases
#   其余 role → fail-open 放行
#
# 推导规则（权威实现在 agf-verdict.py，spec §5）：
#   review · code：critical_count>0 → block；elif warning_count>0 → approve with changes；else approve
#   review · SIT ：sit_checks 任一 fail → Redo SIT；任一 concerns → Pass with concerns；else Pass
#   qa    · 底线：critical_defect_count>0 却非 Block / P0 未全 pass² 却 Promote → 违规
# 声明 verdict ≠ 推导结果（或 QA 底线违规）→ agf-verdict.py exit 2，本 hook 透传打回。
#
# 极保守 fail-open：非目标 role / 无 jq / 无 python3 / 无报告文件 / 解析异常 / stop_hook_active
# 一律 exit 0，绝不误杀；每个 fail-open 分支带一行 stderr WARN（说明因何放行，便于事后审计），
# 不影响 exit code。agf-verdict.py 自身对文件缺失 / yaml 异常 / 缺 PyYAML 也 fail-open（exit 0）。
# SubagentStop 而非 PostToolUse：后者对 subagent/Task 不触发（anthropics/claude-code#34692）；
# 同挂 TeammateIdle 兼顾 Agent Team teammate 形态。
#
# 注册：.claude/settings.json → hooks.SubagentStop / hooks.TeammateIdle（matcher: *，role gating 在本 hook 内）
# 词表 / 推导 SSOT：agf-verdict.py + .claude/standards/workflow.md §Verdict 词表 + review-checklist.md

set -uo pipefail
INPUT=$(cat || true)
# 无 jq → 放行（fail-open 各分支留一行 WARN 便于事后审计为何没拦；不改 exit code）
if ! command -v jq >/dev/null 2>&1; then
  echo "[validate-verdict] WARN — no jq, fail-open 放行" >&2
  exit 0
fi

# loop guard：已在 stop-hook 续跑中不再拦（最多自纠一轮）
if [[ "$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // empty' 2>/dev/null)" == "true" ]]; then
  echo "[validate-verdict] WARN — stop_hook_active loop guard, fail-open 放行（本轮不再复验）" >&2
  exit 0
fi

# role（多路径防御）+ 剥 pool 后缀 -N
ROLE=$(printf '%s' "$INPUT" | jq -r '
  [.agent_type, .subagent_type, .teammate.name, .agent.name, .name, .role]
  | map(select(. != null and . != "")) | .[0] // ""' 2>/dev/null)
BASE="$ROLE"; INST=""
[[ "$ROLE" =~ ^(.+)-([0-9]+)$ ]] && { BASE="${BASH_REMATCH[1]}"; INST="${BASH_REMATCH[2]}"; }

# role → kind + 报告目录 + verdict 键 + 文件名排除集
case "$BASE" in
  code-reviewer|miniapp-code-reviewer|apple-code-reviewer)
    KIND=review; SUBDIR=docs/reviews; VKEY=code_verdict;   EXCLUDES=("_TEMPLATE" "retro-") ;;
  qa-engineer|miniapp-qa-engineer|apple-qa-engineer)
    KIND=qa;     SUBDIR=docs/qa;      VKEY=report_verdict; EXCLUDES=("_TEMPLATE" "process-log" "uat-cases") ;;
  *)
    echo "[validate-verdict] WARN — role='${ROLE:-?}' 非 reviewer/qa, fail-open 放行" >&2
    exit 0 ;;
esac

# 定位本角色应校的报告（mtime 新→旧候选；ADR-003→ADR-010 兜底启发式的收紧版）：
#   1) 过滤排除集（_TEMPLATE / retro- 等）；
#   2) 只收「真 verdict 报告」——frontmatter 含本 kind 的 verdict 键（review=code_verdict / qa=report_verdict）。
#      legacy 散文报告 / audit / sweep / no-verify-log 等无 verdict 键的文件自然落选，根除
#      「非 verdict 报告被误当 verdict 报告、推导≠空声明而误阻断只读/panel reviewer」（idle 死锁）；
#   3) pool 实例（role 带 -N）优先取「自己的」报告 <feat>-r<N>-<date>.md，而非目录最新一份，
#      根除 head -1 在多实例并行时错取邻居报告导致的漏判/误判。
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
DIR="$PROJECT_DIR/$SUBDIR"
CANDS=()
while IFS= read -r f; do
  [[ -n "$f" && -f "$f" ]] || continue
  base=$(basename "$f")
  skip=0
  for ex in "${EXCLUDES[@]}"; do
    [[ "$base" == *"$ex"* ]] && { skip=1; break; }
  done
  (( skip )) && continue
  # 显式标注为非 gating 报告（report_type ∉ {空, code-review, qa-report}）→ 跳过。
  # legacy 对抗性 sweep / audit、no-verify-log 等即使含 code_verdict 也不应阻断当前 reviewer。
  rt=$(grep -m1 -E "^report_type:" "$f" 2>/dev/null | sed -E 's/^report_type:[[:space:]]*//; s/[[:space:]]*$//')
  case "$rt" in ""|code-review|qa-report) ;; *) continue ;; esac
  grep -qE "^${VKEY}:" "$f" || continue   # 仍无 verdict 键（legacy 散文报告等）→ 跳过
  CANDS+=("$f")
done < <(ls -t "$DIR"/*.md 2>/dev/null)

FILE=""
if [[ -n "$INST" && ${#CANDS[@]} -gt 0 ]]; then   # pool 实例：优先匹配自己的 -r<N>- 报告
  for f in "${CANDS[@]}"; do
    [[ "$(basename "$f")" =~ -r${INST}[-.] ]] && { FILE="$f"; break; }
  done
fi
[[ -z "$FILE" && ${#CANDS[@]} -gt 0 ]] && FILE="${CANDS[0]}"   # 非 pool / 无实例匹配 → 取最新 verdict 报告

if [[ -z "$FILE" ]]; then   # 本角色无对应 verdict 报告 → fail-open 放行
  echo "[validate-verdict] WARN — role='$BASE' 在 $SUBDIR/ 无本角色 verdict 报告（排除 ${EXCLUDES[*]}；需含 ${VKEY} 键）, fail-open 放行" >&2
  exit 0
fi

# 无 python3 → 放行（agf-verdict.py 跑不了）
if ! command -v python3 >/dev/null 2>&1; then
  echo "[validate-verdict] WARN — no python3, fail-open 放行" >&2
  exit 0
fi

# agf-verdict.py 与本 hook 同属 .claude/ 树（hook 在 .claude/hooks/，脚本在 .claude/scripts/），
# 按 hook 自身位置解析，而非 CLAUDE_PROJECT_DIR——后者只用于定位被审报告目录。
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERDICT_PY="$HOOK_DIR/../scripts/agf-verdict.py"
if [[ ! -f "$VERDICT_PY" ]]; then   # 脚本缺失 → 放行（防把 python "file not found"(exit 2) 误当 block）
  echo "[validate-verdict] WARN — agf-verdict.py 不存在($VERDICT_PY), fail-open 放行" >&2
  exit 0
fi

# 委托 agf-verdict.py 解析 + 推导 + 比对；透传其 exit（0 一致 / 2 不符或底线违规）
python3 "$VERDICT_PY" validate "$FILE" --kind="$KIND"
RC=$?
case "$RC" in
  0) exit 0 ;;   # 一致
  2) exit 2 ;;   # 阻断（agf-verdict.py 已把 BLOCK 明示到 stderr）
  *)  # 意外退出码（非 0/2）→ belt-and-suspenders fail-open，绝不误杀
    echo "[validate-verdict] WARN — agf-verdict.py 异常退出码 ${RC}（非 0/2）, fail-open 放行" >&2
    exit 0 ;;
esac
