#!/usr/bin/env bash
# .claude/scripts/check-repo-layout.sh
#
# repo-layout.md SSOT 一致性 advisory 校验——防"新增顶层目录忘更新 repo-layout"
# （I8 类型 drift：实际存在的目录未被 SSOT 列出）。
#
# 检查 git-tracked 顶层目录是否都在 .claude/rules/repo-layout.md 提及。
# **advisory**：只打 warning 到 stderr，不阻断 lint（exit 0）——新增目录可能是有意未列
# （临时实验 / 即将删除），由维护者判断。
#
# 跑法：bash .claude/scripts/check-repo-layout.sh
# 由 lint-all.sh 调用（advisory section，不影响 lint 退出码）。

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd -P)" || exit 0
LAYOUT="$ROOT/.claude/rules/repo-layout.md"
[ -f "$LAYOUT" ] || { echo "✗ $LAYOUT 不存在（无法校验）" >&2; exit 0; }
command -v git >/dev/null 2>&1 || exit 0

# 不该在 repo-layout 列的顶层目录（生成物 / 缓存 / IDE / gitignored / 语言产物）
SKIP_RE='^(\.git|\.superpowers|node_modules|__pycache__|.*\.egg-info|\.pytest_cache|\.ruff_cache|\.venv|\.idea|\.vscode|\.agf|dist|build|target|venv|env)$'

warnings=0
# git-tracked 顶层目录（路径形如 "dir/"）
while IFS= read -r top; do
  name="${top%/}"
  [[ -z "$name" ]] && continue
  [[ "$name" =~ $SKIP_RE ]] && continue
  if ! grep -qF "$name" "$LAYOUT" 2>/dev/null; then
    echo "  ⚠️ repo-layout 未提及顶层目录 '$name/'（advisory：若是产物目录应补列）" >&2
    warnings=$((warnings+1))
  fi
done < <(git -C "$ROOT" ls-files 2>/dev/null | grep -oE '^[^/]+/' | sort -u)

if [ "$warnings" -gt 0 ]; then
  echo "⚠️ repo-layout SSOT advisory：$warnings 个顶层目录未提及（advisory，不阻断 lint）" >&2
else
  echo "✓ repo-layout：所有 git-tracked 顶层目录都已提及"
fi
exit 0
