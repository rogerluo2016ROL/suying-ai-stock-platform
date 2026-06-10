#!/usr/bin/env bash
# agf-tasks.sh — 查阅 Claude Code Agent Teams 原生 task list（人类可读视图）
#
# 用法:
#   bash .claude/scripts/agf-tasks.sh                          # 列出所有 team 概览
#   bash .claude/scripts/agf-tasks.sh <team>                   # 某 team 的 task 表
#   bash .claude/scripts/agf-tasks.sh <team> -s <status>       # 按 status 过滤
#   bash .claude/scripts/agf-tasks.sh <team> <id>              # 看单 task 完整描述
#
# Status: completed | in_progress | pending | blocked
#
# 数据源:
#   ~/.claude/teams/<name>/config.json  — team 元信息（成员、描述）
#   ~/.claude/tasks/<name>/*.json       — 每个 task 一个 JSON 文件
#
# 依赖: jq（macOS: brew install jq；本机已自带 /usr/bin/jq）

set -uo pipefail

TEAMS_DIR="${HOME}/.claude/teams"
TASKS_DIR="${HOME}/.claude/tasks"

# 颜色（仅 stdout 是 terminal 时启用）
if [[ -t 1 ]]; then
  R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[0;33m'; B=$'\033[0;34m'
  D=$'\033[0;90m'; N=$'\033[0m'
else
  R= G= Y= B= D= N=
fi

require_jq() {
  if ! command -v jq >/dev/null 2>&1; then
    echo "${R}error:${N} 需要 jq。安装：brew install jq" >&2
    exit 1
  fi
}

# 状态文字映射（带 emoji，对齐用 plain text）
status_label() {
  case "$1" in
    completed)   echo "✅ done   " ;;
    in_progress) echo "🔄 doing  " ;;
    pending)     echo "⏸  pending" ;;
    blocked)     echo "⛔ blocked" ;;
    "")          echo "?  ?      " ;;
    *)           echo "?  $1   " ;;
  esac
}

print_help() {
  # BSD sed (macOS) 不支持 \?，分两步走：先剥 "# "，再剥单独的 "#"
  sed -n '2,16p' "$0" | sed -e 's/^# //' -e 's/^#$//' >&2
}

# ----- 子命令 -----

