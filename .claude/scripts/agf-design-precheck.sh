#!/usr/bin/env bash
# agf-design-precheck.sh — 设计纪律机器预检（advisory，ADR-013 决策 2）
#
# 把 code-reviewer「审美纪律审查项」第 1 项里**机械**的部分自动 flag，让 reviewer 聚焦人审：
#   ① 裸颜色 hex（应引用 DESIGN.md token）
#   ② 100vh / h-screen（应 min-h-[100dvh] / 100dvh，iOS Safari 地址栏跳动）
#   ③ code 内可见 emoji（当 icon 用 → 应改 lucide-react）
#   ④ font-family: Inter 作默认（应用 system-ui 栈或 Geist）
#   ⑤ AI 紫蓝渐变信号（from-indigo / to-violet / bg-purple 等，LLM 头号指纹）
#  ⑥ grid-cols-3 等高三卡信号（advisory，合法场景多，需人审）
#
# **advisory，不阻断**：exit 0（无论有无 flag），仅用法 / 路径错误 exit 1。
# reviewer 仍做 AI Tells 人审 + Design Read / motion 红线核（本脚本不替代判断，只做机械初筛）。
# uiux-designer 可在 SendMessage 前自跑早暴露；code-reviewer 作为审美审查 step 0 跑。
#
# 用法：bash .claude/scripts/agf-design-precheck.sh <feature-design-dir-or-file>
#   例：bash .claude/scripts/agf-design-precheck.sh docs/design/login/
#       bash .claude/scripts/agf-design-precheck.sh docs/design/login/index.html
# 规则 SSOT：.claude/skills/agf-design-discipline/SKILL.md §5 Pre-Flight Check。

set -uo pipefail

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "用法: agf-design-precheck.sh <feature-design-dir-or-file>" >&2
  echo "  扫 docs/design/[feature]/ 下的 .html / .tsx / .jsx / .css / .md" >&2
  exit 1
fi

if [[ -d "$TARGET" ]]; then
  FILES=$(find "$TARGET" -type f \( -name '*.md' -o -name '*.html' -o -name '*.tsx' -o -name '*.jsx' -o -name '*.css' \) 2>/dev/null)
elif [[ -f "$TARGET" ]]; then
  FILES="$TARGET"
else
  echo "✗ 路径不存在: $TARGET" >&2
  exit 1
fi

if [[ -z "$FILES" ]]; then
  echo "ℹ️  [DESIGN-PRECHECK] 目标无可扫文件（.md/.html/.tsx/.jsx/.css）: $TARGET" >&2
  exit 0
fi

flags=0

# 代码 / 样式文件（.md 是文档，含 hex 示例正常，hex/Inter/渐变只扫代码文件）
CODE_FILES=$(printf '%s\n' "$FILES" | grep -E '\.(html|tsx|jsx|css)$' || true)

scan() {
  # $1 label · $2 grep ERE · $3 files · $4 note
  local label="$1" pat="$2" fls="$3" note="$4"
  [[ -z "$fls" ]] && return
  local hits
  hits=$(printf '%s\n' "$fls" | xargs grep -nE "$pat" 2>/dev/null || true)
  if [[ -n "$hits" ]]; then
    printf "⚠️  [DESIGN-PRECHECK] %s 命中（%s · 需人审）:\n%s\n\n" "$label" "$note" "$hits" >&2
    flags=$((flags + 1))
  fi
}

# ① 裸颜色 hex（代码 / 样式文件）
scan "裸颜色 hex" '#[0-9A-Fa-f]{6}' "$CODE_FILES" "应引用 DESIGN.md token"

# ② 100vh / h-screen
scan "100vh / h-screen" '100vh|h-screen' "$CODE_FILES" "iOS Safari 地址栏跳动，用 min-h-[100dvh]"

# ④ Inter 作默认字体
scan "Inter 默认字体" 'font-family[^;}]*Inter' "$CODE_FILES" "用 system-ui 栈或 Geist"

# ⑤ AI 紫蓝渐变信号
scan "AI 紫蓝渐变信号" 'from-indigo|to-violet|from-purple|to-purple|bg-purple|via-purple' "$CODE_FILES" "LLM 头号指纹，中性基底 + 单一 accent"

# ⑥ 等高三卡信号（advisory，grid-cols-3 合法场景多，需人审）
scan "grid-cols-3 三卡信号" 'grid-cols-3' "$CODE_FILES" "若三张等高 feature 卡 → 非对称 / zig-zag / divide-y"

# ③ 可见 emoji（perl 跨平台 UTF-8；grep \x 在 BSD 不可靠）—— 只扫代码文件
# （.md 文档常含 emoji 作反例展示，如 DESIGN.md Do/Don't 表，扫 .md 会误报；spec.md 的 emoji 由 reviewer 人审第 2 项覆盖）
if command -v perl >/dev/null 2>&1 && [[ -n "$CODE_FILES" ]]; then
  emo_hits=$(printf '%s\n' "$CODE_FILES" | xargs perl -CSD -ne 'print "$ARGV:$.: $_" if /[\x{1F000}-\x{1FAFF}\x{2600}-\x{27BF}]/; close ARGV if eof' 2>/dev/null || true)
  if [[ -n "$emo_hits" ]]; then
    printf "⚠️  [DESIGN-PRECHECK] 可见 emoji 命中（当 icon 用 → 改 lucide-react；内容文案里的 emoji 需人审）:\n%s\n\n" "$emo_hits" >&2
    flags=$((flags + 1))
  fi
fi

if [[ "$flags" -eq 0 ]]; then
  echo "✅ [DESIGN-PRECHECK] 无机械信号命中；reviewer 仍需做 AI Tells 人审 + Design Read / motion 红线核（agf-design-discipline §4/§3）" >&2
else
  printf "— 共 %d 个 flag（advisory 非阻断）；reviewer 聚焦上列后做人审裁决\n" "$flags" >&2
fi

exit 0
