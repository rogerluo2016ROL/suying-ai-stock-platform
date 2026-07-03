#!/usr/bin/env bash
# session-start-context.sh
#
# SessionStart hook —— 三个职责：
#   1) source=resume|compact 且 progress/ 有进行中底稿 → 注入「团队态恢复」提示
#      （compaction/resume 后帮 PL lead 找回 teammate 进度；in-process teammate 不随
#       /resume 恢复、需重新 spawn —— 见 agent-teams 已知限制）
#   1b) source=resume|compact 且能定位本 session 的 task list（~/.claude/tasks/<session_id>/，
#       与 agf-tasks.sh 同数据源）→ 追加一行 pending task 汇总（≤ 3 条摘要）；
#       任何环节失败（无 jq / 无目录 / JSON 异常）静默跳过，绝不阻断
#   2) source=startup|resume → 设 session 标题（git 分支名，fallback cwd 目录名）
#      （clear/compact 下 sessionTitle 被官方忽略，故不设）
# 永远 exit 0（绝不阻断 session 启动）。
#
# 注册位置：.claude/settings.json → hooks.SessionStart
# 设计依据：PreCompact 的 stdout 仅副作用、不注入压缩后上下文；SessionStart 在
#           source=compact 时触发且 stdout/additionalContext 注入上下文 —— 故恢复
#           提示走本 hook 而非 PreCompact。
# 参考：https://code.claude.com/docs/en/hooks（SessionStart additionalContext / sessionTitle / source）

set -uo pipefail

INPUT=$(cat || true)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

SOURCE=""
if command -v jq >/dev/null 2>&1; then
  SOURCE=$(printf '%s' "$INPUT" | jq -r '.source // empty' 2>/dev/null || echo "")
fi

ADDITIONAL=""
TITLE=""

# 1) 团队态恢复提示（仅 resume / compact，且确有进行中 progress 底稿）
if [[ "$SOURCE" == "resume" || "$SOURCE" == "compact" ]]; then
  if ls "$PROJECT_DIR"/progress/*.md >/dev/null 2>&1 && \
     ls "$PROJECT_DIR"/progress/*.md 2>/dev/null | grep -qvE '/(README|\.gitkeep)'; then
    ADDITIONAL='[团队态恢复] progress/ 有进行中的角色底稿。若你是 PL lead，请：① 重读 progress/<role>.md 恢复各 teammate 进度；② 跑 `bash .claude/scripts/agf-tasks.sh` 查 task list；③ 注意 in-process teammate 不随 /resume 恢复，缺失的需重新 spawn。'
  fi
fi

# 1b) pending task 汇总（仅 resume / compact；best-effort，全程 fail-open）
#     数据源同 .claude/scripts/agf-tasks.sh：~/.claude/tasks/<list-id>/*.json，
#     list-id 默认 = session_id（team 场景 task list 不挂在 session id 下 → 找不到即跳过）
if [[ "$SOURCE" == "resume" || "$SOURCE" == "compact" ]] && command -v jq >/dev/null 2>&1; then
  SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || echo "")
  TASK_DIR="${HOME}/.claude/tasks/${SESSION_ID}"
  if [[ -n "$SESSION_ID" && -d "$TASK_DIR" ]] && ls "$TASK_DIR"/*.json >/dev/null 2>&1; then
    # 单次 jq 扫全目录：每个 pending task 输出 "<id>: <subject 或 description 首行>"
    PENDING=$(jq -r 'select(.status == "pending")
      | "\(.id): \(.subject // (.description | split("\n")[0]) // "?")"' \
      "$TASK_DIR"/*.json 2>/dev/null || true)
    if [[ -n "$PENDING" ]]; then
      PENDING_N=$(printf '%s\n' "$PENDING" | grep -c . || true)
      # BSD paste -d 只认单字节分隔符 → 用 ASCII ';'
      PENDING_TOP=$(printf '%s\n' "$PENDING" | head -3 | cut -c1-60 | paste -sd ';' - 2>/dev/null || true)
      TASK_LINE="[task list] pending task ${PENDING_N} 个：${PENDING_TOP}（详情跑 bash .claude/scripts/agf-tasks.sh）"
      if [[ -n "$ADDITIONAL" ]]; then
        ADDITIONAL="${ADDITIONAL}
${TASK_LINE}"
      else
        ADDITIONAL="$TASK_LINE"
      fi
    fi
  fi
fi

# 2) session 标题（仅 startup / resume）
if [[ "$SOURCE" == "startup" || "$SOURCE" == "resume" ]]; then
  TITLE=$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
  [[ -z "$TITLE" || "$TITLE" == "HEAD" ]] && TITLE=$(basename "$PROJECT_DIR" 2>/dev/null || echo "")
fi

# 无任何输出需求 → 静默放行
if [[ -z "$ADDITIONAL" && -z "$TITLE" ]]; then
  exit 0
fi

# 构造 JSON 输出（需 jq 合并 context + title）；无 jq 则降级为纯 stdout 注入 context（放弃 title）
if command -v jq >/dev/null 2>&1; then
  jq -n \
    --arg ctx "$ADDITIONAL" \
    --arg title "$TITLE" \
    '{hookSpecificOutput: ({hookEventName: "SessionStart"}
       + (if $ctx   != "" then {additionalContext: $ctx} else {} end)
       + (if $title != "" then {sessionTitle: $title} else {} end))}'
else
  [[ -n "$ADDITIONAL" ]] && printf '%s\n' "$ADDITIONAL"
fi

exit 0
