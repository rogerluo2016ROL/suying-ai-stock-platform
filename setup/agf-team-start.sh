#!/usr/bin/env bash
# agf-team-start.sh — interactive Agent Team launcher
#
# 等价于 slash command `/agf-team-start <feature>`，但额外提供交互式
# teammate 多选菜单。选完后 exec 进 `claude`，自动喂入 spawn prompt。
#
# 用法（在项目根运行）：
#   bash setup/agf-team-start.sh                              # 全交互
#   bash setup/agf-team-start.sh --dry-run                    # 只打印 prompt，不启动 claude
#   bash setup/agf-team-start.sh --skip-deps                  # 跳过项目依赖体检（不推荐）
#   bash setup/agf-team-start.sh --provider deepseek          # 指定后端 provider，跳过交互菜单
#   bash setup/agf-team-start.sh --dangerously-skip-permissions  # 跳过所有权限提示（自担风险）
#   bash setup/agf-team-start.sh -h | --help                  # 帮助
#
# SSOT 引用（本脚本不复述以下内容，仅做 UX + 拼接）：
#   - 启动协议：    .claude/rules/team-mode.md
#   - slash 命令体： .claude/commands/agf-team-start.md
#   - agent 名单：  .claude/agents/*.md（运行时动态读取）

set -uo pipefail

# 本脚本位于 setup/，项目根是上一级
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS_DIR="$PROJECT_ROOT/.claude/agents"
SETTINGS_FILE="$PROJECT_ROOT/.claude/settings.json"

# product-lead 固定为 Agent Team lead，依据 .claude/rules/team-mode.md
LEAD_AGENT="product-lead"

# Agent Teams 实验功能的最低 Claude Code 版本
MIN_CC_MAJOR=2; MIN_CC_MINOR=1; MIN_CC_PATCH=154

DRY_RUN=0
SKIP_PERMS=0
SKIP_DEPS=0
PROVIDER_OPT=""

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

# ---------- TUI 库（纯 bash 零依赖，被 source）----------
# 提供 tui_capable / tui_multiselect / tui_select / tui_input / tui_spinner_*。
# 契约见库头部注释。每处交互都以 `tui_capable` 分支：可用走 TUI，不可用（非 TTY /
# 管道 / dumb 终端）原样走下方现有文本菜单。source 失败（文件缺失等）不让启动器崩——
# warn 后定义 tui_capable() 恒返回 1，强制全程走文本菜单降级。
TUI_LIB="$PROJECT_ROOT/.claude/scripts/agf-tui.sh"
if [[ -f "$TUI_LIB" ]] && source "$TUI_LIB" 2>/dev/null; then
  :
else
  warn "TUI 库不可用（${TUI_LIB}）— 全程使用文本菜单降级"
  tui_capable() { return 1; }
fi

# ---------- LLM provider 选择（启动前导出 ANTHROPIC_* env，透传给 exec claude） ----------
# 设计：base_url / model 为非密值，可入库；密钥一律从 shell env 读（${VAR:?}），脚本内无明文。
# 端点/模型默认值可被同名 env 覆盖。Claude 官方 = 不改 base_url，用现有登录 / ANTHROPIC_API_KEY。
PROVIDER_KEYS=(claude minimax deepseek volcengine qwen mlx_qwen)

provider_label() {
  case "$1" in
    claude)     echo "Claude Official   — 官方 Anthropic（默认登录 / ANTHROPIC_API_KEY）" ;;
    minimax)    echo "MiniMax           — ${MINIMAX_ANTHROPIC_BASE_URL:-https://api.minimax.io/anthropic} · ${MINIMAX_MODEL:-MiniMax-M2}" ;;
    deepseek)   echo "DeepSeek Official — ${DEEPSEEK_ANTHROPIC_BASE_URL:-https://api.deepseek.com/anthropic} · ${DEEPSEEK_MODEL:-deepseek-chat}" ;;
    volcengine) echo "Volcengine        — ${ARK_ANTHROPIC_BASE_URL:-https://ark.cn-beijing.volces.com/api/coding} · ${ARK_MODEL:-ark-code-latest}" ;;
    qwen)       echo "Qwen / DashScope  — ${DASHSCOPE_ANTHROPIC_BASE_URL:-https://dashscope.aliyuncs.com/apps/anthropic} · ${QWEN_MODEL:-qwen3-coder-plus}" ;;
    mlx_qwen)   echo "MLX_Qwen3.6_35b   — 本地 ${MLX_ANTHROPIC_BASE_URL:-http://localhost:8080} · ${MLX_MODEL:-Qwen3.6-35B}" ;;
    *)          echo "$1" ;;
  esac
}