list_teams() {
  if [[ ! -d "$TEAMS_DIR" ]]; then
    echo "${D}（无 ~/.claude/teams/ 目录，还没建过 agent team）${N}"
    return 0
  fi

  local teams=()
  for d in "$TEAMS_DIR"/*/; do
    [[ -d "$d" ]] || continue
    teams+=("$(basename "$d")")
  done

  if [[ ${#teams[@]} -eq 0 ]]; then
    echo "${D}（~/.claude/teams/ 为空）${N}"
    return 0
  fi

  echo "${B}=== Agent Teams 概览 ===${N}"
  echo

  for team in "${teams[@]}"; do
    local task_dir="$TASKS_DIR/$team"
    local total=0 done_n=0 doing_n=0 pending_n=0
    if [[ -d "$task_dir" ]]; then
      while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        total=$((total+1))
        local s
        s=$(jq -r '.status // ""' "$f" 2>/dev/null)
        case "$s" in
          completed)   done_n=$((done_n+1)) ;;
          in_progress) doing_n=$((doing_n+1)) ;;
          pending)     pending_n=$((pending_n+1)) ;;
        esac
      done < <(ls "$task_dir"/*.json 2>/dev/null)
    fi

    local desc="" members="?"
    if [[ -f "$TEAMS_DIR/$team/config.json" ]]; then
      desc=$(jq -r '.description // ""' "$TEAMS_DIR/$team/config.json" 2>/dev/null)
      members=$(jq -r '.members | length' "$TEAMS_DIR/$team/config.json" 2>/dev/null)
    fi

    echo "${B}● ${team}${N}  ${D}(${members} members)${N}"
    [[ -n "$desc" ]] && echo "  ${D}${desc}${N}"
    echo "  ${D}Tasks:${N} ${total} total · ${G}${done_n} done${N} · ${Y}${doing_n} doing${N} · ${pending_n} pending"
    echo
  done

  echo "${D}详情: bash $0 <team-name>${N}"
  echo "${D}过滤: bash $0 <team-name> -s pending${N}"
  echo "${D}单条: bash $0 <team-name> <id>${N}"
}

show_team() {
  local team="$1"
  local status_filter="${2:-}"
  local task_dir="$TASKS_DIR/$team"

  if [[ ! -d "$task_dir" ]]; then
    echo "${R}error:${N} team 不存在: $team" >&2
    echo >&2
    echo "${D}可用 teams:${N}" >&2
    list_teams >&2
    exit 1
  fi

  echo "${B}=== Team: $team ===${N}"

  # team 元信息
  if [[ -f "$TEAMS_DIR/$team/config.json" ]]; then
    local desc lead members
    desc=$(jq -r '.description // ""' "$TEAMS_DIR/$team/config.json")
    lead=$(jq -r '.leadAgentId // ""' "$TEAMS_DIR/$team/config.json")
    members=$(jq -r '.members | length' "$TEAMS_DIR/$team/config.json")
    [[ -n "$desc" ]] && echo "${D}${desc}${N}"
    echo "${D}Lead:${N} $lead   ${D}Members:${N} $members"
  fi

  if [[ -n "$status_filter" ]]; then
    echo "${D}Filter:${N} status=${status_filter}"
  fi
  echo

  # 收集并按 numeric id 排序
  local files
  files=$(ls "$task_dir"/*.json 2>/dev/null | sort -t/ -k7 -n)
  if [[ -z "$files" ]]; then
    echo "${D}（无 task）${N}"
    return 0
  fi

  local shown=0
  while IFS= read -r f; do
    local id status active_form subject blocked_by blocks
    id=$(jq -r '.id // ""' "$f")
    status=$(jq -r '.status // ""' "$f")
    # Agent Teams task JSON schema 不含 .owner 字段（R3 audit 实测确认）
    # 改用 .activeForm（"正在做 X" 现在进行时，in_progress 时最有信息量）
    active_form=$(jq -r '.activeForm // "-"' "$f")
    subject=$(jq -r '.subject // (.description | split("\n")[0]) // ""' "$f")
    blocked_by=$(jq -r '.blockedBy // [] | join(",")' "$f")
    blocks=$(jq -r '.blocks // [] | join(",")' "$f")

    if [[ -n "$status_filter" && "$status" != "$status_filter" ]]; then
      continue
    fi

    local label
    label=$(status_label "$status")

    # 主行：状态 + #id + subject（in_progress 时附 activeForm 灰字提示）
    if [[ "$status" == "in_progress" && "$active_form" != "-" ]]; then
      printf "%s  ${B}#%-4s${N} %s ${D}(%s)${N}\n" "$label" "$id" "$subject" "$active_form"
    else
      printf "%s  ${B}#%-4s${N} %s\n" "$label" "$id" "$subject"
    fi
    # 依赖关系（仅有依赖时显示）
    if [[ -n "$blocked_by" && "$blocked_by" != "" ]]; then
      echo "             ${D}↳ blocked by: ${blocked_by}${N}"
    fi
    if [[ -n "$blocks" && "$blocks" != "" ]]; then
      echo "             ${D}↳ blocks: ${blocks}${N}"
    fi
    shown=$((shown+1))
  done <<< "$files"

  echo
  echo "${D}显示 ${shown} 条 · 单 task 详情: bash $0 $team <id>${N}"
}

show_task() {
  local team="$1"
  local id="$2"
  local f="$TASKS_DIR/$team/${id}.json"

  if [[ ! -f "$f" ]]; then
    echo "${R}error:${N} task 不存在: $f" >&2
    exit 1
  fi

  echo "${B}=== Task #$id (${team}) ===${N}"
  echo "${D}File:${N} $f"
  echo

  jq -r '
    "Subject     : \(.subject // "(none)")",
    "Status      : \(.status // "(none)")",
    "ActiveForm  : \(.activeForm // "(none)")",
    "Blocks      : \(.blocks // [] | if length == 0 then "(none)" else join(", ") end)",
    "Blocked by  : \(.blockedBy // [] | if length == 0 then "(none)" else join(", ") end)",
    "",
    "Description :",
    "─────────────",
    .description // "(empty)"
  ' "$f"
}

# ----- 入口 -----

main() {
  require_jq

  case "${1:-}" in
    -h|--help)
      print_help
      exit 0
      ;;
    "")
      list_teams
      ;;
    *)
      local team="$1"
      shift

      local status_filter=""
      local task_id=""
      while [[ $# -gt 0 ]]; do
        case "$1" in
          -s|--status)
            status_filter="${2:-}"
            shift 2
            ;;
          *)
            task_id="$1"
            shift
            ;;
        esac
      done

      if [[ -n "$task_id" ]]; then
        show_task "$team" "$task_id"
      else
        show_team "$team" "$status_filter"
      fi
      ;;
  esac
}

main "$@"
