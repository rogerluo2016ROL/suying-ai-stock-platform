#!/usr/bin/env bash
# agf-team-start.sh — interactive Agent Team launcher
#
# 等价于 slash command `/agf-team-start <feature>`，但额外提供交互式
# teammate 多选菜单。选完后 exec 进 `claude`，自动喂入 spawn prompt。
#
# 用法：
#   ./agf-team-start.sh                              # 全交互
#   ./agf-team-start.sh --dry-run                    # 只打印 prompt，不启动 claude
#   ./agf-team-start.sh --skip-deps                  # 跳过项目依赖体检（不推荐）
#   ./agf-team-start.sh --dangerously-skip-permissions  # 跳过所有权限提示（自担风险）
#   ./agf-team-start.sh -h | --help                  # 帮助
#
# SSOT 引用（本脚本不复述以下内容，仅做 UX + 拼接）：
#   - 启动协议：    .claude/rules/team-mode.md
#   - slash 命令体： .claude/commands/agf-team-start.md
#   - agent 名单：  .claude/agents/*.md（运行时动态读取）

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_DIR="$PROJECT_ROOT/.claude/agents"
SETTINGS_FILE="$PROJECT_ROOT/.claude/settings.json"

# product-lead 固定为 Agent Team lead，依据 .claude/rules/team-mode.md
LEAD_AGENT="product-lead"

# Agent Teams 实验功能的最低 Claude Code 版本
MIN_CC_MAJOR=2; MIN_CC_MINOR=1; MIN_CC_PATCH=130

DRY_RUN=0
SKIP_PERMS=0
SKIP_DEPS=0

