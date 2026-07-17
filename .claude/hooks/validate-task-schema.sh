#!/usr/bin/env bash
# validate-task-schema.sh
#
# TaskCreated hook — fires when a task is being created (via the TaskCreate tool).
# 目的：强制 product-lead 在跨 teammate 派单的 Task description 里写齐 6 段契约（hand-off 契约 + 上游产物传播），
#       缺任一段 → exit 2 阻断 TaskCreate 并把缺失项反馈给 lead 让其重试。
# 行为：
#   - description 缺失/解析失败 → exit 0 放过（不破坏现有流程，避免 false positive）
#   - 豁免：main session / 非 product-lead caller 的内部追踪任务（短文本 + 无任何 6 段 label hit） → exit 0
#   - description 存在且看起来是 dispatch（≥ 1 段 label 出现，或长度 ≥ 200 chars，或 caller = product-lead）→ 强制全 6 段
#   - 缺段 → exit 2 + stderr 列出缺失段
#   - 6 段齐 → exit 0
#
# 注册位置：.claude/settings.json → hooks.TaskCreated（官方专用事件；exit 2 阻止任务创建。
#           payload 字段位置随事件而变 → 下方 extract_first_nonempty 多路径防御式提取兜底）
# Schema 定义：.claude/agents/product-lead.md "Step 2：分配任务给执行层"

set -uo pipefail

INPUT=$(cat || true)

# 公共提取辅助（去重，见 agf-task-hook.lib.sh）；缺 lib / 缺 jq → fail-open exit 0
_HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$_HOOK_DIR/agf-task-hook.lib.sh" ] && source "$_HOOK_DIR/agf-task-hook.lib.sh"
command -v agf_task_desc >/dev/null 2>&1 || exit 0

DESC=$(agf_task_desc "$INPUT")

# 无法提取 description → 不阻断（保护现有流程；payload shape 变更或非 TaskCreate 事件不应误杀）
if [[ -z "${DESC:-}" ]]; then
  exit 0
fi

# 提取 caller agent name (尝试多路径)
CALLER=$(agf_hook_field "$INPUT" '.agent_name' '.caller_agent' '.subagent_type' '.tool_input.agent_name')

# === 豁免逻辑 ===
# 目的：让 main session / 非 product-lead 上下文中的内部任务追踪不被强制 6 段 schema。
# 触发"必须 6 段校验"的任一条件：
#   1) caller 显式是 product-lead（在 Agent Team 中派单）
#   2) description 已经包含至少 1 个 6 段 label（表明意图按 schema 写）
#   3) description 长度 ≥ 200 字符（dispatch 通常较长）
# 否则视为 main session 的轻量任务追踪，放行。

REQUIRED=(
  "任务描述"
  "任务类型"
  "上下文"
  "上游产物"
  "验收标准"
  "预期产物"
)

# 检查 description 是否已含 ≥ 1 段 label
PARTIAL_HITS=0
for KW in "${REQUIRED[@]}"; do
  if printf '%s' "$DESC" | grep -qF "$KW"; then
    PARTIAL_HITS=$((PARTIAL_HITS + 1))
  fi
done

DESC_LEN=${#DESC}

SHOULD_ENFORCE=0
if [[ "$CALLER" == "product-lead" ]]; then
  SHOULD_ENFORCE=1
elif [[ $PARTIAL_HITS -ge 1 ]]; then
  SHOULD_ENFORCE=1
elif [[ $DESC_LEN -ge 200 ]]; then
  SHOULD_ENFORCE=1
fi

# 豁免：轻量任务追踪 → 不阻断
if [[ $SHOULD_ENFORCE -eq 0 ]]; then
  exit 0
fi

# 必备 6 段（顺序无关，缺任一项即 fail）—— 与 product-lead.md Step 2 schema 严格对齐
# 注：REQUIRED 数组在上方豁免逻辑中已声明，此处复用。

MISSING=()
for KW in "${REQUIRED[@]}"; do
  if ! printf '%s' "$DESC" | grep -qF "$KW"; then
    MISSING+=("$KW")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "❌ [validate-task-schema] TaskCreate 被阻断 — Task description 缺少以下必备段落：" >&2
  for KW in "${MISSING[@]}"; do
    echo "   • $KW" >&2
  done
  echo "" >&2
  echo "请按 .claude/agents/product-lead.md 'Step 2：分配任务给执行层' 的 6 段 schema 补全后重试。" >&2
  echo "Schema：任务描述 / 任务类型 / 上下文 / 上游产物 / 验收标准 / 预期产物" >&2
  exit 2
fi

exit 0
