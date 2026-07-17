#!/usr/bin/env bash
# .claude/hooks/agf-hook-guard.sh
#
# 中央 hook guard 包装器 —— profile 运行时门控。仿 ECC run-with-flags.js:164-167
# （isHookEnabled → 不匹配 profile 则 exit 0 跳过），bash 等价物。
#
# Usage: agf-hook-guard.sh <hookId> <real-script-path>
#   读 stdin（hook payload）→ agf_hook_enabled 判 profile →
#     启用 → stdin 喂给 real-script，透传其 exit code
#     跳过 → exit 0（不执行 real-script；SessionStart 类降级即"不注入 context"）
#
# 安全边界（agf-hook-flags.lib.sh AGF_HOOK_IMMUTABLE）：四层防御 + validate-verdict
# 任何 profile 下都执行 —— 安全 SSOT 不可降级（ADR-014）。
#
# 注册示例（settings.json hooks.TeammateIdle）：
#   "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/agf-hook-guard.sh teammate-keepalive \"\$CLAUDE_PROJECT_DIR\"/.claude/hooks/teammate-keepalive.sh"
#
# fail-open：real-script 缺失 → exit 0 放行（绝不误杀，匹配 AGF hook 哲学）。

set -uo pipefail

HOOK_ID="${1:-}"
REAL_SCRIPT="${2:-}"

# 定位 lib（与 guard 同目录）
GUARD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=agf-hook-flags.lib.sh
source "$GUARD_DIR/agf-hook-flags.lib.sh"

# 读 stdin 一次（hook payload），用于透传给 real-script
INPUT="$(cat || true)"

# 判 profile
if ! agf_hook_enabled "$HOOK_ID"; then
  exit 0   # profile 不匹配 → 放行（不执行 real-script）
fi

# 启用 → 透传 stdin 给 real-script
if [[ -z "$REAL_SCRIPT" || ! -f "$REAL_SCRIPT" ]]; then
  echo "[agf-hook-guard] WARN — real-script 缺失: ${REAL_SCRIPT:-<empty>}, fail-open 放行" >&2
  exit 0
fi

printf '%s' "$INPUT" | bash "$REAL_SCRIPT"
exit $?
