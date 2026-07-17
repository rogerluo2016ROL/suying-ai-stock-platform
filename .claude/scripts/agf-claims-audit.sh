#!/usr/bin/env bash
# agf-claims-audit.sh — CLAUDE.md 治理声称 ↔ 现实 一致性门（对标 claude-code-harness
# rulecoverage 的 RuleOrphans/SelfauditOrphans 思想，但用 bash 落地并真正 wire 成硬门——
# harness 自己那套是 git-ignored、"never a judgment basis" 的 spike）。
#
# 消灭 AGF 自身的 "written ≠ working"：巨大的 CLAUDE.md「Tool Boundaries」声称一堆 hook/
# 脚本，但没人机器校验它们真的存在 + 真的注册。本门查三向：
#   A. 已注册 hook（settings.json）→ 磁盘脚本存在        [硬阻断：注册了却没文件]
#   B. CLAUDE.md 点名的 AGF 脚本（*.sh/*.py）→ 存在于仓库 [硬阻断：doc 点名幽灵脚本 / 改名漂移]
#   C. 已注册 hook → 在治理 doc 里有文档                  [advisory：注册了却没写进文档]
#
# 三态诚实（[known-limitations.md] + ADR）：本门只判 A/B 的**可机器确定**部分（存在性 +
# 注册性）；C 是 advisory 因为文档位置多样。强制强度声称是否诚实（hard-block vs advisory
# vs model-dependent）由 known-limitations.md 人工维护，非本门职责。
#
# 用法： bash .claude/scripts/agf-claims-audit.sh
# 退出码：0 = A+B 通过（C 仅告警）；2 = A 或 B 违规（硬阻断）
# 保守 fail-open：缺 jq / 缺 CLAUDE.md / 缺 settings.json → exit 0 + WARN。

set -uo pipefail

SETTINGS=".claude/settings.json"
CLAUDE_MD="CLAUDE.md"
HOOKS_DIR=".claude/hooks"
WARN_PREFIX="[claims-audit] WARN —"
# 治理 doc 集合（Check C：hook 应至少在其一被文档化）
DOC_SET=("CLAUDE.md" ".claude/standards/security.md" ".claude/rules/repo-layout.md")
# Check C 豁免：基础设施 / 遥测 / 库，非"能力声称"对象
C_EXEMPT="agf-hook-guard"

fail=0

if ! command -v jq >/dev/null 2>&1; then
  echo "$WARN_PREFIX 缺 jq，跳过" >&2; exit 0
fi
if [[ ! -f "$SETTINGS" || ! -f "$CLAUDE_MD" ]]; then
  echo "$WARN_PREFIX 缺 $SETTINGS 或 ${CLAUDE_MD}，跳过" >&2; exit 0
fi

# ---------------------------------------------------------------------------
# Check A: 已注册 hook 脚本 → 磁盘存在（硬阻断）
# ---------------------------------------------------------------------------
echo "--- A. 已注册 hook → 磁盘存在 ---"
REG_HOOKS=$(jq -r '.hooks | to_entries[] | .value[] | .hooks[]?.command' "$SETTINGS" 2>/dev/null \
  | grep -oE '\.claude/hooks/[a-zA-Z0-9_-]+\.sh' | sed 's|.*/||' | sort -u)
A_MISS=""
while IFS= read -r h; do
  [[ -z "$h" ]] && continue
  [[ -f "$HOOKS_DIR/$h" ]] || A_MISS+="   - ${h}（settings.json 注册，但 $HOOKS_DIR/$h 不存在）"$'\n'
done <<< "$REG_HOOKS"
if [[ -n "$A_MISS" ]]; then
  echo "❌ 注册了却无脚本文件：" >&2; printf '%s' "$A_MISS" >&2; fail=1
else
  echo "  ✅ 所有已注册 hook 脚本均存在"
fi

# ---------------------------------------------------------------------------
# Check B: CLAUDE.md 点名的 AGF 脚本 → 仓库中存在（硬阻断，doc-drift）
# 只认带 AGF 脚本前缀特征的 basename，避免误伤 prose 里的通用 .sh/.py 词。
# ---------------------------------------------------------------------------
echo "--- B. CLAUDE.md 点名脚本 → 存在 ---"
NAMED=$(grep -oE '[a-zA-Z0-9_-]+\.(sh|py)' "$CLAUDE_MD" 2>/dev/null \
  | grep -E '^(agf-|gate-|block-|scan-|check-|enforce-|validate-|session-|teammate-|sanitize-|gen-|lint-|run-|archive-)' \
  | sort -u)
B_MISS=""
while IFS= read -r s; do
  [[ -z "$s" ]] && continue
  # 在仓库内查（排除 .git / node_modules / worktree）
  if [[ -z "$(find . -name "$s" -not -path './.git/*' -not -path '*/node_modules/*' 2>/dev/null | head -1)" ]]; then
    B_MISS+="   - ${s}（CLAUDE.md 点名，但仓库中无此文件——幽灵声称 / 改名漂移）"$'\n'
  fi
done <<< "$NAMED"
if [[ -n "$B_MISS" ]]; then
  echo "❌ CLAUDE.md 点名但不存在：" >&2; printf '%s' "$B_MISS" >&2; fail=1
else
  echo "  ✅ CLAUDE.md 点名的脚本均存在"
fi

# ---------------------------------------------------------------------------
# Check C: 已注册 hook → 治理 doc 有文档（advisory）
# ---------------------------------------------------------------------------
echo "--- C. 已注册 hook → 有文档（advisory）---"
C_WARN=""
while IFS= read -r h; do
  [[ -z "$h" ]] && continue
  base="${h%.sh}"
  case " $C_EXEMPT " in *" $base "*) continue ;; esac
  documented=0
  for d in "${DOC_SET[@]}"; do
    [[ -f "$d" ]] || continue
    # 全名（<hook>.sh）或裸名（<hook>）任一出现即视为已文档化——裸名提及也是合法文档
    if grep -qF "$h" "$d" 2>/dev/null || grep -qF "$base" "$d" 2>/dev/null; then documented=1; break; fi
  done
  [[ "$documented" -eq 0 ]] && C_WARN+="   - ${h}（已注册，但未在治理 doc 中文档化）"$'\n'
done <<< "$REG_HOOKS"
if [[ -n "$C_WARN" ]]; then
  echo "⚠️  未文档化的已注册 hook（advisory，不阻断）：" >&2; printf '%s' "$C_WARN" >&2
else
  echo "  ✅ 所有已注册 hook 均有文档"
fi

echo "─────────"
if [[ "$fail" -ne 0 ]]; then
  echo "❌ claims-audit 失败（A/B 硬阻断项违规）" >&2; exit 2
fi
echo "✅ claims-audit 通过"
exit 0
