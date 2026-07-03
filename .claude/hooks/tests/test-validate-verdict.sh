#!/usr/bin/env bash
# test-validate-verdict.sh — validate-verdict.sh 单元测试（泛化后 reviewer + qa 6 role）
#
# 本测试聚焦 hook 的 **bash glue**（role gating / 定位报告文件 / 委托 agf-verdict.py / 透传 exit
# / 全 fail-open 分支）；frontmatter 解析 + 三套推导本身在 test-agf-verdict.sh 覆盖，这里不重测。
# 喂构造的 SubagentStop payload（stdin JSON）+ 临时 docs/reviews|docs/qa 里的 fixture 报告，
# 断言 exit code（0=放行 / 2=拦）。用 CLAUDE_PROJECT_DIR 指向 mktemp -d，不碰真实仓库。
# lint-all 全量模式链调。
set -uo pipefail
HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/validate-verdict.sh"
command -v jq >/dev/null 2>&1 || { echo "需要 jq" >&2; exit 1; }
PASS=0; FAIL=0

# 构造 SubagentStop payload JSON（.agent_type + .last_assistant_message + .stop_hook_active）
payload() { jq -nc --arg r "$1" --arg m "${2:-}" --argjson s "${3:-false}" \
  '{agent_type:$r, last_assistant_message:$m, stop_hook_active:$s}'; }

# --- review fixture：新 schema frontmatter（code_verdict + critical_count + sit_*） ---
review_fm() { # code_verdict critical warning sit_audit_verdict sit_progress
  printf -- '---\nfeature: demo\ndate: 2026-06-16\nreviewer: code-reviewer\ncode_verdict: %s\ncritical_count: %s\nwarning_count: %s\nsuggestion_count: 0\nsit_audit_verdict: %s\nsit_checks:\n  progress: %s\n  ac_coverage: pass\n  evidence: pass\n  fail_marking: pass\n---\n\n# 审查报告\n' \
    "$1" "$2" "$3" "$4" "${5:-pass}"
}
# --- qa fixture：新 schema frontmatter（report_verdict + critical_defect_count + p0_pass2_*） ---
qa_fm() { # report_verdict critical_defect p0_total p0_ok
  printf -- '---\nfeature: demo\ndate: 2026-06-16\ntester: qa-engineer\nstage: UAT\nreport_verdict: %s\ncritical_defect_count: %s\np0_pass2_total: %s\np0_pass2_ok: %s\nuat_signoff_verdict: N/A\n---\n\n# QA 报告\n' \
    "$1" "$2" "$3" "$4"
}

# run：name expected_exit role report_subdir report_filename report_content
# 在 mktemp -d 里铺 fixture，CLAUDE_PROJECT_DIR 指向它（隔离报告目录；agf-verdict.py 由 hook
# 按自身位置在真实 .claude/scripts/ 定位，不受 CLAUDE_PROJECT_DIR 影响），喂 payload。
run() {
  local name="$1" exp="$2" role="$3" subdir="$4" fname="$5" content="$6"
  local got TMPD
  TMPD=$(mktemp -d); mkdir -p "$TMPD/$subdir"
  [[ -n "$fname" ]] && printf '%s' "$content" > "$TMPD/$subdir/$fname"
  printf '%s' "$(payload "$role")" | CLAUDE_PROJECT_DIR="$TMPD" bash "$HOOK" >/dev/null 2>&1; got=$?
  rm -rf "$TMPD"
  if [[ "$got" == "$exp" ]]; then echo "  ✅ $name (exit $got)"; PASS=$((PASS+1))
  else echo "  ❌ ${name} 期望 exit ${exp}，实际 ${got}" >&2; FAIL=$((FAIL+1)); fi
}

echo "=== validate-verdict.sh 单元测试（hook glue）==="

# --- 核心防线：声明 ≠ 推导 → 拦 ---
run "reviewer + critical=1 却 approve → 拦【核心防线】" 2 code-reviewer docs/reviews feat-2026-06-16.md \
  "$(review_fm approve 1 0 'Redo SIT' fail)"
run "qa + critical_defect=1 却 Promote → 拦【QA 底线】" 2 qa-engineer docs/qa feat-uat-2026-06-16.md \
  "$(qa_fm Promote 1 0 0)"
run "qa + P0 未全 pass² 却 Promote → 拦【QA 底线】" 2 qa-engineer docs/qa feat-uat-2026-06-16.md \
  "$(qa_fm Promote 0 3 2)"

