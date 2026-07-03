#!/usr/bin/env bash
# customize.sh — 选装工具：从 AgentForge 模板里裁剪不需要的角色 / skill / 命令。
#
# 用法：
#   bash setup/customize.sh                              # 等价于 --help
#   bash setup/customize.sh --preset minimal             # 移除小程序三件套（仅 Web 项目用）
#   bash setup/customize.sh --preset miniapp-only        # 仅保留小程序链路（移除 Web 执行层）
#   bash setup/customize.sh --remove ml-engineer     # 移除指定 agent（可多个）
#   bash setup/customize.sh --remove agf-X agf-Y --yes   # 跳过确认直接执行
#   bash setup/customize.sh --dry-run --preset minimal   # 显式 dry-run（不写盘）
#
# 默认行为：dry-run（只打印，不删）。加 --yes 才实际删除。
#
# 不会动的（核心 4 件）：product-lead / tech-lead / code-reviewer / qa-engineer
# 这 4 个角色撑起整个交付链路骨架，强制移除会让团队失能。
#
# 安全行为：
# - 只删 .claude/agents/<name>.md 与对应 evals/<name>.jsonl
# - 不修改 standards / CLAUDE.md / docs/ —— 完事后会列出残留引用让用户人工清理
# - git tracked 文件用 git rm；untracked 用 rm
# - 文件不存在时静默跳过（幂等）

set -uo pipefail

# 本脚本位于 setup/，内部用相对路径（.claude/agents/ 等）→ 先 cd 到项目根，无论从哪调用都对
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

# 颜色（AGF_FORCE_COLOR=1 时管道内也保色，供 agf-install TUI 沟槽透传）
if [[ -t 1 || "${AGF_FORCE_COLOR:-}" == "1" ]]; then
  R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[0;33m'; B=$'\033[0;34m'; D=$'\033[0;90m'; N=$'\033[0m'
else
  R= G= Y= B= D= N=
fi

CORE_AGENTS=(product-lead tech-lead code-reviewer qa-engineer)
PRESET_MINIMAL=(miniapp-dev miniapp-code-reviewer miniapp-qa-engineer)
PRESET_MINIAPP_ONLY=(frontend-dev backend-dev ai-agent-dev ml-engineer)
# Note: uiux-designer is NOT removed — designer covers both Web and MiniApp Mode (see standards/miniapp.md §9)

DRY_RUN=1   # default: dry-run
TARGETS=()
PRESET=""
ALSO_REMOVE_MINIAPP_STANDARD=0
ORIGINAL_ARGS=("$@")  # preserve for re-run hint

show_help() {
  cat <<EOF
${B}customize.sh${N} — 选装 AgentForge 角色

${B}Usage:${N}
  bash setup/customize.sh [--preset <name> | --remove <agent>...] [--yes] [--dry-run]
  bash setup/customize.sh --help

${B}Presets:${N}
  ${G}minimal${N}        移除小程序三件套：${PRESET_MINIMAL[*]}
                  + 删除 .claude/standards/miniapp.md
  ${G}miniapp-only${N}   仅保留小程序链路，移除 Web 执行层（共 4 个；uiux-designer 保留兜底小程序设计）：${PRESET_MINIAPP_ONLY[*]}

${B}Custom:${N}
  --remove <agent>...   按名移除指定 agent，可空格分隔多个

${B}Flags:${N}
  --yes        跳过交互确认直接删
  --dry-run    显式 dry-run（默认就是；写来更清楚）
  --help       本帮助

${B}Examples:${N}
  bash setup/customize.sh --preset minimal              # 看会删什么（不删）
  bash setup/customize.sh --preset minimal --yes        # 真删
  bash setup/customize.sh --remove ml-engineer uiux-designer
  bash setup/customize.sh --remove ml-engineer --yes

${B}永远不能删的核心 4 件：${N}
  ${CORE_AGENTS[*]}
EOF
}

is_core() {
  local agent="$1"
  for c in "${CORE_AGENTS[@]}"; do
    [[ "$c" == "$agent" ]] && return 0
  done
  return 1
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) show_help; exit 0 ;;
    --yes) DRY_RUN=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --preset)
      PRESET="$2"
      case "$PRESET" in
        minimal)
          TARGETS+=("${PRESET_MINIMAL[@]}")
          ALSO_REMOVE_MINIAPP_STANDARD=1
          ;;
        miniapp-only)
          TARGETS+=("${PRESET_MINIAPP_ONLY[@]}")
          ;;
        *)
          echo "${R}❌${N} Unknown preset: $PRESET"
          echo "Available: minimal, miniapp-only"
          exit 2
          ;;
      esac
      shift 2
      ;;
    --remove)
      shift
      while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
        TARGETS+=("$1")
        shift
      done
      ;;
    *)
      echo "${R}❌${N} Unknown arg: $1"
      show_help
      exit 2
      ;;
  esac
