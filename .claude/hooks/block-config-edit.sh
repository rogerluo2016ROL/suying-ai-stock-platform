#!/usr/bin/env bash
# .claude/hooks/block-config-edit.sh
#
# PreToolUse hook (Edit | Write) —— 防 agent 改 lint/format 配置文件弱化规则。
# 依据 ECC scripts/hooks/config-protection.js:22-133（AGF bash 等价；ADR-017）。
#
# 哲学：纯防御，steer agent 修源码满足规则而非弱化门（改一行配置比改十处代码便宜，
# 是 agent 最常见的偷懒）。与 AGF「机制兜底」一致，不涉及人拍板。
#
# 行为：
#   - 文件不在保护清单 → exit 0（放行）
#   - 文件在保护清单 + 已存在 → exit 2（阻断「改 lint 配置」）
#   - 文件在保护清单 + 不存在 → exit 0（放行首次创建，允许新增配置）
#   - 无 jq / 无 file_path / basename 提不出 → exit 0（fail-open，AGF 哲学一致）
#
# 保护清单（裁剪为 AGF 实际栈）：ESLint / Prettier / Biome / Ruff / shellcheck / SwiftFormat。
# 不加 AGF 没用的 .stylelintrc。
#
# 进 AGF_HOOK_IMMUTABLE（agf-hook-flags.lib.sh）—— 安全防御，profile 不可降级。
# 注册：settings.json PreToolUse matcher Edit|Write（直接调，不包 guard —— 同 block-dangerous-bash）。

set -uo pipefail

INPUT="$(cat || true)"

# 无 jq → fail-open（不误杀，与 AGF hook 哲学一致）
command -v jq >/dev/null 2>&1 || exit 0

FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
# 无 file_path（非 Edit/Write 工具，或 payload shape 变）→ 放行
[ -z "$FILE_PATH" ] && exit 0

BASENAME=$(basename "$FILE_PATH" 2>/dev/null)
[ -z "$BASENAME" ] && exit 0

# 保护清单（basename 精确匹配）
is_protected() {
  case "$1" in
    .eslintrc|.eslintrc.js|.eslintrc.cjs|.eslintrc.mjs|.eslintrc.json|.eslintrc.yml|.eslintrc.yaml) return 0 ;;
    eslint.config.js|eslint.config.mjs|eslint.config.cjs|eslint.config.ts) return 0 ;;
    .prettierrc|.prettierrc.js|.prettierrc.cjs|.prettierrc.json|.prettierrc.yml|.prettierrc.yaml|.prettierrc.toml) return 0 ;;
    prettier.config.js|prettier.config.cjs|prettier.config.mjs) return 0 ;;
    biome.json|biome.jsonc) return 0 ;;
    ruff.toml|.ruff.toml) return 0 ;;
    .shellcheckrc) return 0 ;;
    .swiftformat|.swiftformat.yml|.swiftformat.yaml) return 0 ;;
    *) return 1 ;;
  esac
}

is_protected "$BASENAME" || exit 0   # 不在保护清单 → 放行

# 在保护清单：已存在 → 阻断；不存在 → 放行（首次创建）
if [[ -f "$FILE_PATH" ]]; then
  cat >&2 <<EOF
❌ [block-config-edit] 修改 lint/format 配置被阻断

文件: $FILE_PATH

agent 不可改 lint/format 配置（弱化规则偷懒），必须修源码满足现有规则。
（依据 ECC scripts/hooks/config-protection.js；ADR-017）

合法配置演进（如升级 ESLint major version 需改 config）由 product-lead / tech-lead
人工执行，不通过 agent 自动 Edit。
EOF
  exit 2
fi

exit 0   # 首次创建放行