# 选中后导出对应 provider 的 ANTHROPIC_* env。缺必填 env（密钥/未知端点）时 ${VAR:?} 会
# 打印提示并直接退出脚本（宁可中止也不要用错端点把启动搞挂）。
apply_provider() {
  case "$1" in
    claude)
      unset ANTHROPIC_BASE_URL ANTHROPIC_MODEL ANTHROPIC_SMALL_FAST_MODEL ANTHROPIC_AUTH_TOKEN 2>/dev/null || true
      ;;
    minimax)
      # 国际站默认；中国大陆改 export MINIMAX_ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
      export ANTHROPIC_BASE_URL="${MINIMAX_ANTHROPIC_BASE_URL:-https://api.minimax.io/anthropic}"
      export ANTHROPIC_AUTH_TOKEN="${MINIMAX_API_KEY:?需 export MINIMAX_API_KEY}"
      export ANTHROPIC_MODEL="${MINIMAX_MODEL:-MiniMax-M2}"
      export ANTHROPIC_SMALL_FAST_MODEL="${MINIMAX_SMALL_MODEL:-${MINIMAX_MODEL:-MiniMax-M2}}"
      ;;
    deepseek)
      export ANTHROPIC_BASE_URL="${DEEPSEEK_ANTHROPIC_BASE_URL:-https://api.deepseek.com/anthropic}"
      export ANTHROPIC_AUTH_TOKEN="${DEEPSEEK_API_KEY:?需 export DEEPSEEK_API_KEY}"
      export ANTHROPIC_MODEL="${DEEPSEEK_MODEL:-deepseek-chat}"
      export ANTHROPIC_SMALL_FAST_MODEL="${DEEPSEEK_SMALL_MODEL:-deepseek-chat}"
      ;;
    volcengine)
      # 火山方舟 Coding Plan 网关（Anthropic 兼容）；模型用聚合名 ark-code-latest
      export ANTHROPIC_BASE_URL="${ARK_ANTHROPIC_BASE_URL:-https://ark.cn-beijing.volces.com/api/coding}"
      export ANTHROPIC_AUTH_TOKEN="${ARK_API_KEY:?需 export ARK_API_KEY}"
      export ANTHROPIC_MODEL="${ARK_MODEL:-ark-code-latest}"
      export ANTHROPIC_SMALL_FAST_MODEL="${ARK_SMALL_MODEL:-${ARK_MODEL:-ark-code-latest}}"
      ;;
    qwen)
      # 阿里云百炼 DashScope（Anthropic 兼容）；新加坡区改 dashscope-intl.aliyuncs.com
      export ANTHROPIC_BASE_URL="${DASHSCOPE_ANTHROPIC_BASE_URL:-https://dashscope.aliyuncs.com/apps/anthropic}"
      export ANTHROPIC_AUTH_TOKEN="${DASHSCOPE_API_KEY:?需 export DASHSCOPE_API_KEY}"
      export ANTHROPIC_MODEL="${QWEN_MODEL:-qwen3-coder-plus}"
      export ANTHROPIC_SMALL_FAST_MODEL="${QWEN_SMALL_MODEL:-${QWEN_MODEL:-qwen3-coder-plus}}"
      ;;
    mlx_qwen)
      export ANTHROPIC_BASE_URL="${MLX_ANTHROPIC_BASE_URL:-http://localhost:8080}"
      export ANTHROPIC_AUTH_TOKEN="${MLX_API_KEY:-mlx-local}"
      export ANTHROPIC_MODEL="${MLX_MODEL:-Qwen3.6-35B}"
      export ANTHROPIC_SMALL_FAST_MODEL="${MLX_SMALL_MODEL:-${MLX_MODEL:-Qwen3.6-35B}}"
      ;;
    *) fail "未知 provider: $1"; exit 2 ;;
  esac
}

provider_summary() {
  if [[ -z "${ANTHROPIC_BASE_URL:-}" ]]; then
    info "Provider = Claude Official（base_url 未改，用默认 Anthropic 登录 / ANTHROPIC_API_KEY）"
  else
    local tok="${ANTHROPIC_AUTH_TOKEN:-${ANTHROPIC_API_KEY:-}}"
    local masked="<未设>"; [[ -n "$tok" ]] && masked="****${tok: -4}"
    info "Provider env 已导出："
    info "  ANTHROPIC_BASE_URL         = $ANTHROPIC_BASE_URL"
    info "  ANTHROPIC_MODEL            = ${ANTHROPIC_MODEL:-<provider 默认>}"
    info "  ANTHROPIC_SMALL_FAST_MODEL = ${ANTHROPIC_SMALL_FAST_MODEL:-<provider 默认>}"
    info "  ANTHROPIC_AUTH_TOKEN       = $masked"
  fi
}

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

