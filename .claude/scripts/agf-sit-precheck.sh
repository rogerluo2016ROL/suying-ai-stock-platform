#!/usr/bin/env bash
# agf-sit-precheck.sh — SIT 证据机器预检（advisory，ADR-011 决策 2）
#
# 把 code-reviewer 的 SIT Audit 4 项检查里**机械**的部分自动 flag，让 reviewer 聚焦：
#   ① 无 **SIT 证据** 段 / 段内无 AC 行
#   ② fail/blocked AC 行缺命令+输出证据（疑似 placeholder）
#   ③ pass AC 行却含失败信号 token（AssertionError / FAILED / Traceback… 疑似 mismark）
#   ④ 质量门标 SIT ✅ 但同段有 AC 标 fail/blocked（矛盾）
#
# **advisory，不阻断**：exit 0（无论有无 flag），仅用法/文件错误 exit 1。
# reviewer 仍做 4 项人工 audit + 3 档 verdict 裁决（本脚本不替代判断，只做机械初筛）。
# dev 可在 SendMessage 前自跑早暴露；code-reviewer 作为 SIT Audit step 0 跑。
#
# 用法：bash .claude/scripts/agf-sit-precheck.sh <progress-file>
# 格式权威：.claude/standards/ac-lifecycle.md「完整条目格式」**SIT 证据** 段。

set -uo pipefail

FILE="${1:-}"
if [[ -z "$FILE" ]]; then
  echo "用法: agf-sit-precheck.sh <progress-file>" >&2
  exit 1
fi
if [[ ! -f "$FILE" ]]; then
  echo "✗ 文件不存在: $FILE" >&2
  exit 1
fi

awk '
function flush_ac() {
  if (ac_line > 0) {
    if (ac_status == "fail" && have_evidence == 0) {
      printf("⚠️  [SIT-PRECHECK] L%d fail/blocked AC 缺命令+输出证据（疑似 placeholder）: %s\n", ac_line, ac_text) > "/dev/stderr"
      flags++
    }
    if (ac_status == "pass" && ac_text ~ /(AssertionError|TypeError|ValueError|KeyError|FAILED|Traceback|panic)/) {
      printf("⚠️  [SIT-PRECHECK] L%d AC 标 pass 但行内含失败信号 token（疑似 mismark）: %s\n", ac_line, ac_text) > "/dev/stderr"
      flags++
    }
  }
  ac_line=0; ac_status=""; ac_text=""; have_evidence=0
}
/\*\*SIT 证据\*\*/ { flush_ac(); in_sit=1; sit_seen=1; block_any_fail=0; next }
/\*\*质量门\*\*/ {
  flush_ac(); in_sit=0
  if ($0 ~ /SIT[[:space:]]*✅/ && block_any_fail==1) {
    printf("⚠️  [SIT-PRECHECK] L%d 质量门标 SIT ✅ 但同段有 AC fail/blocked（矛盾）\n", NR) > "/dev/stderr"
    flags++
  }
  block_any_fail=0; next
}
in_sit==1 && /^[[:space:]]*\*\*[^*]+\*\*/ { flush_ac(); in_sit=0 }
in_sit==1 && /^## / { flush_ac(); in_sit=0 }
in_sit==1 {
  is_ac = ($0 ~ /AC-?[0-9]/ && ($0 ~ /\[[ xX]\]/ || $0 ~ /(✅|❌|⚠)/))
  if (is_ac && !($0 ~ /命令:|输出:/)) {
    flush_ac()
    ac_line=NR; ac_count++; ac_text=$0
    if ($0 ~ /❌/ || $0 ~ /⚠/ || $0 ~ /\[ \]/) { ac_status="fail"; block_any_fail=1 }
    else if ($0 ~ /✅/ || $0 ~ /\[[xX]\]/) { ac_status="pass" }
    else { ac_status="unknown" }
  } else if ($0 ~ /(命令:|输出:|\$ |pytest|curl |psql|vitest|docker)/) {
    have_evidence=1
  }
}
END {
  flush_ac()
  if (sit_seen==0) { print "⚠️  [SIT-PRECHECK] 未找到 **SIT 证据** 段" > "/dev/stderr"; flags++ }
  else if (ac_count==0) { print "⚠️  [SIT-PRECHECK] **SIT 证据** 段无 AC 行" > "/dev/stderr"; flags++ }
  if (flags==0)
    print "✅ [SIT-PRECHECK] 无机械问题；reviewer 仍需做 SIT Audit 4 项人工检查 + 3 档 verdict"
  else
    printf("— 共 %d 个 flag（advisory 非阻断）；reviewer 聚焦上列后做 4 项人工 audit 裁决\n", flags) > "/dev/stderr"
}
' "$FILE"

exit 0
