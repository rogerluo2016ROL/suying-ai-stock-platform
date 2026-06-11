#!/usr/bin/env bash
# .claude/hooks/teammate-keepalive.sh
#
# Trigger: TeammateIdle (Claude Code agent teams)
# Purpose: 当 teammate 即将进入 idle 状态时，检查共享 task list；
#          如仍有 pending 任务，阻止 idle 并提示该 teammate 主动 claim 或与 product-lead 协调交接，
#          避免 lead 误关 teammate 导致工作链路中断。
#
# Behavior:
#   - exit 0  允许 teammate 进入 idle
#   - exit 2  阻止 idle，stderr 内容作为 feedback 回送 teammate
#
# Conservative defaults: 任何无法判定的情况一律 exit 0，避免把 hook 变成 "永不停机" 陷阱。

set -euo pipefail

INPUT=$(cat)

# 提取 team name（不依赖 jq；兼容 teamName / team.name 两种字段写法）
TEAM_NAME=$(printf '%s' "$INPUT" \
  | grep -oE '"team[Nn]ame"[[:space:]]*:[[:space:]]*"[^"]+"' \
  | head -1 \
  | sed -E 's/.*:[[:space:]]*"([^"]+)".*/\1/' || true)

if [[ -z "$TEAM_NAME" ]]; then
  exit 0
fi

TASK_DIR="$HOME/.claude/tasks/$TEAM_NAME"
[[ -d "$TASK_DIR" ]] || exit 0

# 统计 status=="pending" 的任务文件数
PENDING_COUNT=$(grep -lE '"status"[[:space:]]*:[[:space:]]*"pending"' "$TASK_DIR"/*.json 2>/dev/null \
  | wc -l \
  | tr -d ' ')

if [[ "${PENDING_COUNT:-0}" -gt 0 ]]; then
  printf 'Team task list still has %s pending task(s). Before going idle: (1) check the shared task list, (2) claim an unblocked task you can handle, or (3) SendMessage to product-lead to hand off.\n' "$PENDING_COUNT" >&2
  exit 2
fi

exit 0
