#!/usr/bin/env bash
# test-install.sh — 安装链路 E2E 自检（install-to-existing.sh）
#
# 用途: 在 mktemp 临时 git 仓库实跑 install-to-existing.sh，验证：
#   1. 安装清单齐全（.claude/ 七目录条目数与源仓动态对比，不硬编码 + 根脚本 + docs 模板 + progress/ + pre-commit symlink）
#   2. 装入的 settings.json（及 .mcp.json，如有装入）可被 JSON 解析
#   3. 二次重跑不报错；产生 diff 则按 known-gap 输出 warn（不改安装器幂等行为）
#   4. 全程不污染源仓（源仓 git status 前后对比）
#
# 用法: bash .claude/scripts/test-install.sh
# 退出码: 0 = 无硬性失败（warn 允许）；1 = 任一硬性失败
# 备注: bash 3.2 兼容；stdin 接 /dev/null（安装器现状非交互，若未来加 read 会立刻 fail 而非挂死）；
#       结束自动清理临时目录（trap EXIT）

set -uo pipefail

# 颜色（仅当 stdout 是 terminal 时启用）
if [[ -t 1 ]]; then
  R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[0;33m'; B=$'\033[0;34m'; N=$'\033[0m'
else
  R= G= Y= B= N=
fi

PASS=0; WARN=0; FAIL=0
ok()   { echo "${G}✅${N} $1"; PASS=$((PASS+1)); }
warn() { echo "${Y}⚠️ ${N} $1"; WARN=$((WARN+1)); }
fail() { echo "${R}❌${N} $1"; FAIL=$((FAIL+1)); }
info() { echo "${B}→${N} $1"; }

summary_and_exit() {
  echo
  echo "=== Summary ==="
  echo "${G}通过${N}: $PASS  ${Y}警告${N}: $WARN  ${R}失败${N}: $FAIL"
  if [[ $FAIL -gt 0 ]]; then
    echo "${R}安装链路自检有 $FAIL 处硬性失败。${N}"
    exit 1
  fi
  echo "${G}安装链路自检通过${N}（warn 为 known-gap，如实记录，不算失败）"
  exit 0
}

# ---- 定位源仓 -----------------------------------------------------------------
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALLER="$SOURCE/setup/install-to-existing.sh"

echo "=== AGF 安装链路 E2E 自检 (install-to-existing.sh) ==="
echo

if [[ ! -f "$INSTALLER" ]]; then
  fail "找不到安装器: $INSTALLER"
  summary_and_exit
fi

# 源仓污染检测基线
SRC_STATUS_BEFORE="$(git -C "$SOURCE" status --porcelain 2>/dev/null || true)"

# ---- 临时目标仓库 --------------------------------------------------------------
TMP="$(mktemp -d "${TMPDIR:-/tmp}/agf-test-install.XXXXXX")" || { fail "mktemp 失败"; summary_and_exit; }
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT INT TERM

info "临时目标仓库: $TMP"
git -C "$TMP" init -q
git -C "$TMP" config user.email "agf-test@local"
git -C "$TMP" config user.name "agf-test"
ok "git init + identity 就绪"

# 日志放 .git/ 下，避免出现在工作树 diff 里干扰幂等性判定
LOG1="$TMP/.git/agf-install-run1.log"
LOG2="$TMP/.git/agf-install-run2.log"

# ---- Run 1: 首次安装 -----------------------------------------------------------
echo
info "第一次安装（非交互，stdin=/dev/null）..."
if bash "$INSTALLER" "$TMP" </dev/null >"$LOG1" 2>&1; then
  ok "install-to-existing.sh 第一次运行 exit 0"
else
  RC=$?
  fail "第一次安装失败 (exit $RC)，日志尾部："
  tail -20 "$LOG1" | sed 's/^/     /'
  summary_and_exit
fi

# ---- 检查 a: 目录清单（条目数从源仓动态算，不硬编码） ---------------------------
echo
info "校验 .claude/ 目录清单（条目数与源仓动态对比）..."
for d in agents standards hooks commands skills rules scripts; do
  if [[ -d "$TMP/.claude/$d" ]]; then
    SRC_N=$(ls "$SOURCE/.claude/$d" | wc -l | tr -d ' ')
    TGT_N=$(ls "$TMP/.claude/$d" | wc -l | tr -d ' ')
    if [[ "$SRC_N" == "$TGT_N" ]]; then
      ok ".claude/$d/ 条目数一致（${TGT_N}）"
    else
      fail ".claude/$d/ 条目数不一致：源 $SRC_N vs 装入 $TGT_N"
    fi
  else
    fail ".claude/$d/ 未装入"
  fi
done

info "校验关键文件..."
REQUIRED_FILES=".claude/settings.json
setup/init-team.sh
setup/agf-team-start.sh
setup/customize.sh
CLAUDE.md
CLAUDE.md.agf-template
docs/FIRST_RUN.md
docs/team-capability-map.md
docs/product-workflow.md
docs/prd/_TEMPLATE.md
docs/reviews/retro-_TEMPLATE.md
docs/adr/000-system-architecture.md.agf-template
progress/README.md
progress/.gitkeep
AGF_INSTALL_NEXT_STEPS.md"
MISSING=0
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if [[ ! -f "$TMP/$f" ]]; then
    fail "缺文件: $f"
    MISSING=$((MISSING+1))
  fi
done <<< "$REQUIRED_FILES"
if [[ $MISSING -eq 0 ]]; then
  ok "关键文件齐全（$(echo "$REQUIRED_FILES" | wc -l | tr -d ' ') 个）"
fi

# greenfield CLAUDE.md 必须来自 CLAUDE.example.md 脚手架（而非模板仓自身 CLAUDE.md）
if grep -q '^# \[Project Name\]' "$TMP/CLAUDE.md" 2>/dev/null; then
  ok "greenfield CLAUDE.md = CLAUDE.example.md 脚手架起点"
else
  fail "greenfield CLAUDE.md 非 CLAUDE.example.md 起点（疑似拷了模板仓自身 CLAUDE.md）"
fi

# pre-commit symlink
if [[ -L "$TMP/.git/hooks/pre-commit" ]] && [[ "$(readlink "$TMP/.git/hooks/pre-commit")" == *"scan-commit.sh" ]]; then
  ok ".git/hooks/pre-commit → scan-commit.sh symlink 已装"
else
  fail ".git/hooks/pre-commit symlink 缺失或指向错误"
fi

# 可执行位
NOEXEC=0
for f in "$TMP/setup/init-team.sh" "$TMP/setup/agf-team-start.sh" "$TMP/setup/customize.sh" "$TMP/.claude/hooks/"*.sh "$TMP/.claude/scripts/"*.sh; do
  if [[ -f "$f" && ! -x "$f" ]]; then
    fail "缺可执行位: ${f#"$TMP"/}"
    NOEXEC=$((NOEXEC+1))
  fi
done
[[ $NOEXEC -eq 0 ]] && ok "setup/*.sh + hooks/*.sh + scripts/*.sh 可执行位齐全"

# ---- 检查 b: JSON 可解析 --------------------------------------------------------
echo
info "校验装入 JSON 可解析..."
json_check() {
  # $1 = 目标仓内相对路径
  if command -v python3 >/dev/null 2>&1; then
    if python3 -m json.tool "$TMP/$1" >/dev/null 2>&1; then
      ok "$1 JSON 解析通过 (python3)"
    else
      fail "$1 JSON 解析失败"
    fi
  elif command -v jq >/dev/null 2>&1; then
    if jq . "$TMP/$1" >/dev/null 2>&1; then
      ok "$1 JSON 解析通过 (jq)"
    else
      fail "$1 JSON 解析失败"
    fi
  else
    warn "python3 / jq 均不可用，跳过 $1 JSON 校验"
  fi
}
json_check ".claude/settings.json"
if [[ -f "$TMP/.mcp.json" ]]; then
  json_check ".mcp.json"
elif [[ -f "$SOURCE/.mcp.json" ]]; then
  warn "known-gap: 源仓有 .mcp.json 但 install-to-existing.sh 未拷贝（qa-engineer E2E 依赖 chrome-devtools MCP）— 如实记录，不改安装器"
fi

# ---- 检查 c: 幂等性（二次重跑） --------------------------------------------------
echo
info "幂等性：commit 基线后二次重跑..."
git -C "$TMP" add -A >/dev/null 2>&1
git -C "$TMP" commit -q --no-verify -m "agf-install run1 baseline" >/dev/null 2>&1
if bash "$INSTALLER" "$TMP" </dev/null >"$LOG2" 2>&1; then
  ok "第二次重跑 exit 0（不报错）"
else
  RC=$?
  fail "第二次重跑失败 (exit $RC)，日志尾部："
  tail -20 "$LOG2" | sed 's/^/     /'
fi
DIFF="$(git -C "$TMP" status --porcelain 2>/dev/null || true)"
if [[ -z "$DIFF" ]]; then
  ok "二次重跑零 diff（幂等）"
else
  DIFF_N=$(echo "$DIFF" | wc -l | tr -d ' ')
  warn "known-gap: 二次重跑产生 $DIFF_N 处 diff（备份 + .agf-template + NEXT_STEPS 重写，安装器现状刻意如此，不算失败）。样例："
  echo "$DIFF" | head -8 | sed 's/^/     /'
fi

# ---- 检查 d: 源仓未被污染 -------------------------------------------------------
echo
info "校验源仓未被污染..."
SRC_STATUS_AFTER="$(git -C "$SOURCE" status --porcelain 2>/dev/null || true)"
if [[ "$SRC_STATUS_BEFORE" == "$SRC_STATUS_AFTER" ]]; then
  ok "源仓 git status 前后一致（未污染）"
else
  fail "源仓 git status 发生变化！自检脚本或安装器写入了源仓"
fi

summary_and_exit
