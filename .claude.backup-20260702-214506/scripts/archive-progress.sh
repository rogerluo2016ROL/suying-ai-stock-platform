#!/usr/bin/env bash
# archive-progress.sh — UAT 签字后归档 progress/ 到 docs/qa/<feature>-process-log.md
#
# 用法:
#   bash .claude/scripts/archive-progress.sh <feature>
#
# 行为:
#   1. 扫 progress/*.md（除 README.md）
#   2. 按 base role 分组（剥 `-<N>` 后缀），组内按 N 数字升序合并
#      （单实例 `<role>.md` 排在 `<role>-1.md` 之前）
#   3. 写入 docs/qa/<feature>-process-log.md（每 role 一段 ## 标题）
#   4. git rm progress/*.md（保留 .gitkeep + README.md）
#
# Pool 模式（ADR-001）支持:
#   - progress/backend-dev.md（单实例）→ 段标题 "## backend-dev"
#   - progress/backend-dev-1.md / backend-dev-2.md（pool 模式）→ 同一 "## backend-dev" 段下，
#     按 N 升序顺序 append，每实例小标题 "### Instance backend-dev-N"
#
# 调用方: product-lead，UAT 业务签字后执行（Self-Reporting Pattern 闭环）。
# 前置: 所有执行层 teammate 已停止写入 progress/，避免 race condition。

set -euo pipefail

FEATURE="${1:-}"
if [ -z "$FEATURE" ]; then
  echo "Usage: $0 <feature>  (e.g. login-2026-04-24, must match docs/prd/<feature>.md)" >&2
  exit 1
fi

OUT="docs/qa/${FEATURE}-process-log.md"

# 收集所有 progress/*.md（排除 README.md），按 base role + N 数字排序
# bash 3.2 兼容写法
declare -a FILES=()
while IFS= read -r f; do
  [ "$(basename "$f")" = "README.md" ] && continue
  FILES+=("$f")
done < <(find progress -maxdepth 1 -type f -name "*.md" -print 2>/dev/null | sort)

# 提取每文件的 (base_role, N) 二元组用于稳定分组
# N=-1 表示单实例（排在该 role 的 pool 实例之前）
# 数据结构：用临时文件存 "base_role|N|filepath"，方便排序
SORT_FILE=$(mktemp)
trap 'rm -f "$SORT_FILE"' EXIT

for f in "${FILES[@]}"; do
  name=$(basename "$f" .md)
  if [[ "$name" =~ ^(.+)-([0-9]+)$ ]]; then
    base="${BASH_REMATCH[1]}"
    n="${BASH_REMATCH[2]}"
  else
    base="$name"
    n="-1"  # 单实例排序键，置于 pool 实例之前
  fi
  printf '%s|%s|%s\n' "$base" "$n" "$f" >> "$SORT_FILE"
done

# 按 base 字典序 + N 数值升序
# 用 awk 把 N 转 6 位 0 padded 让字典序等价于数值序（避免 `sort -t| -k2,2n` 跨平台差异；%06d 支持 N 到 999999）
SORTED=$(awk -F'|' '{ printf "%s|%06d|%s\n", $1, $2, $3 }' "$SORT_FILE" | sort)

# 输出归档
{
  echo "# Process Log: $FEATURE"
  echo ""
  echo "归档自 progress/*.md，UAT 签字后由 product-lead 写入。"
  echo "原始底稿对应每个执行层 teammate（含 Multi-instance Worker Pool 模式下的多实例）在 feature 期间的完成/阻塞条目。"
  echo ""

  CURRENT_BASE=""
  while IFS='|' read -r base n_padded fpath; do
    [ -z "$base" ] && continue
    # 切换 base role 时输出新 H2 段
    if [ "$base" != "$CURRENT_BASE" ]; then
      [ -n "$CURRENT_BASE" ] && echo ""
      echo "---"
      echo ""
      echo "## $base"
      echo ""
      CURRENT_BASE="$base"
    fi
    # n_padded 是 06d 格式，恢复成数值用于显示
    n=$((10#$n_padded))
    if [ "$n" -ge 0 ]; then
      echo "### Instance ${base}-${n}（pool）"
    else
      echo "### Instance ${base}（single）"
    fi
    echo ""
    cat "$fpath"
    echo ""
  done <<< "$SORTED"
} > "$OUT"

echo "Wrote: $OUT"

# 清理 progress/*.md（保留 README.md + .gitkeep）
git rm progress/*.md 2>/dev/null || true
git restore --staged --worktree progress/README.md 2>/dev/null || true

echo "progress/*.md removed (README.md + .gitkeep retained)."
