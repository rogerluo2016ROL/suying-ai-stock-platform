#!/usr/bin/env bash
# agf-deny-baseline.sh — settings.json permissions.deny 非回归门（对标 claude-code-harness
# selfaudit/baseline.go 的 DenyBaseline；补 AGF 缺的"deny 列表被悄悄改小"检测）。
#
# 威胁模型：agent / PR 把 .claude/settings.json 的 permissions.deny 条目删掉，
#           静默弱化"禁读 .env / ~/.ssh / Apple 签名材料 / eval"等硬边界。
#           block-config-edit.sh 只护 lint/format 配置，不护 deny 列表本身。
#
# 语义（与 harness 一致）：
#   - deny 是无序集合 → 排序 + 规范化后比对
#   - baseline ⊆ 当前 → 通过（新增 deny 放行，收紧永远 OK）
#   - baseline 有、当前缺 → 回归 → exit 2 + 列出被删条目
#   - baseline 文件自身完整性：重算 entries 的 sha256 对比 canonical_sha256，
#     不符 → baseline 被篡改 → exit 2（防绕过：改小 settings 同时改 baseline 也会被抓，
#     除非走 --update 显式重签）
#
# 用法：
#   bash .claude/scripts/agf-deny-baseline.sh            # 检查（CI / lint / hook）
#   bash .claude/scripts/agf-deny-baseline.sh --update   # 有意变更 deny 后，人工重签 baseline
#
# 退出码：0 = 通过 / 未初始化（fail-open advisory）；2 = 回归或 baseline 篡改（硬阻断）
#
# 保守 fail-open：settings.json 缺失 / jq 缺失 / baseline 未初始化 → exit 0 + WARN
#   （沿用 AGF roles-drift 门的优雅降级姿态，绝不因环境问题误杀）。

set -uo pipefail

SETTINGS=".claude/settings.json"
BASELINE=".claude/security/deny-baseline.json"
WARN_PREFIX="[deny-baseline] WARN —"
MODE="check"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE="check"; shift ;;   # 显式别名（默认即 check；repo-layout/ADR-023 文档写法）
    --update) MODE="update"; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# --- 环境降级检查（fail-open） ---
if ! command -v jq >/dev/null 2>&1; then
  echo "$WARN_PREFIX 缺 jq，跳过（brew install jq）" >&2
  exit 0
fi
if [[ ! -f "$SETTINGS" ]]; then
  echo "$WARN_PREFIX $SETTINGS 不存在，跳过" >&2
  exit 0
fi

# --- sha256 抽象（macOS shasum / linux sha256sum 兼容） ---
_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  else
    shasum -a 256 | awk '{print $1}'
  fi
}

# 当前 deny 条目（排序 + 每行一条的规范文本；空数组 → 空串）
CUR_ENTRIES=$(jq -r '(.permissions.deny // []) | sort | .[]' "$SETTINGS" 2>/dev/null || true)
CUR_SHA=$(printf '%s' "$CUR_ENTRIES" | _sha256)

# ============================ update 模式 ============================
if [[ "$MODE" == "update" ]]; then
  mkdir -p "$(dirname "$BASELINE")"
  # 用 jq 生成规范 JSON（entries 排序 + 记录 sha）
  jq -n \
    --arg sha "$CUR_SHA" \
    --argjson entries "$(jq '(.permissions.deny // []) | sort' "$SETTINGS")" \
    '{version:1, note:"AGF deny 非回归 baseline，改 deny 后跑 --update 重签", canonical_sha256:$sha, entries:$entries}' \
    > "$BASELINE"
  n=$(printf '%s\n' "$CUR_ENTRIES" | grep -c . || true)
  echo "✅ deny-baseline 已重签：$n 条 → $BASELINE"
  exit 0
fi

# ============================ check 模式 ============================
if [[ ! -f "$BASELINE" ]]; then
  echo "$WARN_PREFIX baseline 未初始化，跑 --update 生成：$BASELINE" >&2
  exit 0
fi

# baseline 完整性：重算 entries sha 对比记录值
BASE_ENTRIES=$(jq -r '(.entries // []) | sort | .[]' "$BASELINE" 2>/dev/null || true)
BASE_RECORDED_SHA=$(jq -r '.canonical_sha256 // ""' "$BASELINE" 2>/dev/null || true)
BASE_ACTUAL_SHA=$(printf '%s' "$BASE_ENTRIES" | _sha256)

if [[ -n "$BASE_RECORDED_SHA" && "$BASE_RECORDED_SHA" != "$BASE_ACTUAL_SHA" ]]; then
  echo "❌ deny-baseline 文件被篡改：entries 与 canonical_sha256 不符" >&2
  echo "   若为有意变更，请跑：bash .claude/scripts/agf-deny-baseline.sh --update" >&2
  exit 2
fi

# 回归检测：baseline 每条必须仍在当前 deny 中（子集检查）
MISSING=""
while IFS= read -r entry; do
  [[ -z "$entry" ]] && continue
  if ! printf '%s\n' "$CUR_ENTRIES" | grep -Fxq "$entry"; then
    MISSING+="   - $entry"$'\n'
  fi
done <<< "$BASE_ENTRIES"

if [[ -n "$MISSING" ]]; then
  echo "❌ deny 回归：以下 baseline 保护条目被从 $SETTINGS 删除：" >&2
  printf '%s' "$MISSING" >&2
  echo "   安全边界不得弱化。若确为有意变更，跑 --update 显式重签并在 PR 说明理由。" >&2
  exit 2
fi

# 新增条目 → advisory 提示（不阻断），提醒重签让 baseline 保持当前
ADDED=0
while IFS= read -r entry; do
  [[ -z "$entry" ]] && continue
  if ! printf '%s\n' "$BASE_ENTRIES" | grep -Fxq "$entry"; then
    ADDED=$((ADDED+1))
  fi
done <<< "$CUR_ENTRIES"

if [[ "$ADDED" -gt 0 ]]; then
  echo "✅ deny-baseline 无回归（当前新增 $ADDED 条，建议跑 --update 收录进 baseline）"
else
  echo "✅ deny-baseline 无回归"
fi
exit 0
