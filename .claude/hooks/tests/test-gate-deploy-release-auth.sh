#!/usr/bin/env bash
# test-gate-deploy-release-auth.sh — 回归测试 gate-deploy-release-auth.sh（A-F4，ADR-019）
#
# 跑法：bash .claude/hooks/tests/test-gate-deploy-release-auth.sh
# 退出码：0 = 全部通过；1 = 至少一个 case 不符合预期
#
# 由 init-team.sh / run-all-tests.sh / lint-all.sh 自动发现并执行。
#
# **测试构造纪律**：JSON 用单引号 + 字面 `\n`（合法 JSON 转义，2 字符），喂 hook 用
# `printf '%s'`（**禁用 echo**——zsh 的 echo 默认反转义，会把 JSON 里的 `\n` 变成真换行
# 制造非法 JSON → hook fail-open exit 0，假性通过）。同 test-validate-task-schema.sh 约定。

set -uo pipefail

HOOK="$(dirname "$0")/../gate-deploy-release-auth.sh"

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

echo "=== gate-deploy-release-auth.sh test（A-F4 部署/发布门授权归因）==="

# --- AC-1..3: deploy-engineer 派单 ---
# AC-1 非 deploy 任务 → 放行
run_case "非deploy任务放行" 0 \
'{"tool_input":{"description":"任务描述: 实现登录\n任务类型: 新功能\n上下文: src/auth/"}}'

# AC-2 deploy 派单（任务类型=部署 + 派 deploy-engineer）无授权 → 阻断
run_case "deploy派单无授权阻断" 2 \
'{"tool_input":{"description":"任务描述: 部署合并后main到UAT栈\n任务类型: 部署（deploy-only）\n派 deploy-engineer 把 main 部署到隔离栈+冒烟"}}'

# AC-3 deploy 派单 + 用户授权归因行 → 放行
run_case "deploy派单带用户授权放行" 0 \
'{"tool_input":{"description":"任务描述: 部署UAT\n任务类型: 部署\n派 deploy-engineer 部署隔离栈\n用户授权: /agf-deploy-uat login 已触发"}}'

# --- AC-4: 仅引用（非派单）→ fail-open ---
# qa 任务读 deploy-engineer 产的 UAT 栈，任务类型=测试、无「派 deploy-engineer」→ 放行
run_case "qa任务引用deploy-engineer放行（fail-open）" 0 \
'{"tool_input":{"description":"任务描述: 对UAT栈跑E2E\n任务类型: 测试\n上下文: UAT栈由deploy-engineer部署, URL见docs/deploy/login-uat.md"}}'

# --- AC-5..6: apple-release-engineer 派单 ---
# AC-5 apple 发布派单（任务类型=发布 + 派 + initial task）无授权 → 阻断
run_case "apple发布派单无授权阻断" 2 \
'{"tool_input":{"description":"任务描述: 构建签名DMG+公证\n任务类型: 发布\n派 apple-release-engineer fastlane match签名+notarytool公证\napple-release-engineer — initial task: 构建分发包"}}'

# AC-6 apple 发布 + 全角冒号「用户授权：」+ 列表项前缀 → 放行
run_case "apple发布带全角冒号授权放行" 0 \
'{"tool_input":{"description":"任务类型：签名分发\n派 apple-release-engineer 构建分发包\n- 用户授权：用户口头确认发布（2026-07-03）"}}'

# --- AC-7..8: 边界 fail-open ---
# AC-7 无 description 字段 → 放行（保护流程）
run_case "无description字段放行" 0 \
'{"tool_input":{}}'

# AC-8 任务类型=新功能、仅顺带提及 deploy-engineer（非派单）→ 放行
run_case "新功能任务顺带提及deploy放行（fail-open）" 0 \
'{"tool_input":{"description":"任务类型: 新功能\n上下文: 后端对接, deploy-engineer的UAT栈稍后用"}}'

# --- AC-9..10: 派单信号变体 ---
# AC-9 任务类型不含部署词，但显式 `deploy-engineer — initial task` → 派单信号 3b 命中 → 无授权阻断
run_case "initial-task派单短语无授权阻断" 2 \
'{"tool_input":{"description":"任务类型: bugfix\ndeploy-engineer — initial task: 起隔离栈+冒烟"}}'

# AC-10 apple 派单 + 半角冒号 + 行内授权 → 放行
run_case "apple派单半角冒号行内授权放行" 0 \
'{"tool_input":{"description":"任务类型: 发布\n派 apple-release-engineer 构建DMG\n上下文: 用户授权: 用户在Slack确认（2026-07-03）"}}'

# --- AC-11: 缺 jq → fail-open（不阻断）---
if ! command -v jq >/dev/null 2>&1; then
  run_case "缺jq放行（fail-open）" 0 \
'{"tool_input":{"description":"任务类型: 部署\n派 deploy-engineer"}}'
else
  echo "  ⏭️  缺jq用例跳过（本机有 jq，测不到该分支）"
  PASS=$((PASS+1))
fi

echo
# 汇总行刻意不带 ✅（lint-all.sh grep '✅' 计数用例，带 ✅ 会把汇总行算进去 off-by-one）
if [[ $FAIL -eq 0 ]]; then
  echo "=> 全部 $PASS 个用例通过"
  exit 0
else
  echo "=> $FAIL 个用例失败 / $PASS 个通过"
  exit 1
fi
