#!/usr/bin/env bash
# test-validate-task-schema.sh — 回归测试 validate-task-schema.sh
#
# 跑法：bash .claude/hooks/test-validate-task-schema.sh
# 退出码：0 = 全部通过；1 = 至少一个 case 不符合预期
#
# 由 init-team.sh 自动发现并执行。

set -uo pipefail

HOOK="$(dirname "$0")/../validate-task-schema.sh"

if [[ ! -x "$HOOK" ]]; then
  chmod +x "$HOOK" 2>/dev/null || true
fi

PASS=0
FAIL=0

run_case() {
  local name="$1" expected_exit="$2" payload="$3"
  local actual_exit
  set +e
  printf '%s' "$payload" | bash "$HOOK" >/dev/null 2>&1
  actual_exit=$?
  set -e
  if [[ "$actual_exit" -eq "$expected_exit" ]]; then
    echo "  ✅ $name (exit=$actual_exit)"
    PASS=$((PASS+1))
  else
    echo "  ❌ $name (expected=$expected_exit, actual=$actual_exit)"
    FAIL=$((FAIL+1))
  fi
}

echo "=== validate-task-schema.sh test ==="

# Case 1: 6 段齐全 → exit 0
run_case "6 段齐全应通过" 0 \
'{"tool_input":{"description":"任务描述: 实现登录\n任务类型: 新功能\n上下文: React + FastAPI\n上游产物: docs/prd/x.md\n验收标准: AC-1\n预期产物: src/Login.tsx"}}'

# Case 2: 缺"上游产物" → exit 2
run_case "缺上游产物应阻断" 2 \
'{"tool_input":{"description":"任务描述: 实现登录\n任务类型: 新功能\n上下文: React\n验收标准: AC-1\n预期产物: src/Login.tsx"}}'

# Case 3: 缺"预期产物" → exit 2
run_case "缺预期产物应阻断" 2 \
'{"tool_input":{"description":"任务描述: 实现登录\n任务类型: 新功能\n上下文: React\n上游产物: docs/prd/x.md\n验收标准: AC-1"}}'

# Case 4: 完全空 description → exit 2（其他 5 段都缺）
run_case "空 description 应阻断" 2 \
'{"tool_input":{"description":"任务描述: x"}}'

# Case 5: payload 没有 description 字段 → exit 0（保护现有流程，不误杀）
run_case "无 description 字段应放过" 0 \
'{"tool_input":{}}'

# Case 6: 完全空 input → exit 0
run_case "完全空 input 应放过" 0 \
''

# Case 7: description 在备用路径 .description → exit 0（6 段齐）
run_case "备用路径 .description 应被识别" 0 \
'{"description":"任务描述: x\n任务类型: 新功能\n上下文: x\n上游产物: x\n验收标准: x\n预期产物: x"}'

# Case 8: description 在备用路径 .task.description → exit 0（6 段齐）
run_case "备用路径 .task.description 应被识别" 0 \
'{"task":{"description":"任务描述: x\n任务类型: 新功能\n上下文: x\n上游产物: x\n验收标准: x\n预期产物: x"}}'

# Case 9: description 在备用路径 .tool_input.task.description → exit 0（6 段齐）
run_case "备用路径 .tool_input.task.description 应被识别" 0 \
'{"tool_input":{"task":{"description":"任务描述: x\n任务类型: 新功能\n上下文: x\n上游产物: x\n验收标准: x\n预期产物: x"}}}'

echo
if [[ $FAIL -eq 0 ]]; then
  echo "✅ 全部 $PASS 个用例通过"
  exit 0
else
  echo "❌ $FAIL 个用例失败 / $PASS 个通过"
  exit 1
fi
