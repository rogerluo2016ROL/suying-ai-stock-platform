#!/usr/bin/env bash
# gate-deploy-release-auth.sh
#
# TaskCreated hook — 部署 / 发布门「用户授权」归因守门（补评审 A-F4）。
#
# 背景：CLAUDE.md 要求 product-lead 在派 deploy-engineer（UAT 部署）/ apple-release-engineer
#       （签名分发包）前**必须提示用户**获显式授权。但 PL 是主 session、用户的 /agf-deploy-uat
#       / /agf-apple-release 也在主 session 跑——hook 无法区分「PL 自行派单」与「用户 slash 触发」，
#       故**不可能做成硬门**（同 enforce-write-scope 的 agent_type 诚实 caveat 类别，见 ADR-018）。
#       本 hook 是**归因 + 审计 + 摩擦**层：强制派单 task 描述携带 `用户授权:` 归因行，缺则 exit 2，
#       把「PL 是否声称已获用户授权」从暗箱变明面 + 落进 task 历史（audit）+ 把 PL 引向正确入口。
#
# 行为（保守 fail-open，只在「明确是 deploy/release 派单且无归因」时拦）：
#   - description 缺失 / 解析失败 → exit 0（不破坏现有流程）
#   - description 不含 deploy-engineer / apple-release-engineer → exit 0（非 deploy/release 相关）
#   - description 已含 `用户授权:` 归因行 → exit 0（已 attributed）
#   - role 出现但只是「被引用」（如 qa 任务读 deploy-engineer 的 UAT 栈 URL），非派单 → exit 0（歧义 fail-open）
#   - 明确是 deploy/release 派单（任务类型段含 部署/发布/deploy/release/UAT/签名分发，或显式 `派 <role>`
#     / `<role> — initial task`）且无 `用户授权:` → exit 2 + stderr 指引
#
# 注册位置：.claude/settings.json → hooks.TaskCreated（与 validate-task-schema 并列，同 matcher 多 hook，
#           各自独立判定，任一 exit 2 阻断 TaskCreate）。属团队协调类（可降级，见 ADR-014 profile）。
# 诚实限制：PL 可伪造 `用户授权:` 行（与 enforce-write-scope 同限——主 session 全工具权限）。
#          本 hook 不假装是硬门；真正的 human-in-the-loop 由用户经 /agf-deploy-uat / /agf-apple-release
#          触发保证。决策 + 限制详 ADR-019。

set -uo pipefail

INPUT=$(cat || true)

# 公共提取/归因辅助（去重，见 agf-task-hook.lib.sh）；缺 lib / 缺 jq → fail-open exit 0
_HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$_HOOK_DIR/agf-task-hook.lib.sh" ] && source "$_HOOK_DIR/agf-task-hook.lib.sh"
command -v agf_task_desc >/dev/null 2>&1 || exit 0

DESC=$(agf_task_desc "$INPUT")

# 无 description → 放行
if [[ -z "${DESC:-}" ]]; then
  exit 0
fi

# 1) 非 deploy/release 相关 → 放行
if ! printf '%s' "$DESC" | grep -qE 'deploy-engineer|apple-release-engineer'; then
  exit 0
fi

# 2) 已携带「用户授权:」归因行 → 放行（已 attributed）
#    容忍全角冒号「用户授权：」+ 行内（行首 / 缩进 / `- 用户授权:` 列表项）
if agf_has_attribution "$DESC" 用户授权; then
  exit 0
fi

# 3) 判定是否「明确派单」（vs 仅被引用）。任一信号命中即视为派单：
#    a) 任务类型段值含 部署/发布/deploy/release/UAT 部署/签名分发
#    b) 显式派单短语：`派 deploy-engineer` / `派 apple-release-engineer` / `<role> — initial task`
DISPATCH=0

# 3a) 任务类型段值
#     匹配「任务类型:」或「任务类型：」后到行尾的值（容全角冒号 + 行内 / 独立行）
TYPE_LINE=$(printf '%s' "$DESC" | grep -oE '任务类型[[:space:]]*[:：][[:space:]]*[^[:cntrl:]]+' | head -1 || true)
if [[ -n "$TYPE_LINE" ]] && \
   printf '%s' "$TYPE_LINE" | grep -qE '部署|发布|deploy|release|UAT|签名分发|签名包|分发包'; then
  DISPATCH=1
fi

# 3b) 显式派单短语（容中英文 / 全角破折号 / 多空格）
if [[ "$DISPATCH" -eq 0 ]]; then
  if printf '%s' "$DESC" | grep -qE '派[[:space:]]+(deploy-engineer|apple-release-engineer)'; then
    DISPATCH=1
  elif printf '%s' "$DESC" | grep -qE '(deploy-engineer|apple-release-engineer)[[:space:]]*[—-][[:space:]]*initial[[:space:]]+task'; then
    DISPATCH=1
  fi
fi

# 4) role 出现但非明确派单（仅被引用）→ fail-open 放行
if [[ "$DISPATCH" -eq 0 ]]; then
  exit 0
fi

# 5) 明确派单 + 无归因 → 阻断
cat >&2 <<'EOF'
❌ [gate-deploy-release-auth] 部署 / 发布门 task 缺「用户授权」归因行 — TaskCreate 被阻断。

CLAUDE.md 要求：派 deploy-engineer（UAT 部署）/ apple-release-engineer（签名分发包）前，
product-lead 必须先获用户**显式授权**（用户跑 `/agf-deploy-uat <feature>` / `/agf-apple-release <feature>`，
或口头 / 渠道明确同意）。本 hook 强制把授权归因写进 task 描述（audit + 引向正确入口）。

在 task description 加一行（任一）：
  用户授权: /agf-deploy-uat <feature> 已触发
  用户授权: 用户口头确认部署 UAT（YYYY-MM-DD）
  用户授权: 用户在 <channel> 明确同意发布签名包

诚实限制（ADR-019）：本 hook 是归因 + 摩擦层，非硬门——PL 仍可伪造此行；真正的 human-in-the-loop
由用户经 /agf-deploy-uat / /agf-apple-release 触发保证。伪造归因 = 流程违规、追溯到人。
EOF
exit 2