done

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  show_help
  exit 0
fi

# Validate: no core agents
for agent in "${TARGETS[@]}"; do
  if is_core "$agent"; then
    echo "${R}❌ Refusing to remove core agent:${N} $agent"
    echo "   核心 4 件（${CORE_AGENTS[*]}）撑起整个交付链路，强制移除会让团队失能。"
    exit 1
  fi
done

# Plan
echo
if [[ $DRY_RUN -eq 1 ]]; then
  echo "${Y}=== DRY-RUN: 以下文件将被移除（加 --yes 才实际删除）===${N}"
else
  echo "${B}=== 即将移除以下文件 ===${N}"
fi
echo

PLANNED=()
for agent in "${TARGETS[@]}"; do
  for f in ".claude/agents/${agent}.md" "evals/${agent}.jsonl"; do
    if [[ -f "$f" ]]; then
      echo "  ${R}-${N} $f"
      PLANNED+=("$f")
    else
      echo "  ${D}-${N} $f ${D}(已不存在，跳过)${N}"
    fi
  done
done

if [[ $ALSO_REMOVE_MINIAPP_STANDARD -eq 1 ]]; then
  if [[ -f ".claude/standards/miniapp.md" ]]; then
    echo "  ${R}-${N} .claude/standards/miniapp.md ${D}(preset minimal 附带)${N}"
    PLANNED+=(".claude/standards/miniapp.md")
  fi
fi

if [[ ${#PLANNED[@]} -eq 0 ]]; then
  echo
  echo "${G}✅${N} 没有需要移除的文件（已经是目标状态）。"
  exit 0
fi

# Confirmation prompt
if [[ $DRY_RUN -eq 1 ]]; then
  echo
  echo "${Y}（这是 dry-run，无实际删除）${N}"
  echo "确认无误后跑：${B}bash setup/customize.sh ${ORIGINAL_ARGS[*]} --yes${N}"
  exit 0
fi

# Actually delete
echo
echo "${B}=== 执行删除 ===${N}"
for f in "${PLANNED[@]}"; do
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    git rm -q "$f" && echo "  ${G}git rm${N} $f"
  else
    rm "$f" && echo "  ${G}rm${N}    $f"
  fi
done

# Find dangling refs
echo
echo "${B}=== 残留引用扫描（手动清理） ===${N}"
DANGLING_FOUND=0
for agent in "${TARGETS[@]}"; do
  hits=$(grep -rln "\\b${agent}\\b" --include="*.md" --include="*.json" --include="*.yml" \
    .claude/standards .claude/rules .claude/commands .claude/skills .claude/hooks docs CLAUDE.md README.md CHANGELOG.md \
    2>/dev/null | sort -u)
  if [[ -n "$hits" ]]; then
    DANGLING_FOUND=1
    echo "  ${Y}⚠${N}  仍有引用 ${R}${agent}${N}："
    echo "$hits" | sed 's/^/      /'
  fi
done

if [[ $ALSO_REMOVE_MINIAPP_STANDARD -eq 1 ]]; then
  hits=$(grep -rln "miniapp\\.md\\|standards/miniapp" --include="*.md" \
    .claude docs CLAUDE.md README.md CHANGELOG.md 2>/dev/null | sort -u)
  if [[ -n "$hits" ]]; then
    DANGLING_FOUND=1
    echo "  ${Y}⚠${N}  仍有引用 ${R}standards/miniapp.md${N}："
    echo "$hits" | sed 's/^/      /'
  fi
fi

if [[ $DANGLING_FOUND -eq 0 ]]; then
  echo "  ${G}✅${N} 没有残留引用。"
fi

# Re-run validation
echo
echo "${B}=== 跑回归验证 ===${N}"
if [[ -f "setup/init-team.sh" ]]; then
  bash setup/init-team.sh 2>&1 | tail -5
fi

echo
echo "${G}=== 完成 ===${N}"
echo
echo "${B}Next:${N}"
echo "  1. 上面列出的残留引用需要人工 review（grep 后决定改写或删除整段）"
echo "  2. 跑 ${B}git diff${N} 检查 evals/ 与 .claude/agents/ 的删除是否符合预期"
echo "  3. 满意后 ${B}git commit${N} 提交此次定制"