# --- 一致 → 放行 ---
run "reviewer + 一致(approve/clean/Pass) → 放行" 0 code-reviewer docs/reviews feat-2026-06-16.md \
  "$(review_fm approve 0 0 Pass pass)"
run "reviewer + 一致(block/critical=1/Redo SIT) → 放行" 0 code-reviewer docs/reviews feat-2026-06-16.md \
  "$(review_fm block 1 0 'Redo SIT' fail)"
run "qa + 底线无违规(Promote/0缺陷/P0全过) → 放行" 0 qa-engineer docs/qa feat-uat-2026-06-16.md \
  "$(qa_fm Promote 0 3 3)"

# --- pool 后缀 + miniapp/apple role 走对分支 ---
run "pool 后缀 code-reviewer-2 + 不符 → 拦" 2 code-reviewer-2 docs/reviews feat-2026-06-16.md \
  "$(review_fm approve 1 0 Pass pass)"
run "apple-code-reviewer + 不符 → 拦" 2 apple-code-reviewer docs/reviews feat-2026-06-16.md \
  "$(review_fm approve 1 0 Pass pass)"
run "miniapp-qa-engineer + 底线违规 → 拦" 2 miniapp-qa-engineer docs/qa feat-e2e-2026-06-16.md \
  "$(qa_fm Promote 1 0 0)"

# --- 报告目录排除集：reviewer 只看 docs/reviews（qa 报告不该被它读）---
run "reviewer 排除 _TEMPLATE（目录仅模板）→ 放行(fail-open)" 0 code-reviewer docs/reviews feat-_TEMPLATE.md \
  "$(review_fm approve 1 0 Pass pass)"
run "qa 排除 uat-cases（目录仅用例文档）→ 放行(fail-open)" 0 qa-engineer docs/qa feat-uat-cases-2026-06-16.md \
  "$(qa_fm Promote 1 0 0)"

# --- fail-open 各分支 ---
run "非目标 role(backend-dev) → 放行(fail-open)" 0 backend-dev docs/reviews feat-2026-06-16.md \
  "$(review_fm approve 1 0 Pass pass)"
run "无报告文件 → 放行(fail-open)" 0 code-reviewer docs/reviews "" ""

# --- #8 根因回归：docs/reviews 里的「非 verdict 报告」不得被误当 verdict 报告阻断 ---
# （legacy 散文审查 / audit / sweep / no-verify-log 等无 verdict 键的文件）
run "legacy 无 frontmatter 报告 → 放行(fail-open)" 0 code-reviewer docs/reviews legacy-audit-report.md \
  "$(printf '# 源码深度审查报告\n\n无 frontmatter 的散文式报告正文。')"
run "非 verdict 报告(有 frontmatter 无 code_verdict) → 放行" 0 code-reviewer docs/reviews no-verify-log-2026-06-17.md \
  "$(printf -- '---\nreport_type: no-verify-log\ndate: 2026-06-17\n---\n\n# log')"
# report_type 显式标注非 gating（legacy audit/sweep）→ 即使含 code_verdict 且不自洽也必须跳过（不阻断当前 reviewer）
run "report_type=legacy-sweep(含不自洽 code_verdict) → 放行" 0 code-reviewer docs/reviews build-plugin-sweep-2026-05-30.md \
  "$(printf -- '---\nreport_type: legacy-sweep\ncode_verdict: approve with changes\ncritical_count: 2\nwarning_count: 3\nsuggestion_count: 0\nsit_audit_verdict: Pass\nsit_checks:\n  progress: pass\n  ac_coverage: pass\n  evidence: pass\n  fail_marking: pass\n---\n# sweep')"

# loop guard：需 payload 第 3 参 stop_hook_active=true（run() 不暴露它）→ 单独跑一例。
# fixture 故意 approve+critical=1（本应推导 block → 拦），但 loop guard 必须在比对前先放行（exit 0），
# 证明 loop guard 优先级高于推导拦截。
lg() {
  local got TMPD; TMPD=$(mktemp -d); mkdir -p "$TMPD/docs/reviews"
  printf '%s' "$(review_fm approve 1 0 Pass pass)" > "$TMPD/docs/reviews/feat-2026-06-16.md"
  printf '%s' "$(payload code-reviewer "" true)" | CLAUDE_PROJECT_DIR="$TMPD" bash "$HOOK" >/dev/null 2>&1; got=$?
  rm -rf "$TMPD"
  if [[ "$got" == "0" ]]; then echo "  ✅ loop guard(stop_hook_active=true) → 放行 (exit 0)"; PASS=$((PASS+1))
  else echo "  ❌ loop guard：期望 exit 0，实际 $got" >&2; FAIL=$((FAIL+1)); fi
}
lg

