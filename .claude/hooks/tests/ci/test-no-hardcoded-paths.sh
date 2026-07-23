#!/bin/bash
# .claude/hooks/tests/ci/test-no-hardcoded-paths.sh
#
# CI 治理断言：.claude/ 无硬编码绝对个人路径。
# 依据 ECC tests/ci/no-personal-paths.test.js。防 /Users/someone/ 或 /home/user/ 进
# 模板（应改相对路径或 $CLAUDE_PROJECT_DIR / $HOME 变量）。
#
# 这是 tests/ci/ 子目录的首个测试，验证分层结构（P1 ④ tests 分层）。

set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
SCAN_DIR="$PROJECT_DIR/.claude"

# 扫 .sh/.py/.json（可执行/配置，硬编码风险高），排除：
#   - 注释行（# 开头）
#   - 变量引用（$HOME / $CLAUDE_PROJECT_DIR）+ 标准路径（/tmp / /dev/null）
HITS=$(grep -rnE '/(Users|home)/[a-z_-]+' "$SCAN_DIR" 2>/dev/null \
  --include='*.sh' --include='*.py' --include='*.json' \
  | grep -vE ':[[:space:]]*#' \
  | grep -vE '\$\{?HOME|\$\{?CLAUDE_PROJECT_DIR|/tmp/|/dev/null' \
  || true)

PASS=0; FAIL=0; FAIL_LINES=()
echo "  扫描: $SCAN_DIR (*.sh / *.py / *.json)"
if [ -z "$HITS" ]; then
  PASS=$((PASS + 1))
  echo "  ✅ 无硬编码个人绝对路径（/Users/... 或 /home/...）"
else
  FAIL=$((FAIL + 1))
  echo "  ❌ 发现硬编码路径（改相对路径 / \$CLAUDE_PROJECT_DIR / \$HOME）："
  echo "$HITS" | head -15 | sed 's/^/    /'
fi

echo ""
echo "=========================================="
echo "test-no-hardcoded-paths (ci)"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
[ $FAIL -gt 0 ] && exit 1
exit 0
