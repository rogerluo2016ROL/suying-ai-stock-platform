#!/usr/bin/env bash
# agf-task-hook.lib.sh — TaskCreated hook 公共提取/归因辅助（ADR-023 F1 去重）
#
# 去掉 validate-task-schema / gate-deploy-release-auth / gate-redo-fuse 三个 TaskCreated
# hook 各自手抄的「jq 多路径 description 提取」+「归因 sentinel grep」。payload shape
# 变更从 3 文件同步改 → 1 处改。
#
# source 用，不自执行。缺 jq → 提取函数返回空串，调用方按各自 fail-open（DESC 空 → exit 0）。

# agf_hook_field <json> <jq-path>...  首个非空路径值 → stdout；无 jq / 全空 → 空串
agf_hook_field() {
  local json="$1"; shift
  command -v jq >/dev/null 2>&1 || return 0
  local p val
  for p in "$@"; do
    val=$(printf '%s' "$json" | jq -r "$p // empty" 2>/dev/null || true)
    if [[ -n "$val" && "$val" != "null" ]]; then printf '%s' "$val"; return 0; fi
  done
}

# agf_task_desc <json>  → task description（标准 4 路径，payload shape 随事件变的兜底）
agf_task_desc() {
  agf_hook_field "$1" '.tool_input.description' '.task.description' '.description' '.tool_input.task.description'
}

# agf_has_attribution <text> <keyword>  归因行 `<keyword>:` 存在 → exit 0
#   容全角冒号「：」+ 行内（行首 / 缩进 / `- <kw>:` 列表项）
agf_has_attribution() {
  printf '%s' "$1" | grep -qE "(^|[[:space:]]|-)[[:space:]]*$2[:：]"
}