# --- 无 jq / 无 python3：用受限 PATH 模拟（fail-open）---
# 准备一个只含 jq 的 PATH（剥 python3）：验「无 python3 → 放行」
no_py_dir=$(mktemp -d)
for tool in bash jq cat ls basename dirname env mktemp printf rm; do
  src=$(command -v "$tool" 2>/dev/null) && ln -sf "$src" "$no_py_dir/$tool" 2>/dev/null || true
done
nopytest() {
  local got TMPD; TMPD=$(mktemp -d); mkdir -p "$TMPD/docs/reviews"
  printf '%s' "$(review_fm approve 1 0 Pass pass)" > "$TMPD/docs/reviews/feat-2026-06-16.md"
  printf '%s' "$(payload code-reviewer)" | PATH="$no_py_dir" CLAUDE_PROJECT_DIR="$TMPD" bash "$HOOK" >/dev/null 2>&1; got=$?
  rm -rf "$TMPD"
  if [[ "$got" == "0" ]]; then echo "  ✅ 无 python3(受限 PATH) → 放行(fail-open) (exit 0)"; PASS=$((PASS+1))
  else echo "  ❌ 无 python3：期望 exit 0，实际 $got" >&2; FAIL=$((FAIL+1)); fi
}
command -v jq >/dev/null 2>&1 && [[ -x "$no_py_dir/jq" ]] && nopytest || echo "  ⏭  跳过无 python3 用例（受限 PATH 构造不全）"
rm -rf "$no_py_dir"

# 无 jq：PATH 完全不含 jq（也不含 python3）→ 第一道就 fail-open
no_jq_dir=$(mktemp -d)
for tool in bash cat ls basename dirname env mktemp printf rm; do
  src=$(command -v "$tool" 2>/dev/null) && ln -sf "$src" "$no_jq_dir/$tool" 2>/dev/null || true
done
nojqtest() {
  local got TMPD; TMPD=$(mktemp -d)
  printf '%s' '{"agent_type":"code-reviewer"}' | PATH="$no_jq_dir" CLAUDE_PROJECT_DIR="$TMPD" bash "$HOOK" >/dev/null 2>&1; got=$?
  rm -rf "$TMPD"
  if [[ "$got" == "0" ]]; then echo "  ✅ 无 jq(受限 PATH) → 放行(fail-open) (exit 0)"; PASS=$((PASS+1))
  else echo "  ❌ 无 jq：期望 exit 0，实际 $got" >&2; FAIL=$((FAIL+1)); fi
}
nojqtest
rm -rf "$no_jq_dir"

# --- #1 根因回归：pool 实例必须校验「自己的」报告（<feat>-r<N>-<date>.md），而非目录最新一份 ---
# r1 合规 + r2 不符，r1 故意 touch 成最新（current head-1 会错取 r1 放行）。code-reviewer-2 必须取 r2 → 拦。
pooltest() {
  local got TMPD; TMPD=$(mktemp -d); mkdir -p "$TMPD/docs/reviews"
  printf '%s' "$(review_fm approve 1 0 'Redo SIT' fail)" > "$TMPD/docs/reviews/feat-r2-2026-06-16.md"  # 不符 → 应拦
  printf '%s' "$(review_fm approve 0 0 Pass pass)"       > "$TMPD/docs/reviews/feat-r1-2026-06-16.md"  # 合规
  touch "$TMPD/docs/reviews/feat-r1-2026-06-16.md"  # 令 r1 成为目录最新（暴露 head-1 错取）
  printf '%s' "$(payload code-reviewer-2)" | CLAUDE_PROJECT_DIR="$TMPD" bash "$HOOK" >/dev/null 2>&1; got=$?
  rm -rf "$TMPD"
  if [[ "$got" == "2" ]]; then echo "  ✅ pool 实例取自己报告(-r2-)不符 → 拦 (exit 2)"; PASS=$((PASS+1))
  else echo "  ❌ pool 实例匹配 期望 exit 2 取 r2，实际 ${got} 疑被 head-1 误取 r1 放行" >&2; FAIL=$((FAIL+1)); fi
}
pooltest

echo "─────────"
if (( FAIL )); then echo "❌ $FAIL 用例失败 / $PASS 通过" >&2; exit 1; fi
echo "✅ 全部 $PASS 用例通过"
