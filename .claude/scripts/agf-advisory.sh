#!/usr/bin/env bash
# agf-advisory.sh — advisory 机筛统一入口（ADR-026 D2）
#
# 一次调用串跑机械 advisory 预检（替代逐个跑，收敛认知面）：
#   ① agf-sit-precheck.sh <progress-file>    —— SIT 证据机筛（ADR-011 决策 2）
#   ② agf-design-precheck.sh <design-path>   —— 设计纪律机筛（ADR-013；仅传了第 2 参才跑）
#
# 定位：**dev 报告前跑一次；reviewer 不重跑**——advisory 不进 verdict，重复跑零增量
#（reviewer 的 SIT Audit 4 项人工检查与 3 档 verdict 裁决权不变）。
# 原 agf-wiring-check.sh（模块级"写了没接线"）已随 ADR-026 D2 退役；怀疑没接线时
# 手动走 /agf-code-map 的 codemap `orphans` 子命令。
#
# **advisory，不阻断**：恒 exit 0（无论有无 flag）；仅用法错误 exit 1。
# 用法：bash .claude/scripts/agf-advisory.sh <progress-file> [<design-dir-or-file>]

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -lt 1 ]]; then
  echo "用法: agf-advisory.sh <progress-file> [<design-dir-or-file>]" >&2
  exit 1
fi

echo "=== agf-advisory（advisory 机筛统一入口，永不阻断；ADR-026 D2）==="
bash "$SCRIPT_DIR/agf-sit-precheck.sh" "$1" || true

if [[ $# -ge 2 && -n "${2:-}" ]]; then
  echo
  bash "$SCRIPT_DIR/agf-design-precheck.sh" "$2" || true
fi

exit 0
