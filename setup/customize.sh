#!/usr/bin/env bash
# customize.sh — 选装工具：从 AgentForge 模板里裁剪不需要的角色 / skill / 命令。
#
# 用法：
#   bash setup/customize.sh                              # 等价于 --help
#   bash setup/customize.sh --preset web-only            # 纯 Web：去 Apple 4 角色 + 小程序 3 角色 + 对应轨道资产（推荐默认）
#   bash setup/customize.sh --preset minimal             # 只移除小程序三件套（Web + Apple 项目用）
#   bash setup/customize.sh --preset miniapp-only        # 仅保留小程序链路（移除 Web 执行层）
#   bash setup/customize.sh --preset web-only --drop-postlaunch --yes   # 再去 post-launch 三角色（19→9）
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
# - 删 .claude/agents/<name>.md，并同步删 roles.yaml 条目
#   + 重跑 gen-roles.py 再生成 team-roles.md 能力表（否则 gen-roles file-set 校验
#   会让目标项目所有后续 commit 被 pre-commit 硬阻断）
# - 不修改 standards / CLAUDE.md / docs/ —— 完事后会列出残留引用让用户人工清理
# - git tracked 文件用 git rm；untracked 用 rm
# - 文件不存在时静默跳过（幂等）

set -uo pipefail

# 本脚本位于 setup/，内部用相对路径（.claude/agents/ 等）→ 先 cd 到项目根，无论从哪调用都对
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

# 颜色（AGF_FORCE_COLOR=1 时管道内也保色，供上层编排脚本透传）
if [[ -t 1 || "${AGF_FORCE_COLOR:-}" == "1" ]]; then
  R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[0;33m'; B=$'\033[0;34m'; D=$'\033[0;90m'; N=$'\033[0m'
else
  R= G= Y= B= D= N=
fi

CORE_AGENTS=(product-lead tech-lead code-reviewer qa-engineer)
PRESET_MINIMAL=(miniapp-dev miniapp-code-reviewer miniapp-qa-engineer)
PRESET_MINIAPP_ONLY=(frontend-dev backend-dev ai-agent-dev ml-engineer)
APPLE_AGENTS=(apple-dev apple-code-reviewer apple-qa-engineer apple-release-engineer)
POSTLAUNCH_AGENTS=(growth-analyst content-writer ml-engineer)
# Apple 轨附属资产（agent 之外按轨联删，ADR-026 D4；轨道文件边界清晰、机械可删）
APPLE_EXTRAS=(.claude/standards/apple-native.md
  .claude/skills/agf-running-apple-sit
  .claude/skills/agf-wiring-apple-llm
  .claude/skills/agf-releasing-apple
  .claude/commands/agf-apple-release.md)
# Note: uiux-designer is NOT removed — designer covers Web / MiniApp / Apple Mode (see standards/miniapp.md §9)

DRY_RUN=1   # default: dry-run
TARGETS=()
PRESET=""
ALSO_REMOVE_MINIAPP_STANDARD=0
ALSO_REMOVE_APPLE_TRACK=0
DROP_POSTLAUNCH=0
ORIGINAL_ARGS=("$@")  # preserve for re-run hint

show_help() {
  cat <<EOF
${B}customize.sh${N} — 选装 AgentForge 角色

${B}Usage:${N}
  bash setup/customize.sh [--preset <name> | --remove <agent>...] [--yes] [--dry-run]
  bash setup/customize.sh --help

${B}Presets:${N}
  ${G}web-only${N}       纯 Web 项目（推荐默认）：去 Apple 4 角色 + 小程序 3 角色
                  + 联删轨道资产（apple-native.md / 3 个 apple skill / agf-apple-release 命令 / miniapp.md），19→12
  ${G}minimal${N}        移除小程序三件套：${PRESET_MINIMAL[*]}
                  + 删除 .claude/standards/miniapp.md
  ${G}miniapp-only${N}   仅保留小程序链路，移除 Web 执行层（共 4 个；uiux-designer 保留兜底小程序设计）：${PRESET_MINIAPP_ONLY[*]}

${B}Custom:${N}
  --remove <agent>...   按名移除指定 agent，可空格分隔多个

${B}Flags:${N}
  --drop-postlaunch  连带移除 post-launch 三角色：${POSTLAUNCH_AGENTS[*]}（可叠加任意 preset）
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
    --drop-postlaunch) DROP_POSTLAUNCH=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --preset)
      PRESET="$2"
      case "$PRESET" in
        web-only)
          TARGETS+=("${PRESET_MINIMAL[@]}" "${APPLE_AGENTS[@]}")
          ALSO_REMOVE_MINIAPP_STANDARD=1
          ALSO_REMOVE_APPLE_TRACK=1
          ;;
        minimal)
          TARGETS+=("${PRESET_MINIMAL[@]}")
          ALSO_REMOVE_MINIAPP_STANDARD=1
          ;;
        miniapp-only)
          TARGETS+=("${PRESET_MINIAPP_ONLY[@]}")
          ;;
        *)
          echo "${R}❌${N} Unknown preset: $PRESET"
          echo "Available: web-only, minimal, miniapp-only"
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

if [[ $DROP_POSTLAUNCH -eq 1 ]]; then
  TARGETS+=("${POSTLAUNCH_AGENTS[@]}")
fi

# 去重（preset 与 --drop-postlaunch 可能重叠，如 ml-engineer；bash 3.2 无关联数组）
DEDUPED=()
for agent in ${TARGETS[@]+"${TARGETS[@]}"}; do
  seen=0
  for d in ${DEDUPED[@]+"${DEDUPED[@]}"}; do [[ "$d" == "$agent" ]] && seen=1 && break; done
  [[ $seen -eq 0 ]] && DEDUPED+=("$agent")
