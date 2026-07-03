#!/usr/bin/env bash
# test-sit-precheck.sh — 回归测试 agf-sit-precheck.sh（ADR-011 决策 2）
#
# 跑法：bash .claude/hooks/tests/test-sit-precheck.sh
# 退出码：0 = 全部通过；1 = 至少一个 case 不符合预期
# 由 lint-all.sh / init-team.sh 自动发现并执行。

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCRIPT="$REPO_ROOT/.claude/scripts/agf-sit-precheck.sh"

PASS=0
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ok()  { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

# run_fixture <name> <expected_exit> <grep_mode:has|nohas|clean> <pattern> <content>
run_fixture() {
  local name="$1" exp_exit="$2" mode="$3" pat="$4" content="$5"
  local f="$TMP/p.md" out rc
  printf '%s\n' "$content" > "$f"
  set +e
  out=$(bash "$SCRIPT" "$f" 2>&1); rc=$?
  set -e
  if [[ "$rc" -ne "$exp_exit" ]]; then bad "$name (exit expected=$exp_exit got=$rc)"; return; fi
  case "$mode" in
    has)   echo "$out" | grep -qF "$pat" && ok "$name" || bad "$name (缺 flag: $pat)";;
    nohas) echo "$out" | grep -qF "$pat" && bad "$name (不应出现: $pat)" || ok "$name";;
    clean) echo "$out" | grep -qF "无机械问题" && ! echo "$out" | grep -q "⚠️" && ok "$name" || bad "$name (应 clean 无 flag)";;
  esac
}

echo "=== agf-sit-precheck.sh test ==="

# Case 1: clean — pass 单行 + fail 带证据 + 质量门 SIT ⚠️ → 0 flag
run_fixture "clean: pass+fail带证据+门⚠️ 应无 flag" 0 clean "" \
'## [登录] - 2026-06-23 10:00
**状态**: 已完成
**Skills**: agf-running-sit-tests

**SIT 证据**（按 AC 列）:
- [x] AC-1 ✅ 用户注册 — POST /register 写库成功
- [x] AC-2 ✅ 邮箱校验通过
- [ ] AC-3 ❌ webhook 签名 — 实现 SHA1，PRD 要 HMAC-SHA256
    - 命令: $ pytest backend/tests/sit/test_webhook.py -v
    - 输出: AssertionError: signature mismatch

**质量门**: lint ✅ / typecheck ✅ / unit ✅ / SIT ⚠️（AC-3 fail）

**下一步**: 等待 review'

# Case 2: placeholder — fail AC 无命令/输出证据
run_fixture "placeholder: fail 缺证据应 flag" 0 has "placeholder" \
'**SIT 证据**:
- [x] AC-1 ✅ ok
- [ ] AC-2 ❌ 失败了没贴证据

**质量门**: lint ✅ / SIT ⚠️'

# Case 3: mismark — pass AC 行含失败信号 token
run_fixture "mismark: pass 含 AssertionError 应 flag" 0 has "mismark" \
'**SIT 证据**:
- [x] AC-1 ✅ 注册成功但 AssertionError 偶现

**质量门**: lint ✅ / SIT ✅'

# Case 4: 质量门矛盾 — AC fail（带证据）但质量门 SIT ✅
run_fixture "inconsistency: 门 SIT✅ 但 AC fail 应 flag" 0 has "矛盾" \
'**SIT 证据**:
- [ ] AC-1 ❌ 失败
    - 命令: $ pytest x
    - 输出: FAILED test_x

**质量门**: lint ✅ / SIT ✅'

# Case 4b: 该 fixture 不应同时报 placeholder（AC-1 有证据）
run_fixture "inconsistency 不误报 placeholder" 0 nohas "placeholder" \
'**SIT 证据**:
- [ ] AC-1 ❌ 失败
    - 命令: $ pytest x
    - 输出: FAILED test_x

**质量门**: lint ✅ / SIT ✅'

# Case 5: 无 SIT 段
run_fixture "无 SIT 段应 flag" 0 has "未找到" \
'## [task]
**状态**: 已完成
**质量门**: lint ✅'

# Case 6: SIT 段但无 AC 行
run_fixture "SIT 段无 AC 行应 flag" 0 has "无 AC 行" \
'**SIT 证据**:
跑了一些测试都过了

**质量门**: SIT ✅'

# Case 7: clean 全 pass（无 fail，门 SIT ✅）
run_fixture "clean: 全 pass 门✅ 应无 flag" 0 clean "" \
'**SIT 证据**:
- [x] AC-1 ✅ 注册成功
- [x] AC-2 ✅ 登录成功

**质量门**: lint ✅ / SIT ✅'

# Case 8: 用法错误（无参数）→ exit 1
echo "--- 用法错误 ---"
set +e
bash "$SCRIPT" >/dev/null 2>&1; rc=$?
set -e
[[ "$rc" -eq 1 ]] && ok "无参数应 exit 1" || bad "无参数 expected exit 1 got $rc"

# Case 9: 文件不存在 → exit 1
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
