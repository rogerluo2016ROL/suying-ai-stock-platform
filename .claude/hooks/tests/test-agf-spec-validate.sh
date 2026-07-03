#!/usr/bin/env bash
# test-agf-spec-validate.sh — 回归测试 agf-spec-validate.sh（ADR-012）
# 跑法：bash .claude/hooks/tests/test-agf-spec-validate.sh
# 退出码：0 = 全过；1 = 至少一个 case 不符。由 lint-all.sh / init-team.sh 自动发现执行。

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCRIPT="$REPO_ROOT/.claude/scripts/agf-spec-validate.sh"

PASS=0
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ok()  { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

# run <name> <mode:has|clean> <pattern> <content>
run() {
  local name="$1" mode="$2" pat="$3" content="$4"
  local f="$TMP/s.md" out rc
  printf '%s\n' "$content" > "$f"
  set +e
  out=$(bash "$SCRIPT" "$f" 2>&1); rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then bad "$name (advisory 应 exit 0，got $rc)"; return; fi
  case "$mode" in
    has)   echo "$out" | grep -qF "$pat" && ok "$name" || bad "$name (缺 flag: $pat)";;
    clean) echo "$out" | grep -qF "格式合法" && ! echo "$out" | grep -q "⚠️" && ok "$name" || bad "$name (应 clean)";;
  esac
}

echo "=== agf-spec-validate.sh test ==="

run "clean: 合法活规格" clean "" \
'# Spec: demo

## Requirements

### Requirement: 行为

The system MUST 做某事.

#### Scenario: 场景
- WHEN x
- THEN y'

run "clean: 合法 delta（四段）" clean "" \
'# Delta: demo

## ADDED Requirements
### Requirement: 新
The system MUST a.
#### Scenario: s
- WHEN x
- THEN y

## REMOVED Requirements
### Requirement: 旧
**Reason**: r
**Migration**: m

## RENAMED Requirements
- FROM: `### Requirement: 甲`
- TO: `### Requirement: 乙`'

run "flag: requirement 无 scenario" has "无 #### Scenario" \
'# Spec: demo

## Requirements

### Requirement: 行为
The system MUST 做某事.'

run "flag: requirement 缺 MUST/SHALL" has "缺 MUST/SHALL" \
'# Spec: demo

## Requirements

### Requirement: 行为
这条没有规范性语言.
#### Scenario: s
- WHEN x
- THEN y'

run "flag: scenario 错级别（3个#）" has "恰好 4 个" \
'# Spec: demo

## Requirements

### Requirement: 行为
The system MUST x.
### Scenario: 错
- WHEN x'

run "flag: REMOVED 缺 Reason/Migration" has "**Reason**" \
'# Delta: demo

## REMOVED Requirements
### Requirement: 旧'

run "flag: RENAMED 缺 FROM/TO" has "RENAMED 段缺" \
'# Delta: demo

## RENAMED Requirements
（这里啥都没写）'

run "flag: scenario 缺 WHEN/THEN（不可测）" has "缺 WHEN/THEN" \
'# Spec: demo

## Requirements

### Requirement: 行为
The system MUST x.
#### Scenario: 空场景
- 这条既没有触发也没有结果'

run "clean: GIVEN/WHEN/THEN 场景合法" clean "" \
'# Spec: demo

## Requirements

### Requirement: 行为
The system MUST x.
#### Scenario: 三段式
- GIVEN 前置
- WHEN 触发
- THEN 结果'

run "flag: requirement 含模糊词（建议量化）" has "疑似模糊词" \
'# Spec: demo

## Requirements

### Requirement: 性能
The system MUST 快速 响应用户请求.
#### Scenario: s
- WHEN 请求到达
- THEN 返回结果'

run "clean: 量化表述不误报模糊词" clean "" \
'# Spec: demo

## Requirements

### Requirement: 性能
The system MUST 在 200ms 内返回响应.
#### Scenario: s
- WHEN 请求到达
- THEN 返回结果'

# 多文件入参（#14）：一次校验多个文件，各自出结论
f1="$TMP/a.md"; f2="$TMP/b.md"
printf '%s\n' '# Spec: a
## Requirements
### Requirement: A
The system MUST x.
#### Scenario: s
- WHEN x
- THEN y' > "$f1"
cp "$f1" "$f2"
set +e
out=$(bash "$SCRIPT" "$f1" "$f2" 2>&1); rc=$?
set -e
{ [[ "$rc" -eq 0 ]] && echo "$out" | grep -qF "a.md 格式合法" && echo "$out" | grep -qF "b.md 格式合法"; } \
  && ok "多文件入参各自校验" || bad "多文件入参（rc=$rc）"

echo "--- 用法 / 文件错误 ---"
set +e
bash "$SCRIPT" >/dev/null 2>&1; rc=$?
set -e
[[ "$rc" -eq 1 ]] && ok "无参数应 exit 1" || bad "无参数 expected exit 1 got $rc"
set +e
bash "$SCRIPT" "$TMP/nope.md" >/dev/null 2>&1; rc=$?
set -e
[[ "$rc" -eq 1 ]] && ok "文件不存在应 exit 1" || bad "文件不存在 expected exit 1 got $rc"

echo
if [[ $FAIL -eq 0 ]]; then
  echo "=> 全部 $PASS 个用例通过"
  exit 0
else
  echo "=> $FAIL 个用例失败 / $PASS 个通过"
  exit 1
fi
