#!/usr/bin/env bash
# .claude/scripts/run-all-tests.sh
#
# hermetic test runner —— 剥离继承环境变量，防 hook 环境跑 test 时 git 指向 host repo
# 污染 fixture。依据 ECC tests/run-all.js:80-83。
#
# 与 lint-all.sh 互补：lint-all 含语法/JSON/YAML + gen-roles drift + test 套（非 hermetic）；
# 本脚本只跑 test 套，但 hermetic（剥离 GIT_DIR/GIT_WORK_TREE/CLAUDE_* 等继承 env）。
#
# 用法：bash .claude/scripts/run-all-tests.sh

set -uo pipefail

# 剥离可能污染 fixture 的继承环境变量（ECC run-all.js:80-83 防 git hook 环境污染）
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_QUARANTINE_PATH 2>/dev/null || true

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR" || { echo "FAIL: cd $PROJECT_DIR"; exit 1; }

echo "== hermetic test runner（已剥离 GIT_DIR / GIT_WORK_TREE 等继承 env）=="
echo "  扫描：.claude/hooks/tests/**/*.test.sh（递归，含子目录如 ci/）"
echo ""

FAIL=0
COUNT=0
while IFS= read -r t; do
  [ -z "$t" ] && continue
  COUNT=$((COUNT + 1))
  [ -x "$t" ] || chmod +x "$t" 2>/dev/null
  short="${t#.claude/hooks/tests/}"
  if bash "$t" >/tmp/_rall.out 2>&1; then
    echo "  ✅ $short"
  else
    echo "  ❌ $short"
    cat /tmp/_rall.out >&2
    FAIL=1
  fi
  rm -f /tmp/_rall.out
done < <(find .claude/hooks/tests -type f -name 'test-*.sh' 2>/dev/null)

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 全部通过（$COUNT 个 test 套）"
else
  echo "❌ 有失败（$COUNT 个 test 套）"
fi
exit $FAIL