# ---------- helpers ----------
if [[ -t 1 ]]; then
  R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[0;33m'; B=$'\033[0;34m'
  C=$'\033[0;36m'; BOLD=$'\033[1m'; N=$'\033[0m'
else
  R= G= Y= B= C= BOLD= N=
fi
ok()   { printf '%s\n' "${G}✅${N} $1"; }
warn() { printf '%s\n' "${Y}⚠️ ${N} $1"; }
fail() { printf '%s\n' "${R}❌${N} $1" >&2; }
info() { printf '%s\n' "${B}→${N} $1"; }
hdr()  { printf '\n%s\n' "${BOLD}$1${N}"; }

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

交互式 Agent Team 启动器。等价于 slash command \`/agf-team-start <feature>\`，
但提供 teammate 多选菜单与运行时预检。

OPTIONS
  -h, --help        显示本帮助
      --dry-run     只打印拼好的 prompt，不启动 claude
      --skip-deps   跳过项目依赖体检（jq / docker / node / python 等）
      --dangerously-skip-permissions
                    [DEPRECATED, 默认已开] 自 commit 86c883f 起本脚本默认透传
                    --dangerously-skip-permissions，本 flag 为兼容旧脚本保留

WORKFLOW
  1. 预检（claude CLI、版本、Agent Teams env、git 仓库、agents 目录）
  2. 输入 feature 描述
  3. 从 .claude/agents/ 动态列出 teammates（lead 固定为 ${LEAD_AGENT}）
  4. 多选 teammates
  5. exec claude 并喂入 spawn prompt

SSOT
  启动协议：    .claude/rules/team-mode.md
  slash 命令：  .claude/commands/agf-team-start.md
  agent 名单：  .claude/agents/*.md（运行时动态读取）
EOF
}

# ---------- arg parse ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-deps) SKIP_DEPS=1; shift ;;
    --dangerously-skip-permissions) SKIP_PERMS=1; shift ;;
    *) fail "未知参数: $1"; usage; exit 2 ;;
  esac
done

# ---------- pre-flight ----------
hdr "Pre-flight 检查"

if ! command -v claude >/dev/null 2>&1; then
  fail "claude CLI 未安装。安装：https://claude.com/claude-code"
  exit 1
fi
ok "claude CLI: $(command -v claude)"

CC_VER="$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
if [[ -z "$CC_VER" ]]; then
  warn "无法解析 claude --version 输出（继续）"
else
  IFS='.' read -r maj min pat <<< "$CC_VER"
  if (( maj < MIN_CC_MAJOR )) \
     || (( maj == MIN_CC_MAJOR && min < MIN_CC_MINOR )) \
     || (( maj == MIN_CC_MAJOR && min == MIN_CC_MINOR && pat < MIN_CC_PATCH )); then
    fail "claude v${CC_VER} 低于 Agent Teams 最低 v${MIN_CC_MAJOR}.${MIN_CC_MINOR}.${MIN_CC_PATCH}。请运行 \`claude update\`"
    exit 1
  fi
  ok "claude v${CC_VER} (≥ v${MIN_CC_MAJOR}.${MIN_CC_MINOR}.${MIN_CC_PATCH})"
fi

# Agent Teams env：settings.json 启用 OR shell env 启用 任一即可
TEAMS_IN_SETTINGS=0; TEAMS_IN_SHELL=0
if [[ -f "$SETTINGS_FILE" ]] && \
   grep -q '"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"[[:space:]]*:[[:space:]]*"1"' "$SETTINGS_FILE"; then
  TEAMS_IN_SETTINGS=1
fi
[[ "${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-}" = "1" ]] && TEAMS_IN_SHELL=1

if (( TEAMS_IN_SETTINGS == 0 && TEAMS_IN_SHELL == 0 )); then
  fail "Agent Teams 未启用"
  fail "  方案 A：.claude/settings.json env 块加 \"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS\": \"1\""
  fail "  方案 B：shell 中 export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1"
  exit 1
fi
ok "Agent Teams 已启用 (settings.json=${TEAMS_IN_SETTINGS}, env=${TEAMS_IN_SHELL})"

if git -C "$PROJECT_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  ok "git 仓库已就绪（worktree 隔离前提）"
else
  warn "非 git 仓库 — 并行 teammate worktree 隔离不可用"
  warn "见 .claude/standards/workflow.md 'Parallel Dispatch' 节"
fi

if [[ ! -d "$AGENTS_DIR" ]]; then
  fail "agents 目录不存在: $AGENTS_DIR"
  exit 1
fi

# ---------- dependency checks ----------
# Block：缺即退出（hooks / 脚本运行所必需）
# Warn：缺仅警告（项目技术栈，按需安装）
# Hook integrity：pre-commit 软链 + scan-commit.sh 可执行（CLAUDE.md 强制）
if (( SKIP_DEPS == 0 )); then
  hdr "依赖体检（--skip-deps 可跳过）"
  block_miss=0; warn_miss=0

  # Block: required commands -----------------------------------------------
  # claude / git 已在前面预检，这里只补剩余 block 项
  if command -v jq >/dev/null 2>&1; then
    ok "jq: $(jq --version 2>/dev/null) — 6 个 hook + 1 个 script 依赖"
  else
    fail "缺 jq — hook 脚本不可运行（macOS: brew install jq）"
    block_miss=$((block_miss+1))
  fi

  # Warn: project tech stack -----------------------------------------------
  hdr "技术栈依赖（缺仅警告）"

  if (( BASH_VERSINFO[0] >= 4 )); then
    ok "bash v${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]} (≥ 4)"
  else
    warn "bash v${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]} 偏老（macOS 默认 3.2；脚本 / hook 当前能跑，但写新脚本若用 4+ 特性会失败 → brew install bash）"
    warn_miss=$((warn_miss+1))
  fi

  if command -v gh >/dev/null 2>&1; then
    ok "gh: $(gh --version 2>/dev/null | head -1)"
  else
    warn "缺 gh — release / PR 流程不可用（brew install gh）"
    warn_miss=$((warn_miss+1))
  fi

  if command -v docker >/dev/null 2>&1; then
    ok "docker: $(docker --version 2>/dev/null)"
    if docker compose version >/dev/null 2>&1; then
      ok "docker compose 可用"
    elif command -v docker-compose >/dev/null 2>&1; then
      ok "docker-compose: $(docker-compose --version 2>/dev/null)"
    else
      warn "docker 在但 compose 不可用 — ADR-000 用 docker compose 跑 Postgres"
      warn_miss=$((warn_miss+1))
    fi
  else
    warn "缺 docker — backend 无法跑 Postgres（见 ADR-000）"
    warn_miss=$((warn_miss+1))
  fi

  if command -v node >/dev/null 2>&1; then
    nv="$(node --version 2>/dev/null | sed 's/^v//')"
    nmaj="${nv%%.*}"
    if [[ -n "$nmaj" ]] && (( nmaj >= 20 )); then
      ok "node v${nv} (≥ 20)"
    else
      warn "node v${nv} 偏低（推荐 ≥ 20，Vite 前端要求）"
      warn_miss=$((warn_miss+1))
    fi
  else
    warn "缺 node — 前端开发不可用"
    warn_miss=$((warn_miss+1))
  fi

  if command -v npm >/dev/null 2>&1; then
    ok "npm v$(npm --version 2>/dev/null)"
  else
    warn "缺 npm"
    warn_miss=$((warn_miss+1))
  fi

  if command -v python3 >/dev/null 2>&1; then
    pv="$(python3 --version 2>/dev/null | awk '{print $2}')"
    pmaj="${pv%%.*}"
    rest="${pv#*.}"; pmin="${rest%%.*}"
    if [[ -n "$pmaj" && -n "$pmin" ]] && { (( pmaj > 3 )) || { (( pmaj == 3 )) && (( pmin >= 11 )); }; }; then
      ok "python3 v${pv} (≥ 3.11)"
    else
      warn "python3 v${pv} 偏低（推荐 ≥ 3.11）"
      warn_miss=$((warn_miss+1))
    fi
  else
    warn "缺 python3 — backend 开发不可用"
    warn_miss=$((warn_miss+1))
  fi

  if command -v uv >/dev/null 2>&1; then
    ok "uv: $(uv --version 2>/dev/null)"
  elif command -v pip3 >/dev/null 2>&1; then
    ok "pip3: $(pip3 --version 2>/dev/null | awk '{print $2}')（建议升级到 uv：curl -LsSf https://astral.sh/uv/install.sh | sh）"
  else
    warn "缺 uv / pip3 — backend 依赖管理不可用"
    warn_miss=$((warn_miss+1))
  fi

  # Hook integrity ---------------------------------------------------------
  hdr "Hook 防御链完整性（CLAUDE.md 强制）"
  hook_src="$PROJECT_ROOT/.claude/hooks/scan-commit.sh"
  hook_dst="$PROJECT_ROOT/.git/hooks/pre-commit"
  if [[ ! -f "$hook_src" ]]; then
    warn "scan-commit.sh 不存在: $hook_src"
    warn_miss=$((warn_miss+1))
  elif [[ ! -x "$hook_src" ]]; then
    warn "scan-commit.sh 不可执行 → chmod +x \"$hook_src\""
    warn_miss=$((warn_miss+1))
  elif [[ -L "$hook_dst" ]]; then
    target="$(readlink "$hook_dst")"
    if [[ "$target" == *"scan-commit.sh" ]]; then
      ok "pre-commit hook → ${target}"
    else
      warn "pre-commit hook 指向 ${target}（应指 scan-commit.sh）"
      warn_miss=$((warn_miss+1))
    fi
  elif [[ -f "$hook_dst" ]]; then
    warn "pre-commit hook 存在但非软链 — 可能覆盖项目防御链"
    warn_miss=$((warn_miss+1))
  else
    warn "pre-commit hook 未安装 → ln -sf ../../.claude/hooks/scan-commit.sh \"$hook_dst\""
    warn_miss=$((warn_miss+1))
  fi

  # Summary ----------------------------------------------------------------
  hdr "依赖体检汇总"
  if (( block_miss > 0 )); then
    fail "${block_miss} 个必需依赖缺失，中止"
    fail "如确认环境受限可加 --skip-deps 跳过（自担风险）"
    exit 1
  fi
  if (( warn_miss > 0 )); then
    warn "${warn_miss} 个可选依赖警告 — 不阻塞，继续启动"
  else
    ok "全部依赖就绪"
  fi
else
  warn "依赖体检已跳过 (--skip-deps)"
fi

# ---------- discover teammates ----------
AGENT_NAMES=(); AGENT_DESCS=()
for f in "$AGENTS_DIR"/*.md; do
  [[ -f "$f" ]] || continue
  name="$(awk '/^name:/{print $2; exit}' "$f")"
  [[ -z "$name" || "$name" = "$LEAD_AGENT" ]] && continue
  # description 第一段（取行内容，截 80 字符）
  desc="$(awk '/^description:/{$1=""; sub(/^ /,""); print; exit}' "$f")"
  desc="${desc:0:80}"
  AGENT_NAMES+=("$name")
  AGENT_DESCS+=("$desc")
done

if (( ${#AGENT_NAMES[@]} == 0 )); then
  fail "$AGENTS_DIR 下没有可选 teammate（已排除 lead ${LEAD_AGENT}）"
  exit 1
fi
ok "发现 ${#AGENT_NAMES[@]} 个候选 teammate（lead 固定为 ${LEAD_AGENT}）"

# ---------- 1) 任务描述 ----------
hdr "1) 描述要交付的 feature / task"
printf "  ${C}一句话描述，回车确认：${N} "
IFS= read -er FEATURE_DESC
FEATURE_DESC="$(printf '%s' "$FEATURE_DESC" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if (( ${#FEATURE_DESC} < 4 )); then
  fail "描述过短（<4 字符），中止"
  exit 2
fi

# ---------- 2) 选 teammates ----------
hdr "2) 选择 teammates"
selected=()
for _ in "${AGENT_NAMES[@]}"; do selected+=(0); done

print_menu() {
  for i in "${!AGENT_NAMES[@]}"; do
    if (( selected[i] )); then mark="${G}[x]${N}"; else mark="[ ]"; fi
    printf "  %2d) %b %-25s %s\n" "$((i+1))" "$mark" "${AGENT_NAMES[$i]}" "${AGENT_DESCS[$i]}"
  done
}

while true; do
  echo
  print_menu
  echo
  printf "  ${C}输入数字切换选中（如 '1 3 5'）；'a' 全选、'n' 全不选、'd' 完成、'q' 退出：${N} "
  IFS= read -er input
  case "$input" in
    d|D|done) break ;;
    a|A|all)  for i in "${!selected[@]}"; do selected[$i]=1; done ;;
    n|N|none) for i in "${!selected[@]}"; do selected[$i]=0; done ;;
    q|Q|quit) info "已退出"; exit 0 ;;
    "") warn "无输入。'd' 完成 / 数字切换 / 'q' 退出" ;;
    *)
      for tok in $input; do
        if [[ "$tok" =~ ^[0-9]+$ ]]; then
          idx=$((tok-1))
          if (( idx >= 0 && idx < ${#AGENT_NAMES[@]} )); then
            selected[idx]=$(( ! selected[idx] ))
          else
            warn "越界: $tok"
          fi
        else
          warn "非数字: $tok"
        fi
      done
      ;;
  esac
done

CHOSEN=()
for i in "${!AGENT_NAMES[@]}"; do
  (( selected[i] )) && CHOSEN+=("${AGENT_NAMES[$i]}")
done
if (( ${#CHOSEN[@]} == 0 )); then
  fail "未选择任何 teammate，中止"
  exit 2
fi
ok "已选 ${#CHOSEN[@]} 个 teammate: ${CHOSEN[*]}"

# ---------- 3) 拼装 prompt ----------
# 纯透传：feature 描述 + teammate 标记。如何解读 [teammates: ...] 标记由
# .claude/commands/agf-team-start.md "Teammate 选择规则" 节定义（SSOT）。
TEAMMATE_CSV="$(IFS=','; echo "${CHOSEN[*]}")"
PROMPT="/agf-team-start ${FEATURE_DESC}
[teammates: ${TEAMMATE_CSV}]"

hdr "3) 即将发送的 prompt"
echo "$PROMPT"

if (( DRY_RUN == 1 )); then
  hdr "Dry run — 不启动 claude"
  (( SKIP_PERMS == 1 )) && info "(若实际启动会附加 --dangerously-skip-permissions)"
  exit 0
fi

# ---------- 4) launch ----------
hdr "4) 启动 claude..."
# --dangerously-skip-permissions 自 commit 86c883f 起默认透传（避免 spawn 时反复
# permission prompt 中断 PL 编排）；脚本不再支持关闭，--dangerously-skip-permissions
# 旧 flag 保留兼容但行为相同。
warn "已启用 --dangerously-skip-permissions：claude 将跳过所有权限提示，自担风险"
exec claude --dangerously-skip-permissions "$PROMPT"
