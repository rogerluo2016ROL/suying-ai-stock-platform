#!/usr/bin/env bash
# test-gate-redo-fuse.sh — 回归测试 gate-redo-fuse.sh（A-F3，ADR-020）
#
# 跑法：bash .claude/hooks/tests/test-gate-redo-fuse.sh
# 退出码：0 = 全部通过；1 = 至少一个 case 不符合预期
#
# 由 init-team.sh / run-all-tests.sh / lint-all.sh 自动发现并执行。
#
# **测试构造纪律**（同 test-gate-deploy-release-auth.sh）：
#   1) JSON 用 python3 生成（ground truth，真换行正确转义），喂 hook 用 `printf '%s'`——
#      禁用 echo（zsh echo 默认反转义，把 JSON 的 `\n` 变真换行造非法 JSON → hook fail-open 假性通过）。
#   2) env 变量（AGF_REVIEW_DIR / AGF_REDO_FUSE_LIMIT）必须放**管道右侧 bash 前**：
#      `printf ... | AGF_REVIEW_DIR=X bash hook`——放左侧只作用于 printf，hook 子进程拿不到。
#   3) 用临时 fixture 目录（mktemp）+ AGF_REVIEW_DIR 指向，不污染真 docs/reviews/。

set -uo pipefail

HOOK="$(dirname "$0")/../gate-redo-fuse.sh"

if [[ ! -x "$HOOK" ]]; then
  chmod +x "$HOOK" 2>/dev/null || true
fi

PASS=0
FAIL=0
FIXTURE=""

# 造一份 frontmatter 报告：mk_rep <dir> <filename> <code_verdict> <sit_verdict>
mk_rep() {
  local dir="$1" fn="$2" cv="$3" sv="$4"
  printf -- '---\nfeature: login\ndate: 2026-07-03\nreviewer: code-reviewer\ncode_verdict: %s\nsit_audit_verdict: %s\ncritical_count: 0\n---\n# body\n' "$cv" "$sv" > "$dir/$fn"
}

# run_case <expect> <name> <reviewdir> [limit] <description>
run_case() {
  local expect="$1" name="$2" reviewdir="$3" limit="$4" desc="$5"
  local payload
  payload=$(python3 -c "import json,sys; print(json.dumps({'tool_input':{'description':sys.argv[1]}}, ensure_ascii=False))" "$desc")
  local got
  set +e
  printf '%s' "$payload" | AGF_REVIEW_DIR="$reviewdir" AGF_REDO_FUSE_LIMIT="$limit" bash "$HOOK" >/dev/null 2>&1
  got=$?
  set -e
  if [[ "$got" -eq "$expect" ]]; then
    echo "  ✅ $name (exit=$got)"
    PASS=$((PASS+1))
  else
    echo "  ❌ $name (expected=$expect, actual=$got)"
    FAIL=$((FAIL+1))
  fi
}

echo "=== gate-redo-fuse.sh test（A-F3 回派熔断）==="

# === fixture 准备 ===
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# F0: 空（0 报告）
F0="$TMP/f0"; mkdir -p "$F0"
# F2: 2 blocking + 1 approve
F2="$TMP/f2"; mkdir -p "$F2"
mk_rep "$F2" "login-01.md" "block" "Pass"
mk_rep "$F2" "login-02.md" "block" "Pass"
mk_rep "$F2" "login-03.md" "approve" "Pass"
# F3: 3 blocking（block × 2 + Redo SIT × 1）+ 模板/retro（应排除）
F3="$TMP/f3"; mkdir -p "$F3"
mk_rep "$F3" "login-01.md" "block" "Pass"
mk_rep "$F3" "login-02.md" "approve" "Redo SIT"
mk_rep "$F3" "login-03.md" "block" "Pass"
mk_rep "$F3" "login-_TEMPLATE.md" "block" "Pass"   # 应排除
mk_rep "$F3" "retro-login.md" "block" "Pass"        # 应排除（retro- 前缀但无 login- 前缀；本用例验 retro 不被 login-* glob 命中）

DESC_CHANGES="任务类型: bugfix
上游产物: docs/changes/login/tasks.md"
DESC_REVIEWS="任务类型: bugfix
上游产物: docs/reviews/login-01.md"

# === AC ===
# AC-1 无 slug（描述无 docs 路径）→ 放行
run_case 0 "无slug放行" "$F3" 3 "任务类型: 新功能
上下文: src/auth/ 实现登录表单"

# AC-2 0 blocking → 放行
run_case 0 "0blocking放行" "$F0" 3 "$DESC_CHANGES"

# AC-3 2 blocking（< 3）→ 放行
run_case 0 "2blocking放行(limit3)" "$F2" 3 "$DESC_CHANGES"

# AC-4 3 blocking（≥ 3）+ 无豁免 → 阻断（docs/changes 路径抽 slug）
run_case 2 "3blocking无豁免阻断(changes路径)" "$F3" 3 "$DESC_CHANGES"

# AC-5 3 blocking + 半角冒号「熔断豁免:」→ 放行
run_case 0 "3blocking半角冒号豁免放行" "$F3" 3 "$DESC_CHANGES
熔断豁免: tech-lead 已诊断根因，按新指导重派"

# AC-6 3 blocking + 全角冒号「熔断豁免：」+ 列表项前缀 → 放行
run_case 0 "3blocking全角冒号豁免放行" "$F3" 3 "$DESC_CHANGES
- 熔断豁免：tech-lead 已诊断完"

# AC-7 3 blocking + 无豁免，docs/reviews 路径抽 slug → 阻断（slug 抽取 fallback）
run_case 2 "3blocking无豁免阻断(reviews路径抽slug)" "$F3" 3 "$DESC_REVIEWS"

# AC-8 LIMIT=2 + 2 blocking → 阻断（阈值可调）
run_case 2 "LIMIT=2+2blocking阻断" "$F2" 2 "$DESC_CHANGES"

# AC-9 LIMIT=5 + 3 blocking → 放行（未达高阈值）
run_case 0 "LIMIT=5+3blocking放行" "$F3" 5 "$DESC_CHANGES"

# AC-10 模板/retro 排除：F3 实际 3 blocking（模板/retro 不计），LIMIT=3 仍阻断 = 证明排除生效
#      （若没排除会变 5 blocking，但 LIMIT=3 都阻断；改用 LIMIT=4 区分：3 blocking < 4 放行）
run_case 0 "模板/retro排除(LIMIT=4,真3blocking放行)" "$F3" 4 "$DESC_CHANGES"

# AC-11 无 description → 放行（fail-open）
set +e
printf '%s' '{"tool_input":{}}' | bash "$HOOK" >/dev/null 2>&1
got=$?
set -e
if [[ "$got" -eq 0 ]]; then
  echo "  ✅ 无description放行 (exit=$got)"; PASS=$((PASS+1))
else
  echo "  ❌ 无description放行 (expected=0, actual=$got)"; FAIL=$((FAIL+1))
fi

# AC-12 缺 jq → 放行（fail-open）
if ! command -v jq >/dev/null 2>&1; then
  run_case 0 "缺jq放行(fail-open)" "$F3" 3 "$DESC_CHANGES"
else
  echo "  ⏭️  缺jq用例跳过（本机有 jq）"; PASS=$((PASS+1))
fi

echo
if [[ $FAIL -eq 0 ]]; then
  echo "=> 全部 $PASS 个用例通过"
  exit 0
else
  echo "=> $FAIL 个用例失败 / $PASS 个通过"
  exit 1
fi