done
TARGETS=(${DEDUPED[@]+"${DEDUPED[@]}"})

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
  for f in ".claude/agents/${agent}.md"; do
    if [[ -f "$f" ]]; then
      echo "  ${R}-${N} $f"
      PLANNED+=("$f")
    else
      echo "  ${D}-${N} $f ${D}(已不存在，跳过)${N}"
    fi
  done
  if grep -q "^- name: ${agent}\$" .claude/agents/roles.yaml 2>/dev/null; then
    echo "  ${R}-${N} .claude/agents/roles.yaml 条目：${agent} ${D}(能力 SSOT 同步)${N}"
  fi
done

if [[ $ALSO_REMOVE_MINIAPP_STANDARD -eq 1 ]]; then
  if [[ -f ".claude/standards/miniapp.md" ]]; then
    echo "  ${R}-${N} .claude/standards/miniapp.md ${D}(preset 附带)${N}"
    PLANNED+=(".claude/standards/miniapp.md")
  fi
fi

if [[ $ALSO_REMOVE_APPLE_TRACK -eq 1 ]]; then
  for f in "${APPLE_EXTRAS[@]}"; do
    if [[ -e "$f" ]]; then
      echo "  ${R}-${N} $f ${D}(Apple 轨附带，ADR-026 D4)${N}"
      PLANNED+=("$f")
    fi
  done
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
  if [[ -d "$f" ]]; then
    if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
      git rm -rq "$f" && echo "  ${G}git rm -r${N} $f"
    else
      rm -r "$f" && echo "  ${G}rm -r${N} $f"
    fi
  elif git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    git rm -q "$f" && echo "  ${G}git rm${N} $f"
  else
    rm "$f" && echo "  ${G}rm${N}    $f"
  fi
done

# 同步 roles.yaml（能力 SSOT，防 gen-roles file-set 校验阻断后续 commit）：
# 文本级块删除保注释/格式（yaml round-trip 会毁注释）——条目是顶格 `- name: <agent>`，
# 删到下一个顶格 `- name:` / 顶层 key 为止；随后重跑 gen-roles.py 再生成 team-roles.md 两表。
echo
echo "${B}=== 同步 roles.yaml（能力 SSOT） ===${N}"
ROLES_YAML=".claude/agents/roles.yaml"
if [[ -f "$ROLES_YAML" ]]; then
  for agent in "${TARGETS[@]}"; do
    if grep -q "^- name: ${agent}\$" "$ROLES_YAML"; then
      awk -v target="$agent" '
        $0 == "- name: " target { skip = 1; next }
        skip && (/^- name: / || /^[A-Za-z_]+:/) { skip = 0 }
        !skip { print }
      ' "$ROLES_YAML" > "${ROLES_YAML}.tmp" && mv "${ROLES_YAML}.tmp" "$ROLES_YAML"
      echo "  ${G}yaml${N}  移除条目：${agent}"
    fi
  done
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' 2>/dev/null; then
    if python3 .claude/scripts/gen-roles.py >/dev/null 2>&1; then
      echo "  ${G}gen${N}   已重新生成 team-roles.md 能力表"
    else
      echo "  ${Y}⚠${N}  gen-roles.py 再生成失败——手动跑：python3 .claude/scripts/gen-roles.py"
    fi
    if python3 .claude/scripts/gen-roles.py --check >/dev/null 2>&1; then
      echo "  ${G}✅${N} gen-roles.py --check 通过（roles SSOT 已收敛，commit 不会被 pre-commit 阻断）"
    else
      echo "  ${R}❌${N} gen-roles.py --check 未通过——commit 会被 pre-commit 阻断，先手动修复："
      python3 .claude/scripts/gen-roles.py --check 2>&1 | head -8 | sed 's/^/      /'
    fi
  else
    echo "  ${Y}⚠${N}  缺 python3/PyYAML，跳过再生成；commit 前手动跑 gen-roles.py 收敛 SSOT"
  fi
else
  echo "  ${D}（无 roles.yaml，跳过）${N}"
fi

# Find dangling refs
echo
echo "${B}=== 残留引用扫描（手动清理） ===${N}"
DANGLING_FOUND=0
for agent in "${TARGETS[@]}"; do
  hits=$(grep -rln "\\b${agent}\\b" --include="*.md" --include="*.json" --include="*.yml" --include="*.yaml" \
    .claude/agents .claude/standards .claude/rules .claude/commands .claude/skills .claude/hooks docs CLAUDE.md README.md CHANGELOG.md \
    2>/dev/null | sort -u)
  if [[ -n "$hits" ]]; then
    DANGLING_FOUND=1
    echo "  ${Y}⚠${N}  仍有引用 ${R}${agent}${N}："
    echo "$hits" | sed 's/^/      /'
  fi
done

if [[ $ALSO_REMOVE_APPLE_TRACK -eq 1 ]]; then
  hits=$(grep -rln "apple-native\\.md\\|agf-running-apple-sit\\|agf-wiring-apple-llm\\|agf-releasing-apple\\|agf-apple-release" --include="*.md" \
    .claude docs CLAUDE.md README.md 2>/dev/null | sort -u)
  if [[ -n "$hits" ]]; then
    DANGLING_FOUND=1
    echo "  ${Y}⚠${N}  仍有引用 ${R}Apple 轨资产${N}："
    echo "$hits" | sed 's/^/      /'
  fi
fi

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
echo "  2. 跑 ${B}git diff${N} 检查 .claude/agents/ 与 roles.yaml 的删除是否符合预期"
echo "  3. 满意后 ${B}git commit${N} 提交此次定制"