交互式 Agent Team 启动器。等价于 slash command \`/agf-team-start <feature>\`，
但提供 teammate 多选菜单与运行时预检。

OPTIONS
  -h, --help        显示本帮助
      --dry-run     只打印拼好的 prompt，不启动 claude
      --skip-deps   跳过项目依赖体检（jq / docker / node / python 等）
      --provider NAME   指定启动 provider，跳过交互菜单。可选：
                        claude | minimax | deepseek | volcengine | qwen | mlx_qwen
      --dangerously-skip-permissions
                    [opt-in，默认关闭] 跳过所有权限提示（自担风险）。默认不传：
                    lead 以 --agent product-lead 启动，权限基线 = PL 的 acceptEdits

WORKFLOW
  1. 预检（claude CLI、版本、Agent Teams env、git 仓库、agents 目录）
  2. 输入 feature 描述
  3. 从 .claude/agents/ 动态列出 teammates（lead 固定为 ${LEAD_AGENT}）
  4. 多选 teammates
  5. 选择启动 provider / 模型（导出对应 ANTHROPIC_* env）
  6. exec claude --agent product-lead 并喂入 spawn prompt（PL = lead 主 session）

PROVIDER ENV（密钥从 shell env 读，脚本内无明文；端点/模型已内置默认，可同名 env 覆盖）
  claude      用现有登录 / ANTHROPIC_API_KEY（不改 base_url）
  deepseek    DEEPSEEK_API_KEY [+ DEEPSEEK_MODEL]
  minimax     MINIMAX_API_KEY [+ MINIMAX_ANTHROPIC_BASE_URL(国际默认/国内 api.minimaxi.com) / MINIMAX_MODEL]
  volcengine  ARK_API_KEY [+ ARK_MODEL / ARK_ANTHROPIC_BASE_URL]
  qwen        DASHSCOPE_API_KEY [+ QWEN_MODEL / DASHSCOPE_ANTHROPIC_BASE_URL]
  mlx_qwen    MLX_ANTHROPIC_BASE_URL(本地 Anthropic 兼容代理) [+ MLX_MODEL]

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
    --provider) PROVIDER_OPT="${2:-}"; shift 2 ;;
    --provider=*) PROVIDER_OPT="${1#*=}"; shift ;;
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
if tui_capable; then
  # TUI 路径：tui_input 自带非空 + minlen(4) 重问，对齐文本路径 <4 拒的语义
  tui_input "  一句话描述要交付的 feature / task" 4
  FEATURE_DESC="$TUI_RESULT"
else
  # 文本菜单降级（管道 / CI / dumb 终端）——保留原行为
  printf "  ${C}一句话描述，回车确认：${N} "
  IFS= read -er FEATURE_DESC
  FEATURE_DESC="$(printf '%s' "$FEATURE_DESC" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if (( ${#FEATURE_DESC} < 4 )); then
    fail "描述过短（<4 字符），中止"
    exit 2
  fi
fi

# ---------- 2) 选 teammates ----------
hdr "2) 选择 teammates"
CHOSEN=()
if tui_capable; then
  # TUI 路径：方向键多选。把候选灌进库的入参全局，按下标重建 CHOSEN[]。
  TUI_ITEMS=("${AGENT_NAMES[@]}")
  TUI_LABELS=("${AGENT_DESCS[@]}")
  if tui_multiselect "选择 teammates（空格勾选 · a 全选 · n 全不选 · 回车确认 · q 退出）"; then
    for idx in $TUI_RESULT_IDX; do
      CHOSEN+=("${AGENT_NAMES[$idx]}")
    done
  else
    # q/Esc 取消 → 等同文本菜单里的 'q'
    info "已退出"
    exit 0
  fi
else
  # 文本菜单降级（管道 / CI / dumb 终端）——保留原"输数字切换"循环
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

  for i in "${!AGENT_NAMES[@]}"; do
    (( selected[i] )) && CHOSEN+=("${AGENT_NAMES[$i]}")
  done
fi

if (( ${#CHOSEN[@]} == 0 )); then
  fail "未选择任何 teammate，中止"
  exit 2
fi
ok "已选 ${#CHOSEN[@]} 个 teammate: ${CHOSEN[*]}"

# ---------- 3) 选择启动 provider / 模型 ----------
hdr "3) 选择启动 provider / 模型"
if [[ -n "$PROVIDER_OPT" ]]; then
  case " ${PROVIDER_KEYS[*]} " in
    *" $PROVIDER_OPT "*) PROVIDER_CHOICE="$PROVIDER_OPT" ;;
    *) fail "未知 --provider: ${PROVIDER_OPT}（可选：${PROVIDER_KEYS[*]}）"; exit 2 ;;
  esac
  ok "Provider（--provider 指定）：$PROVIDER_CHOICE"
elif tui_capable; then
  # TUI 路径：方向键单选。PROVIDER_KEYS 灌入参值，provider_label 各项灌描述。
  TUI_ITEMS=("${PROVIDER_KEYS[@]}")
  TUI_LABELS=()
  for k in "${PROVIDER_KEYS[@]}"; do TUI_LABELS+=("$(provider_label "$k")"); done
  if tui_select "选择启动 provider / 模型（↑/↓ 移动 · 回车确认 · q 取消）"; then
    PROVIDER_CHOICE="$TUI_RESULT"
  else
    # 取消（q/Esc）→ 沿用文本路径默认语义：claude 官方
    # 注：此处取消(q/Esc)≠teammate 多选的 exit——provider 有零配置安全默认(claude)，
    #     故取消即降级到默认继续，与文本路径"回车默认 1=claude"语义一致；teammate 无安全
    #     默认故取消=退出。两者语义刻意不同，非 bug。
    PROVIDER_CHOICE="claude"
    warn "未选择 provider，默认 claude 官方"
  fi
  ok "Provider：$PROVIDER_CHOICE"
else
  # 文本菜单降级（管道 / CI / dumb 终端）——保留原编号菜单循环
  for i in "${!PROVIDER_KEYS[@]}"; do
    printf "  %d) %s\n" "$((i+1))" "$(provider_label "${PROVIDER_KEYS[$i]}")"
  done
  while true; do
    printf "  ${C}选择 provider 编号 [默认 1=claude]：${N} "
    IFS= read -er psel
    psel="${psel:-1}"
    if [[ "$psel" =~ ^[0-9]+$ ]] && (( psel >= 1 && psel <= ${#PROVIDER_KEYS[@]} )); then
      PROVIDER_CHOICE="${PROVIDER_KEYS[$((psel-1))]}"
      break
    fi
    warn "请输入 1-${#PROVIDER_KEYS[@]}"
  done
  ok "Provider：$PROVIDER_CHOICE"
fi
apply_provider "$PROVIDER_CHOICE"
provider_summary

# ---------- 4) 拼装 prompt ----------
# 纯透传：feature 描述 + teammate 标记。如何解读 [teammates: ...] 标记由
# .claude/commands/agf-team-start.md "Teammate 选择规则" 节定义（SSOT）。
TEAMMATE_CSV="$(IFS=','; echo "${CHOSEN[*]}")"
PROMPT="/agf-team-start ${FEATURE_DESC}
[teammates: ${TEAMMATE_CSV}]"

hdr "4) 即将发送的 prompt"
echo "$PROMPT"

if (( DRY_RUN == 1 )); then
  hdr "Dry run — 不启动 claude"
  (( SKIP_PERMS == 1 )) && info "(若实际启动会附加 --dangerously-skip-permissions)"
  exit 0
fi

# ---------- 5) launch ----------
hdr "5) 启动 claude..."
# PL 作为 Agent Team lead，以 `--agent product-lead` 启动主 session：其 frontmatter
# （permissionMode: acceptEdits / skills / memory）走 --agent 路径全生效，团队权限
# 基线 = PL 的 acceptEdits；teammate 继承该基线，reviewer 等需更严模式时由 lead 在
# spawn 后对单个 teammate 单独切换。前提：product-lead.md 的 tools 含 Agent。
# 默认不再透传 --dangerously-skip-permissions；仅在显式传该 flag 时才跳过所有权限提示。
LAUNCH_ARGS=(--agent "$LEAD_AGENT")
if (( SKIP_PERMS == 1 )); then
  warn "已显式启用 --dangerously-skip-permissions：claude 将跳过所有权限提示，自担风险"
  LAUNCH_ARGS+=(--dangerously-skip-permissions)
fi
info "启动：claude ${LAUNCH_ARGS[*]} <prompt>"
# spinner 仅在 TUI 可用时起（非 dry-run：dry-run 已在上方 exit 0，不会到这）。
# 关键：exec 替换进程、不触发 EXIT trap → spinner 子进程不会被 trap 自动停，
# 必须在 exec 那行之前手动 tui_spinner_stop，否则后台子进程残留 + 光标乱。
if tui_capable; then
  tui_spinner_start "🚀 启动 claude 中…"
  tui_spinner_stop
fi
exec claude "${LAUNCH_ARGS[@]}" "$PROMPT"
