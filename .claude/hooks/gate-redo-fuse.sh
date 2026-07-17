#!/usr/bin/env bash
# gate-redo-fuse.sh
#
# TaskCreated hook — 回派熔断（补评审 A-F3）。
#
# 背景：task 被 reviewer 打回（code_verdict: block）或 SIT Audit 打回（Redo SIT）后，
#       product-lead 重派 dev 改 → 再 review → 再 block …… AGF 无熔断计数，理论上可
#       无限循环回派（dev 改 → block → dev 改 → block），浪费 token + 暴露更深层问题
#       （架构 / 需求模糊 / 技能差距）却无机制发现"卡死循环"。
#
# 机制：TaskCreated 时，从 task 描述抽 feature slug（docs/changes/<slug>/ 或
#       docs/reviews/<slug>-），数 docs/reviews/<slug>-*.md 里 blocking 报告数
#       （code_verdict: block 或 sit_audit_verdict: Redo SIT）。≥ 阈值（默认 3，
#       env AGF_REDO_FUSE_LIMIT）→ exit 2 + 升级 tech-lead 提示，除非 task 描述含
#       `熔断豁免:` 归因行（同 gate-deploy-release-auth 的 sentinel 模式）。
#
# 行为（保守 fail-open）：
#   - description 缺失 / 解析失败 → exit 0
#   - 抽不到 feature slug → exit 0（无法判定 feature，fail-open；PL 若故意省略 slug 可绕过——
#     同 gate-deploy-release-auth 的诚实限制类，真正 loop 检测靠描述诚实引用变更文件夹）
#   - docs/reviews/ 不存在 / 该 feature 0 blocking 报告 → exit 0
#   - blocking 数 < 阈值 → exit 0
#   - blocking 数 ≥ 阈值 + 已含 `熔断豁免:` → exit 0（PL 显式归因，如「tech-lead 已诊断」）
#   - blocking 数 ≥ 阈值 + 无豁免 → exit 2 + stderr 升级指引
#
# 注册位置：.claude/settings.json → hooks.TaskCreated（与 validate-task-schema /
#           gate-deploy-release-auth 同 matcher 并列）。属团队协调类（可降级，ADR-014 profile）。
# 诚实限制：PL 可省略 slug 绕过 + 可伪造 `熔断豁免:` 行（同 ADR-019 类别，主 session 全工具权限）。
#          本 hook 是 loop 检测 + 强制升级归因层，非硬门。决策 + 限制详 ADR-020。

set -uo pipefail

INPUT=$(cat || true)

# 公共提取/归因辅助（去重，见 agf-task-hook.lib.sh）；缺 lib / 缺 jq → fail-open exit 0
_HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$_HOOK_DIR/agf-task-hook.lib.sh" ] && source "$_HOOK_DIR/agf-task-hook.lib.sh"
command -v agf_task_desc >/dev/null 2>&1 || exit 0

DESC=$(agf_task_desc "$INPUT")
[[ -z "${DESC:-}" ]] && exit 0

# 1) 抽 feature slug（先 docs/changes/<slug>/，后 docs/reviews/<slug>-）
SLUG=$(printf '%s' "$DESC" | grep -oE 'docs/changes/[a-z0-9][a-z0-9-]+' | head -1 | sed 's#docs/changes/##' || true)
if [[ -z "$SLUG" ]]; then
  SLUG=$(printf '%s' "$DESC" | grep -oE 'docs/reviews/[a-z0-9][a-z0-9-]+-' | head -1 | sed 's#docs/reviews/##; s#-$##' || true)
fi
[[ -z "${SLUG:-}" ]] && exit 0  # 抽不到 slug → fail-open

# 2) 数 blocking 报告（pattern 同 agf-verdict.py _collect_files；排除 _TEMPLATE / retro-）
LIMIT="${AGF_REDO_FUSE_LIMIT:-3}"
REVIEW_DIR="${AGF_REVIEW_DIR:-docs/reviews}"
BLOCK_COUNT=0

if [[ -d "$REVIEW_DIR" ]]; then
  shopt -s nullglob
  files=()
  for f in "$REVIEW_DIR"/"$SLUG"-*.md; do
    # 排除模板 / retro（子串语义，对齐 agf-verdict.py _collect_files 的 `ex in base`）
    case "$(basename "$f")" in
      *_TEMPLATE*|*retro-*) continue ;;
    esac
    files+=("$f")
  done
  shopt -u nullglob

  for f in "${files[@]}"; do
    # frontmatter 字段在行首；field 名唯一不会出现在正文散文里
    if grep -qE '^code_verdict:[[:space:]]*block\b' "$f" 2>/dev/null \
       || grep -qE '^sit_audit_verdict:[[:space:]]*Redo SIT\b' "$f" 2>/dev/null; then
      BLOCK_COUNT=$((BLOCK_COUNT+1))
    fi
  done
fi

# 3) 未达阈值 → 放行
if [[ "$BLOCK_COUNT" -lt "$LIMIT" ]]; then
  exit 0
fi

# 4) 已达阈值 + 含「熔断豁免:」归因行 → 放行（PL 显式归因，容全角冒号 / 行内 / 列表项）
if agf_has_attribution "$DESC" 熔断豁免; then
  exit 0
fi

# 5) 达阈值 + 无豁免 → 阻断 + 升级指引
cat >&2 <<EOF
❌ [gate-redo-fuse] 回派熔断 — feature「${SLUG}」已有 $BLOCK_COUNT 份 blocking 评审报告（阈值 ${LIMIT}），疑卡死循环。

连续 ≥ $LIMIT 次 block / Redo SIT 通常不是 dev 实现问题，而是更深层根因：
  • 架构方向错（tech-lead 重估技术选型 / 边界）
  • 需求 / AC 模糊或矛盾（product-lead 回变更文件夹澄清）
  • 技能 / 知识差距（换 dev 实例或补 skill）

勿再直接回派 dev 改。先升级 tech-lead 诊断根因（TaskCreate tech-lead 审 feature $SLUG 的阻塞根因）。
若 tech-lead 已诊断、确需继续回派，task 描述加一行显式归因（任一）：
  熔断豁免: tech-lead 已诊断根因（<结论>），按新指导重派
  熔断豁免: 上轮 block 为 X 类问题已修，本轮验证

诚实限制（ADR-020）：本 hook 是 loop 检测 + 升级归因层，非硬门；PL 可伪造豁免行。
阈值可调：AGF_REDO_FUSE_LIMIT=N（默认 3）。
EOF
exit 2
