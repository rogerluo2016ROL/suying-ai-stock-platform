#!/usr/bin/env bash
# .claude/scripts/check-superpowers-mapping.sh
#
# superpowers skill↔task-type 映射 drift 守门（防 sweep W1：hook advisory 硬编码的 skill
# 字面量与 superpowers.md §4 desync）。
#
# 检查：check-progress-file.sh 的 advisory 段若含 skill 字面量（test-driven-development /
# verification-before-completion），则 superpowers.md 必须也提及——否则未来改 superpowers
# 命名时 hook 会静默 desync。
#
# **advisory**：只 warning，不阻断（exit 0）。hook 无 advisory 字面量时 vacuous pass
# （PR #20 的 check-progress-file.sh 无 advisory；PR #18 merge 后激活）。
#
# 跑法：bash .claude/scripts/check-superpowers-mapping.sh（由 lint-all.sh advisory section 调）。

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd -P)" || exit 0
HOOK="$ROOT/.claude/hooks/check-progress-file.sh"
SUPER="$ROOT/.claude/standards/superpowers.md"
[ -f "$HOOK" ] && [ -f "$SUPER" ] || exit 0

# W1：hook advisory 硬编码的 skill 字面量
SKILLS=(test-driven-development verification-before-completion)

warnings=0
for sk in "${SKILLS[@]}"; do
  if grep -q "$sk" "$HOOK" 2>/dev/null && ! grep -q "$sk" "$SUPER" 2>/dev/null; then
    echo "  ⚠️ check-progress-file.sh advisory 含 '$sk' 但 superpowers.md 未提及 → drift 风险（W1）" >&2
    warnings=$((warnings+1))
  fi
done

if [ "$warnings" -gt 0 ]; then
  echo "⚠️ superpowers-mapping advisory：$warnings 处 drift（advisory，不阻断 lint）" >&2
else
  echo "✓ superpowers-mapping：hook advisory 字面量与 superpowers.md 一致"
fi
exit 0
