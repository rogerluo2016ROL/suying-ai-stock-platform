#!/usr/bin/env bash
# .claude/hooks/check-progress-file.sh
#
# Trigger: SubagentStop + TeammateIdle (Claude Code Agent Teams runtime)
# Purpose: 强制 Self-Reporting Pattern —— 执行层 teammate 在退出/idle 前必须已经
#          append 到 progress/<role>.md（含至少一个 markdown 二级标题 ## 任务条目），
#          否则 exit 2 阻断退出，提示按 .claude/standards/ac-lifecycle.md 流程补写。
#
# 强制对象（execution-layer roles）：
#   backend-dev / frontend-dev / ai-agent-dev / ml-engineer / miniapp-dev / apple-dev
#
# 豁免规则（exit 0 放行）：
#   - 当前 teammate 不在执行层强制名单（lead / reviewer / qa / designer / writer / analyst）
#   - 无法从 hook payload 提取出 teammate role（payload shape 变化时不误杀）
#   - 当前 team 的 task list 里没有任何任务分给该 role（standby 状态）
#   - progress/<role>.md 存在且含至少一条 ## 二级标题
#
# 阻断规则（exit 2 + stderr 提示）：
#   - 该 role 在执行层名单 + 有任务分配 + progress/<role>.md 不存在或无 ## 条目
#
# 注册位置：.claude/settings.json → hooks.SubagentStop / hooks.TeammateIdle
# 参考：https://code.claude.com/docs/en/agent-teams#enforce-quality-gates-with-hooks
# Pattern 定义：.claude/standards/ac-lifecycle.md "Self-Reporting Pattern"

set -uo pipefail

INPUT=$(cat || true)

# 执行层强制名单（与 .claude/standards/ac-lifecycle.md "强制对象" 对齐）
EXECUTION_ROLES=(
  "backend-dev"
  "frontend-dev"
  "ai-agent-dev"
  "ml-engineer"
  "miniapp-dev"
  "apple-dev"
)

# 防御式提取 role / teammate name（payload shape 因 hook 类型而异）
#
# Pool 模式（ADR-001）：实例名形如 `<base>-<N>`（如 `backend-dev-1`），
# 优先取 teammate.name / agent.name（实例完整名）作为 progress 文件名根据；
# subagent_type 仍是 `<base>`，作为 EXECUTION_ROLES 匹配依据（见下面 strip_instance_suffix）。
#
# Single jq call walks the entire fallback chain (was N separate forks per call).
extract_role() {
  if ! command -v jq >/dev/null 2>&1; then
    # jq 不可用 → 回退到 grep（粗暴但够用）
    printf '%s' "$INPUT" \
      | grep -oE '"(teammate|name|subagent_type|agent_name|role)"[[:space:]]*:[[:space:]]*"[^"]+"' \
      | head -1 \
      | sed -E 's/.*:[[:space:]]*"([^"]+)".*/\1/' \
      || echo ""
    return
  fi
  printf '%s' "$INPUT" | jq -r '
    [.teammate.name, .agent.name, .name,
     .subagent_type, .agent.subagent_type, .teammate.role, .role]
    | map(select(. != null and . != ""))
    | .[0] // ""
  ' 2>/dev/null
}

