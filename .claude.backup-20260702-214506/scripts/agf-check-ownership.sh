#!/usr/bin/env bash
# agf-check-ownership.sh — Pool 并行派发时校验实例只改了自己名下的文件
#
# 对比当前 worktree 的全部改动（staged + unstaged 走 `git diff --name-only HEAD`，
# untracked 走 `git ls-files --others --exclude-standard`）与允许的路径前缀 / glob；
# 越界 → 非零退出并列出违规文件。PL fan-in 前 / 实例收工自检用。
#
# 用法:
#   bash .claude/scripts/agf-check-ownership.sh <allowed-glob> [<allowed-glob>...]
#   匹配规则（保持简单，逐参数试）:
#     - 含 * ? [ 的参数 → bash case 模式匹配整个相对路径（注意 * 也会跨 /）
#     - 不含通配符的参数 → 前缀匹配（'backend/' ≈ backend/ 下所有文件；恰等也算）
#
# 退出码: 0 = 全部在允许范围；1 = 有越界文件；2 = 用法错误

set -uo pipefail

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,15p' "$0" >&2
  [[ $# -eq 0 ]] && exit 2
  exit 0
fi

# === 收集改动文件（staged + unstaged + untracked，去重）===
CHANGED=$(
  {
    git diff --name-only HEAD 2>/dev/null
    git ls-files --others --exclude-standard 2>/dev/null
  } | sort -u
)

# === 逐文件对允许列表做 case 模式 / 前缀匹配 ===
VIOLATIONS=()
CHECKED=0
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  CHECKED=$((CHECKED + 1))
  ok=0
  for g in "$@"; do
    case "$g" in
      *[\*\?\[]*)
        # glob 参数：case 模式匹配整个相对路径
        case "$f" in
          $g) ok=1 ;;
        esac
        ;;
      *)
        # 无通配符：前缀匹配（剥尾部 / 后，恰等或目录前缀都算）
        p="${g%/}"
        case "$f" in
          "$p"|"$p"/*) ok=1 ;;
        esac
        ;;
    esac
    [[ "$ok" -eq 1 ]] && break
  done
  [[ "$ok" -eq 0 ]] && VIOLATIONS+=("$f")
done <<< "$CHANGED"

if [[ ${#VIOLATIONS[@]} -gt 0 ]]; then
  echo "❌ [agf-check-ownership] ${#VIOLATIONS[@]} 个文件越界（不在允许范围内）:" >&2
  for f in "${VIOLATIONS[@]}"; do
    echo "  - $f" >&2
  done
  echo "   允许范围: $*" >&2
  exit 1
fi

echo "✅ [agf-check-ownership] 改动均在允许范围内（共 $CHECKED 个文件 · 允许: $*）"
exit 0
