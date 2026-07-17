#!/usr/bin/env bash
# .claude/scripts/agf-worktree-gc.sh
#
# worktree 生命周期分类 + 安全清理建议（人触发，**只建议不自动删**）。
# 依据 ECC scripts/lib/worktree-lifecycle/lifecycle.js:16-154 + git.js:125
# （AGF bash 移植；ADR-017 关联）。
#
# 状态分类（简化 8 态→6 态，省 conflict/idle 的 corner case）：
#   main          → keep（主仓）
#   detached      → keep（HEAD detached，不删）
#   dirty         → keep（**永不删**，有未提交工作 — ECC planCleanup 安全规则）
#   merged        → remove（ahead==0，已合并到默认分支，安全删）
#   stale         → salvage（有未合并 commit 但旧 >7d；先 push 备份再删）
#   merge-ready   → keep（新且有未合并，待 merge）
#
# 用法：bash .claude/scripts/agf-worktree-gc.sh
# 输出：分类表 + remove/salvage 的清理命令（人复制执行，脚本不自动删）

set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$PROJECT_DIR" 2>/dev/null || { echo "FAIL: 无法 cd $PROJECT_DIR"; exit 1; }

COMMON=$(git rev-parse --git-common-dir 2>/dev/null) || { echo "FAIL: 非 git 仓"; exit 1; }
MAIN_PATH=$(cd "$COMMON/.." 2>/dev/null && pwd)
DEFAULT=$(git symbolic-ref "refs/remotes/origin/HEAD" 2>/dev/null || true)
DEFAULT="${DEFAULT#refs/remotes/origin/}"
: "${DEFAULT:=main}"

echo "== worktree 生命周期分类（主仓: $(basename "$MAIN_PATH") · 默认分支: ${DEFAULT}）=="
echo ""
printf "%-45s %-18s %-6s %-6s %-7s %s\n" "PATH" "BRANCH" "AHEAD" "DIRTY" "AGE(d)" "STATE→ACTION"
printf '%.0s-' {1..100}; echo ""

git worktree list --porcelain 2>/dev/null | \
  awk 'BEGIN{RS=""}{wt="";br="";det=0;for(i=1;i<=NF;i++){if($i=="worktree")wt=$(i+1);if($i=="branch")br=$(i+1);if($i=="detached")det=1}print wt"\t"br"\t"det}' | \
  while IFS=$'\t' read -r wt br det; do
    [ -z "$wt" ] && continue
    short="${wt/#$HOME/~}"
    if [ "$wt" = "$MAIN_PATH" ]; then
      printf "%-45s %-18s %-6s %-6s %-7s %s\n" "$short" "(main)" "-" "-" "-" "main→keep"
      continue
    fi
    bdisp="${br:-detached}"; [ "$det" = "1" ] && bdisp="(detached)"
    dirty="-"; [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ] && dirty="Y"
    ahead=0
    if [ -n "$br" ] && [ "$det" != "1" ]; then
      ahead=$(git -C "$wt" rev-list --count "$DEFAULT..$br" 2>/dev/null || echo 0)
    fi
    age="-"
    lc=$(git -C "$wt" log -1 --format=%ct "${br:-HEAD}" 2>/dev/null)
    [ -n "$lc" ] && age=$(( ($(date +%s) - lc) / 86400 ))
    if [ "$dirty" = "Y" ]; then s="dirty→keep"
    elif [ "$det" = "1" ]; then s="detached→keep"
    elif [ "${ahead:-0}" -eq 0 ]; then s="merged→remove"
    elif [ "${age:-0}" -gt 7 ]; then s="stale→salvage"
    else s="merge-ready→keep"; fi
    printf "%-45s %-18s %-6s %-6s %-7s %s\n" "$short" "$bdisp" "$ahead" "$dirty" "$age" "$s"
  done

echo ""
echo "== 清理建议（人执行，不自动删）=="
echo "  remove  = git worktree remove <path>          （已合并，安全删）"
echo "  salvage = 先 git push <branch> 备份，再 git worktree remove <path>  （旧且有未合并 commit）"
echo "  keep    不动（main / detached / dirty / 活跃 merge-ready）"