# Pool 实例名 → base type（如 `backend-dev-1` → `backend-dev`）
# 用于 EXECUTION_ROLES 名单匹配；若不带 `-<N>` 后缀则原样返回。
strip_instance_suffix() {
  local name="$1"
  # 仅当末尾是 `-数字` 才剥离（避免误伤角色名内的 `-`，如 `ai-agent-dev`）
  if [[ "$name" =~ ^(.+)-([0-9]+)$ ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  else
    printf '%s' "$name"
  fi
}

extract_team() {
  if ! command -v jq >/dev/null 2>&1; then
    printf '%s' "$INPUT" \
      | grep -oE '"team[Nn]ame"?[[:space:]]*:[[:space:]]*"[^"]+"' \
      | head -1 \
      | sed -E 's/.*:[[:space:]]*"([^"]+)".*/\1/' \
      || echo ""
    return
  fi
  # 兼容 .team 是 string（"team": "myteam"）和 object（"team": {"name": "myteam"}）两种 shape
  # 用 try/catch 防 jq 在 string 上调 .name 报 "Cannot index string"
  printf '%s' "$INPUT" | jq -r '
    [.teamName, (try .team.name catch null), (.team | strings)]
    | map(select(. != null and . != ""))
    | .[0] // ""
  ' 2>/dev/null
}

ROLE=$(extract_role)
TEAM=$(extract_team)

# 提不出 role → 不阻断（payload 变更或非 teammate 退出场景不应误杀）
[[ -z "$ROLE" ]] && exit 0

# ROLE 可能是单实例（`backend-dev`）或 pool 实例（`backend-dev-1`）。
# BASE_ROLE 用于 EXECUTION_ROLES 名单匹配；ROLE 本身用作 progress 文件名根据。
BASE_ROLE=$(strip_instance_suffix "$ROLE")

# base 不在执行层强制名单 → 不阻断
IN_LIST=0
for r in "${EXECUTION_ROLES[@]}"; do
  if [[ "$BASE_ROLE" == "$r" ]]; then
    IN_LIST=1
    break
  fi
done
[[ "$IN_LIST" -eq 0 ]] && exit 0

# Standby 豁免：
# 真实 Agent Teams task JSON schema 仅含 {id, subject, description, activeForm,
# status, blocks, blockedBy}——没有 assignee/teammate/to/owner 字段。R3 audit 实测
# 发现 R1 写的"按 role 名匹配 task"判定永远 false → hook 永远走 exit 0 死分支 →
# 5 段校验从未触发。此次 R3 修复改判定逻辑：
#
# - 若 team task list 完全没有任何 pending/in_progress task → 视为团队尚未开工 / 全部完成，放行
# - 否则进入下面的 progress 文件存在 + 5 段校验
#
# 这样 dev 在团队启动初期(没分到任务前) 不会被错误阻断,但只要团队有任何 active task,
# 执行层 role 退出/idle 时必须有合规的 progress 文件。
if [[ -n "$TEAM" ]]; then
  TASK_DIR="$HOME/.claude/tasks/$TEAM"
  if [[ -d "$TASK_DIR" ]]; then
    # 任何 task 处于 pending 或 in_progress 状态即认为团队 active
    ACTIVE_COUNT=0
    if command -v jq >/dev/null 2>&1; then
      ACTIVE_COUNT=$(jq -s '[.[] | select(.status == "pending" or .status == "in_progress")] | length' \
        "$TASK_DIR"/*.json 2>/dev/null || echo 0)
    else
      ACTIVE_COUNT=$(grep -lE '"status"[[:space:]]*:[[:space:]]*"(pending|in_progress)"' \
        "$TASK_DIR"/*.json 2>/dev/null | wc -l | tr -d ' ')
    fi
    # 团队没有 active task → 团队 standby，放行
    if [[ "${ACTIVE_COUNT:-0}" -eq 0 ]]; then
      exit 0
    fi
  fi
fi

# 检查 progress/<role>.md 是否存在 + 含 ≥1 个 ## 二级标题
PROGRESS_FILE="progress/$ROLE.md"

if [[ ! -f "$PROGRESS_FILE" ]]; then
  cat >&2 <<EOF
❌ [check-progress-file] 退出/idle 被阻断 — Self-Reporting Pattern 未遵守

Role: $ROLE
缺失文件: $PROGRESS_FILE

按 .claude/standards/ac-lifecycle.md "Self-Reporting Pattern" 节要求：
  1. 完成任务后必须先 append 一条完整条目到 progress/$ROLE.md
  2. 5 段精简格式: 状态 / Skills / SIT 证据（含 AC 自验勾选）/ 质量门 / 下一步
     （pass 单行，fail/blocked 才展开；详见 .claude/standards/ac-lifecycle.md "完整条目格式"）
  3. 写完 progress/ 后再 SendMessage 完成报告

如果你确实没领到任何任务（standby）— 通常 hook 已经豁免；若仍被拦截，
SendMessage 给 product-lead 说明并请求豁免授权。
EOF
  exit 2
fi

# 文件存在但无任何 ## 二级标题（空骨架不算数）
if ! grep -qE '^## ' "$PROGRESS_FILE" 2>/dev/null; then
  cat >&2 <<EOF
❌ [check-progress-file] 退出/idle 被阻断 — $PROGRESS_FILE 存在但无任务条目

按 .claude/standards/ac-lifecycle.md "完整条目格式" append 至少一条 (## 标题开头)
后再尝试退出/idle。空文件 / 仅占位说明不算有效条目。
EOF
  exit 2
fi

# 5 段格式校验：提最后一个 task 块（最后一个 ## 起始），检查 5 段是否齐
# 缺任一段 → exit 2 + 提示缺哪段
LAST_TASK_LINE=$(grep -n '^## ' "$PROGRESS_FILE" 2>/dev/null | tail -1 | cut -d: -f1)
LAST_BLOCK=$(tail -n +"$LAST_TASK_LINE" "$PROGRESS_FILE")

REQUIRED_SECTIONS=(
  "状态"
  "Skills"
  "SIT 证据"
  "质量门"
  "下一步"
)
MISSING_SECTIONS=()
for SEC in "${REQUIRED_SECTIONS[@]}"; do
  if ! printf '%s' "$LAST_BLOCK" | grep -qE "^\*\*${SEC}\*\*[:：]" 2>/dev/null; then
    MISSING_SECTIONS+=("$SEC")
  fi
done

if [[ ${#MISSING_SECTIONS[@]} -gt 0 ]]; then
  cat >&2 <<EOF
❌ [check-progress-file] 退出/idle 被阻断 — $PROGRESS_FILE 最后一条 task 条目缺 5 段格式

缺少段: $(IFS=,; echo "${MISSING_SECTIONS[*]}")

5 段必填: 状态 / Skills / SIT 证据 / 质量门 / 下一步
（行首格式 \`**段名**: 内容\`，详见 .claude/standards/ac-lifecycle.md "完整条目格式"）

如果该 task 在阻塞状态，"状态" 段填 "阻塞"，"下一步" 段写明阻塞点 + 已尝试 + 需要什么。
EOF
  exit 2
fi

exit 0
