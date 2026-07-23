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
    # 排除 __pycache__：源 checkout 用过 python 后会有编译产物，安装器现已主动不分发；
    # skills 另排除 office 技能组（默认不装，--with-office-skills 选装，v6.25.0）
    if [[ "$d" == "skills" ]]; then
      SRC_N=$(ls "$SOURCE/.claude/$d" | grep -Evc '^(docx|pptx|agf-writing-docx-reports|agf-writing-pptx-reports|__pycache__)$')
    else
      SRC_N=$(ls "$SOURCE/.claude/$d" | grep -cv '^__pycache__$')
    fi
    TGT_N=$(ls "$TMP/.claude/$d" | grep -cv '^__pycache__$')
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
.claude/.agf-version
setup/init-team.sh
setup/customize.sh
CLAUDE.md
CLAUDE.md.agf-template
docs/FIRST_RUN.md
docs/team-capability-map.md
docs/product-workflow.md
docs/qa/_TEMPLATE.md
docs/qa/uat-cases-_TEMPLATE.md
docs/reviews/_TEMPLATE.md
docs/reviews/retro-_TEMPLATE.md
docs/changes/README.md
docs/changes/_TEMPLATE/proposal.md
docs/changes/_TEMPLATE/design.md
docs/changes/_TEMPLATE/tasks.md
docs/changes/archive/.gitkeep
docs/specs/README.md
docs/specs/_TEMPLATE.md
.claude/security/deny-baseline.json
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

# 负向断言：弃用/垃圾资产不得进目标项目
if [[ -d "$TMP/docs/prd" || -d "$TMP/docs/growth" ]]; then
  fail "弃用目录被创建：docs/prd 或 docs/growth（PRD 弃用 v6.9.0；growth 无目录约定）"
else
  ok "未创建弃用目录（docs/prd / docs/growth）"
fi
if find "$TMP/.claude" \( -name '__pycache__' -o -name '*.pyc' \) 2>/dev/null | grep -q .; then
  fail "目标 .claude/ 含 __pycache__/.pyc（安装器应清理源 checkout 编译产物）"
else
  ok "目标 .claude/ 无 __pycache__/.pyc"
fi
if [[ -d "$TMP/.claude/skills/docx" || -d "$TMP/.claude/skills/pptx" || -d "$TMP/.claude/skills/agf-writing-pptx-reports" ]]; then
  fail "office 技能组被默认装入（应 --with-office-skills 才装，v6.25.0）"
else
  ok "office 技能组默认未装（docx/pptx/agf-writing-{docx,pptx}-reports）"
fi

# C2（ADR-021）：codemap build 生成 .agf/code-map.db（整库结构摘要，二进制可重建），
# 安装器必须随装写入 target .gitignore 忽略 .agf/，否则用户首次 codemap build 后
# git add . 就把图谱泄入版本库。
if grep -q '\.agf/' "$TMP/.gitignore" 2>/dev/null; then
  ok "target .gitignore 含 .agf/ 忽略规则（codemap 运行态产物不入库；C2）"
else
  fail "target .gitignore 缺 .agf/ 忽略规则（C2：codemap build 后 .agf/*.db 会泄入 git）"
fi

# greenfield CLAUDE.md 必须来自 CLAUDE.example.md 脚手架（而非模板仓自身 CLAUDE.md）
if grep -q '^# \[Project Name\]' "$TMP/CLAUDE.md" 2>/dev/null; then
  ok "greenfield CLAUDE.md = CLAUDE.example.md 脚手架起点"
else
  fail "greenfield CLAUDE.md 非 CLAUDE.example.md 起点（疑似拷了模板仓自身 CLAUDE.md）"
fi

# 版本标记：内容必须与源仓 CLAUDE.md Template Version 一致（agf-install 升级检测依赖）
SRC_VER="$(sed -n 's/.*Template Version: \(v[0-9][0-9.]*\).*/\1/p' "$SOURCE/CLAUDE.md" 2>/dev/null | head -1)"
TGT_VER="$(head -1 "$TMP/.claude/.agf-version" 2>/dev/null)"
if [[ -n "$SRC_VER" && "$TGT_VER" == "$SRC_VER" ]]; then
  ok ".claude/.agf-version = ${TGT_VER}（与源仓一致）"
else
  fail ".claude/.agf-version 不一致：源 '${SRC_VER}' vs 装入 '${TGT_VER}'"
fi

# pre-commit symlink
if [[ -L "$TMP/.git/hooks/pre-commit" ]] && [[ "$(readlink "$TMP/.git/hooks/pre-commit")" == *"scan-commit.sh" ]]; then
  ok ".git/hooks/pre-commit → scan-commit.sh symlink 已装"
else
  fail ".git/hooks/pre-commit symlink 缺失或指向错误"
fi

# 可执行位
NOEXEC=0
for f in "$TMP/setup/init-team.sh" "$TMP/setup/customize.sh" "$TMP/.claude/hooks/"*.sh "$TMP/.claude/scripts/"*.sh; do
  if [[ -f "$f" && ! -x "$f" ]]; then
    fail "缺可执行位: ${f#"$TMP"/}"
    NOEXEC=$((NOEXEC+1))
  fi
done
[[ $NOEXEC -eq 0 ]] && ok "setup/*.sh + hooks/*.sh + scripts/*.sh 可执行位齐全"

# workflows 已随 ADR-026 D5 退役——目标项目不应再收到该目录
if [[ -d "$TMP/.claude/workflows" ]]; then
  fail ".claude/workflows/ 被装入（ADR-026 D5 已退役，不应分发）"
else
  ok ".claude/workflows/ 未分发（ADR-026 D5 退役）"
fi

# 去链接化：目标 .claude/*.md 不应残留任何 markdown 链接 [text](url)
MDLINKS=$(grep -rE '\]\([^)]+\)' "$TMP/.claude" --include="*.md" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$MDLINKS" -eq 0 ]]; then
  ok "target .claude/*.md 无 markdown 链接（去链接化生效，零 404）"
else
  fail "target .claude/*.md 残留 $MDLINKS 处 markdown 链接（去链接化未生效）"
fi

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

# ---- 检查 c2: --refresh-docs（升级刷新：旧文件备份 + 内容更新为源仓新版）----------
echo
info "--refresh-docs：篡改目标 docs/FIRST_RUN.md 后第三次重跑..."
echo "OLD-CONTENT-MARKER" > "$TMP/docs/FIRST_RUN.md"
LOG3="$TMP/.git/agf-install-run3.log"
if bash "$INSTALLER" "$TMP" --refresh-docs </dev/null >"$LOG3" 2>&1; then
  ok "第三次重跑（--refresh-docs）exit 0"
else
  RC=$?
  fail "--refresh-docs 运行失败 (exit $RC)，日志尾部："
  tail -10 "$LOG3" | sed 's/^/     /'
fi
if ! grep -q "OLD-CONTENT-MARKER" "$TMP/docs/FIRST_RUN.md" 2>/dev/null \
   && cmp -s "$TMP/docs/FIRST_RUN.md" "$SOURCE/docs/FIRST_RUN.md"; then
  ok "--refresh-docs 已把 docs/FIRST_RUN.md 刷新为源仓新版"
else
  fail "--refresh-docs 未刷新 docs/FIRST_RUN.md（仍是旧内容或与源仓不一致）"
fi
if ls "$TMP"/docs/FIRST_RUN.md.backup-* >/dev/null 2>&1; then
  ok "--refresh-docs 旧文件已备份（docs/FIRST_RUN.md.backup-*）"
else
  fail "--refresh-docs 未备份旧文件"
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
