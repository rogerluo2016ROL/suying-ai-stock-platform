#!/usr/bin/env bash
# test-agf-verdict.sh — agf-verdict.py 单元测试（spec §11 第 1–4 组；第 5 组 hook wrapper = Task 3）。
# 覆盖：三套推导正确性 / validate 抓不符（exit 2）/ fail-open（exit 0 + WARN）/ matrix 输出。
# 所有 fixture 落在 mktemp 目录，绝不写真实 docs/reviews 或 docs/qa。
set -uo pipefail
SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../scripts" && pwd)/agf-verdict.py"
command -v python3 >/dev/null 2>&1 || { echo "需要 python3" >&2; exit 1; }
python3 -c 'import yaml' 2>/dev/null || { echo "需要 PyYAML（repo 已依赖）" >&2; exit 1; }

PASS=0; FAIL=0
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "=== agf-verdict.py 单元测试 ==="

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
# 断言一段 python（在模块上）求值的 stdout == 期望值
assert_py() { # name expr expected
  local name="$1"
  local expr="$2"
  local expected="$3"
  local got
  # stderr 落临时文件（不吞）：模块语法/import 报错时把 traceback 回显，
  # 避免 16 条 `实际 []` 掩盖「模块整体坏了」。本套是唯一 python 语法守门
  # （lint-all 只 `bash -n`，不编 python），失败必须可读。
  got=$(python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('agf_verdict', '$SCRIPT')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print($expr)
" 2>"$WORK/_py.err")
  if [[ "$got" == "$expected" ]]; then echo "  ✅ $name"; PASS=$((PASS+1))
  else
    echo "  ❌ ${name}：期望 [$expected]，实际 [$got]" >&2
    [[ -s "$WORK/_py.err" ]] && { echo "     ↳ python stderr:" >&2; sed 's/^/       /' "$WORK/_py.err" >&2; }
    FAIL=$((FAIL+1))
  fi
}

# 断言 validate CLI 的 exit code
assert_validate() { # name file kind expected_exit
  local name="$1"
  local file="$2"
  local kind="$3"
  local exp="$4"
  local got
  python3 "$SCRIPT" validate "$file" --kind="$kind" >/dev/null 2>&1; got=$?
  if [[ "$got" == "$exp" ]]; then echo "  ✅ $name (exit $got)"; PASS=$((PASS+1))
  else echo "  ❌ ${name}：期望 exit ${exp}，实际 $got" >&2; FAIL=$((FAIL+1)); fi
}

# 断言 validate CLI 既 exit 0 又在 stderr 打 WARN（fail-open）
assert_failopen() { # name file kind
  local name="$1"
  local file="$2"
  local kind="$3"
  local got
  local err
  err=$(python3 "$SCRIPT" validate "$file" --kind="$kind" 2>&1 >/dev/null); got=$?
  if [[ "$got" == 0 && "$err" == *"WARN"* ]]; then echo "  ✅ $name (exit 0 + WARN)"; PASS=$((PASS+1))
  else echo "  ❌ ${name}：期望 exit 0 + WARN，实际 exit $got / [$err]" >&2; FAIL=$((FAIL+1)); fi
}

# 写 review fixture frontmatter
write_review() { # path code_verdict critical warning sit_audit progress ac evidence fail_marking
  cat > "$1" <<EOF
---
feature: demo
date: 2026-06-15
reviewer: code-reviewer
code_verdict: $2
critical_count: $3
warning_count: $4
suggestion_count: 0
sit_audit_verdict: $5
sit_checks:
  progress: $6
  ac_coverage: $7
  evidence: $8
  fail_marking: $9
---

# 报告正文
EOF
}

# 写 qa fixture frontmatter
write_qa() { # path stage report_verdict critical_defect p0_total p0_ok uat_signoff
  cat > "$1" <<EOF
---
feature: demo
date: 2026-06-15
tester: qa-engineer
stage: $2
report_verdict: $3
critical_defect_count: $4
p0_pass2_total: $5
p0_pass2_ok: $6
uat_signoff_verdict: $7
---

# 报告正文
EOF
}

# --------------------------------------------------------------------------- #
# 1) 推导正确性（典型 + 边界）
# --------------------------------------------------------------------------- #
echo "--- 推导正确性 ---"
# derive_code
assert_py "code: critical>0 → block"            "m.derive_code({'critical_count':1,'warning_count':5})" "block"
assert_py "code: warning>0 → approve w/changes"  "m.derive_code({'critical_count':0,'warning_count':2})" "approve with changes"
assert_py "code: 全 0 → approve"                 "m.derive_code({'critical_count':0,'warning_count':0})" "approve"
assert_py "code: 缺字段 → approve(默认 0)"        "m.derive_code({})" "approve"
assert_py "code: important 别名 → approve w/chg"  "m.derive_code({'critical_count':0,'important_count':3})" "approve with changes"
# derive_sit
assert_py "sit: 含 fail → Redo SIT"   "m.derive_sit({'sit_checks':{'progress':'pass','ac_coverage':'fail','evidence':'pass','fail_marking':'pass'}})" "Redo SIT"
assert_py "sit: 含 concerns → Pass w/concerns" "m.derive_sit({'sit_checks':{'progress':'pass','ac_coverage':'concerns','evidence':'pass','fail_marking':'pass'}})" "Pass with concerns"
assert_py "sit: 全 pass → Pass"       "m.derive_sit({'sit_checks':{'progress':'pass','ac_coverage':'pass','evidence':'pass','fail_marking':'pass'}})" "Pass"
assert_py "sit: fail 优先于 concerns" "m.derive_sit({'sit_checks':{'progress':'concerns','ac_coverage':'fail','evidence':'pass','fail_marking':'pass'}})" "Redo SIT"
assert_py "sit: 缺 sit_checks → Pass(默认)" "m.derive_sit({})" "Pass"
# qa_floor_violations
assert_py "qa: critical_defect>0 非 Block → 违规" "len(m.qa_floor_violations({'critical_defect_count':1,'report_verdict':'Promote','p0_pass2_total':0,'p0_pass2_ok':0}))" "1"
assert_py "qa: P0 未全过却 Promote → 违规"        "len(m.qa_floor_violations({'critical_defect_count':0,'report_verdict':'Promote','p0_pass2_total':3,'p0_pass2_ok':2}))" "1"
assert_py "qa: critical_defect>0 且 Block → OK"   "len(m.qa_floor_violations({'critical_defect_count':2,'report_verdict':'Block','p0_pass2_total':0,'p0_pass2_ok':0}))" "0"
assert_py "qa: P0 全过 + Promote → OK"            "len(m.qa_floor_violations({'critical_defect_count':0,'report_verdict':'Promote','p0_pass2_total':3,'p0_pass2_ok':3}))" "0"
assert_py "qa: Conditional + P0 未全过 → 不硬拦"  "len(m.qa_floor_violations({'critical_defect_count':0,'report_verdict':'Conditional promote','p0_pass2_total':3,'p0_pass2_ok':2}))" "0"
assert_py "qa: 两条同违规 → 2 条 msg"             "len(m.qa_floor_violations({'critical_defect_count':1,'report_verdict':'Promote','p0_pass2_total':3,'p0_pass2_ok':2}))" "2"

# --------------------------------------------------------------------------- #
# 2) validate 抓不符（exit 2）
# --------------------------------------------------------------------------- #
echo "--- validate 抓不符 ---"
write_review "$WORK/r-bad-code.md" approve 1 0 Pass pass pass pass pass
assert_validate "review: critical=1 却 approve → exit 2" "$WORK/r-bad-code.md" review 2

write_review "$WORK/r-bad-sit.md" approve 0 0 Pass pass fail pass pass
assert_validate "review: sit_checks 含 fail 却 Pass → exit 2" "$WORK/r-bad-sit.md" review 2

write_review "$WORK/r-good.md" approve 0 0 Pass pass pass pass pass
assert_validate "review: 一致 → exit 0" "$WORK/r-good.md" review 0

write_review "$WORK/r-block.md" block 1 0 "Redo SIT" pass pass pass fail
assert_validate "review: block+RedoSIT 一致 → exit 0" "$WORK/r-block.md" review 0

write_qa "$WORK/q-bad-crit.md" UAT Promote 1 0 0 approve
assert_validate "qa: critical_defect=1 却 Promote → exit 2" "$WORK/q-bad-crit.md" qa 2

write_qa "$WORK/q-bad-p0.md" UAT Promote 0 3 2 approve
assert_validate "qa: P0 未全 pass² 却 Promote → exit 2" "$WORK/q-bad-p0.md" qa 2

write_qa "$WORK/q-good.md" UAT Promote 0 3 3 approve
assert_validate "qa: P0 全过 + Promote → exit 0" "$WORK/q-good.md" qa 0

write_qa "$WORK/q-cond.md" E2E "Conditional promote" 0 3 2 N/A
assert_validate "qa: Conditional + P0 未全过 → exit 0(不硬拦)" "$WORK/q-cond.md" qa 0

# W2：非整数计数不应被 _as_int 静默转 0 放行——frontmatter 数据非法，verdict 一致性门
# 要求数据本身有效（原 critical_count: see-notes → _as_int→0 → derive "approve" 与声明
# 一致 → exit 0 放行，门形同虚设）
write_review "$WORK/r-bad-count.md" approve see-notes 0 Pass pass pass pass pass
assert_validate "review: critical_count 非整数 → exit 2（W2）" "$WORK/r-bad-count.md" review 2
write_qa "$WORK/q-bad-count.md" UAT Promote not-a-number 3 3 approve
assert_validate "qa: critical_defect_count 非整数 → exit 2（W2）" "$WORK/q-bad-count.md" qa 2

# --------------------------------------------------------------------------- #
# 3) fail-open（exit 0 + WARN）
# --------------------------------------------------------------------------- #
echo "--- fail-open ---"
assert_failopen "缺文件 → exit 0 + WARN" "$WORK/does-not-exist.md" review
printf -- '---\ncode_verdict: approve\n  bad: : indent: yaml\n :::\n---\n' > "$WORK/r-malformed.md"
assert_failopen "坏 yaml → exit 0 + WARN" "$WORK/r-malformed.md" review

# --------------------------------------------------------------------------- #
# 4) matrix 输出（fixture 在 mktemp 的 docs/reviews & docs/qa）
# --------------------------------------------------------------------------- #
echo "--- matrix ---"
MROOT=$(mktemp -d)
mkdir -p "$MROOT/docs/reviews" "$MROOT/docs/qa"
write_review "$MROOT/docs/reviews/feat-2026-06-15.md" "approve with changes" 0 2 Pass pass pass pass pass
write_review "$MROOT/docs/reviews/feat-r2-2026-06-15.md" block 1 0 "Redo SIT" pass pass pass fail
# 应被排除的文件
write_review "$MROOT/docs/reviews/feat-2026-06-15_TEMPLATE.md" approve 0 0 Pass pass pass pass pass
write_qa "$MROOT/docs/qa/feat-uat-2026-06-15.md" UAT Promote 0 3 3 approve
write_qa "$MROOT/docs/qa/feat-process-log.md" UAT Promote 0 0 0 N/A
# uat-cases 用例文档命中 {feat}-*.md glob，但应与 hook 排除集一致地排除（非报告，不进 matrix）
write_qa "$MROOT/docs/qa/feat-uat-cases-2026-06-16.md" UAT Promote 0 0 0 N/A

assert_matrix() { # name out grep_pattern
  local name="$1"
  local out="$2"
  local pat="$3"
  if echo "$out" | grep -qF "$pat"; then echo "  ✅ $name"; PASS=$((PASS+1))
  else echo "  ❌ ${name}：未在 matrix 输出找到 [$pat]" >&2; echo "$out" >&2; FAIL=$((FAIL+1)); fi
}

# review matrix — 默认 docs-root=. → 用 --docs-root 指向 mktemp（不 cd，避免影响）
RV_OUT=$(python3 "$SCRIPT" matrix --type=review --feature=feat --docs-root="$MROOT" 2>&1)
assert_matrix "review matrix: 表头" "$RV_OUT" "| Reviewer 实例 | 代码 Verdict | SIT Audit | Critical | Warning | 报告路径 |"
assert_matrix "review matrix: r2 行(block)" "$RV_OUT" "| block | Redo SIT | 1 | 0 |"
# _TEMPLATE 应被排除
if echo "$RV_OUT" | grep -qF "_TEMPLATE"; then
  echo "  ❌ review matrix: _TEMPLATE 未被排除" >&2; FAIL=$((FAIL+1))
else echo "  ✅ review matrix: _TEMPLATE 已排除"; PASS=$((PASS+1)); fi

# review matrix via cd（验证默认相对 CWD 扫描路径）
RV_OUT_CD=$(cd "$MROOT" && python3 "$SCRIPT" matrix --type=review --feature=feat 2>&1)
assert_matrix "review matrix: cd 后默认相对 CWD 扫描" "$RV_OUT_CD" "| Reviewer 实例 | 代码 Verdict |"

# qa matrix
QA_OUT=$(python3 "$SCRIPT" matrix --type=qa --feature=feat --docs-root="$MROOT" 2>&1)
assert_matrix "qa matrix: 表头" "$QA_OUT" "| QA 实例 | 阶段 | 报告级 Verdict | UAT 业务签字 | pass^2 (P0) | 报告路径 |"
assert_matrix "qa matrix: uat 行(pass^2=3/3)" "$QA_OUT" "| qa-engineer | UAT | Promote | approve | 3/3 |"
if echo "$QA_OUT" | grep -qF "process-log"; then
  echo "  ❌ qa matrix: process-log 未被排除" >&2; FAIL=$((FAIL+1))
else echo "  ✅ qa matrix: process-log 已排除"; PASS=$((PASS+1)); fi
# uat-cases 用例文档应被排除（与 hook 排除集一致），不得作为 junk 行进 matrix
if echo "$QA_OUT" | grep -qF "uat-cases"; then
  echo "  ❌ qa matrix: uat-cases 未被排除" >&2; FAIL=$((FAIL+1))
else echo "  ✅ qa matrix: uat-cases 已排除"; PASS=$((PASS+1)); fi

# 空 feature → 暂无 note
EMPTY_OUT=$(python3 "$SCRIPT" matrix --type=review --feature=nonexistent --docs-root="$MROOT" 2>&1)
assert_matrix "review matrix: 无文件 → 暂无 note" "$EMPTY_OUT" "暂无 review 报告"

rm -rf "$MROOT"

# --------------------------------------------------------------------------- #
echo "─────────"
if (( FAIL )); then echo "❌ $FAIL 用例失败 / $PASS 通过" >&2; exit 1; fi
echo "✅ 全部 $PASS 用例通过"
