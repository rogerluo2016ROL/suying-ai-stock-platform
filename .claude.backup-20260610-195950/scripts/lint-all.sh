#!/usr/bin/env bash
# lint-all.sh — 项目级一键 lint 入口
#
# 用途: 跑所有可行的静态校验（不跑测试套，那是 dev 自己的事）：
#   1. Bash 脚本语法（bash -n）
#   2. JSON 文件解析（python3 -m json.tool）
#   3. YAML 文件解析（python3 yaml.safe_load）
#   4. Markdown 文件不强制 lint（项目无 markdownlint 依赖）但检查链接死链（可选 grep）
#
# 用法:
#   bash .claude/scripts/lint-all.sh             # 全跑
#   bash .claude/scripts/lint-all.sh --quick     # 跳过慢检查（暂同 default）
#   bash .claude/scripts/lint-all.sh --pre-commit # 仅检查 git staged 文件
#
# 退出码: 0 = 全过；1 = 任一失败
#
# pre-commit 集成: .git/hooks/pre-commit 串行调用本脚本（在 scan-commit.sh 之后）

set -uo pipefail

PRE_COMMIT_MODE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pre-commit) PRE_COMMIT_MODE=1; shift ;;
    --quick) shift ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

FAIL=0
PASS_COUNT=0

# === 文件列表 ===
if [[ "$PRE_COMMIT_MODE" -eq 1 ]]; then
  # 仅校验 staged 文件
  STAGED=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)
  SHELL_FILES=$(echo "$STAGED" | grep -E '\.sh$' || true)
  JSON_FILES=$(echo "$STAGED" | grep -E '\.json$' | grep -v 'tools/team-dashboard/node_modules' || true)
  YAML_FILES=$(echo "$STAGED" | grep -E '\.(ya?ml)$' || true)
else
  SHELL_FILES=$(find .claude -type f -name '*.sh' 2>/dev/null | grep -v node_modules)
  # JSON: 单根 . 跑（避免 .claude 和 . 双根重复扫同文件）
  JSON_FILES=$(find . -maxdepth 3 -type f -name '*.json' 2>/dev/null \
    | grep -v node_modules | grep -v '\.pytest_cache' | grep -v 'tools/team-dashboard' \
    | sed 's|^\./||' | sort -u)
  YAML_FILES=$(find . -maxdepth 3 -type f \( -name '*.yaml' -o -name '*.yml' \) 2>/dev/null \
    | grep -v node_modules | grep -v '\.pytest_cache' | grep -v 'tools/team-dashboard' \
    | sed 's|^\./||' | sort -u)
fi

# === Bash lint ===
echo "=== Bash 脚本语法 ==="
if [[ -n "${SHELL_FILES:-}" ]]; then
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if bash -n "$f" 2>/dev/null; then
      echo "  ✅ $f"
      PASS_COUNT=$((PASS_COUNT + 1))
    else
      echo "  ❌ $f" >&2
      bash -n "$f" 2>&1 | sed 's/^/     /' >&2
      FAIL=$((FAIL + 1))
    fi
  done <<< "$SHELL_FILES"
else
  echo "  （无 .sh 文件）"
fi

# === JSON lint ===
echo ""
echo "=== JSON 解析 ==="
if [[ -n "${JSON_FILES:-}" ]]; then
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if python3 -m json.tool "$f" >/dev/null 2>&1; then
      echo "  ✅ $f"
      PASS_COUNT=$((PASS_COUNT + 1))
    else
      echo "  ❌ $f" >&2
      python3 -m json.tool "$f" 2>&1 | sed 's/^/     /' >&2
      FAIL=$((FAIL + 1))
    fi
  done <<< "$JSON_FILES"
else
  echo "  （无 .json 文件）"
fi

# === YAML lint ===
echo ""
echo "=== YAML 解析 ==="
if [[ -n "${YAML_FILES:-}" ]]; then
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if python3 -c "import sys, yaml; yaml.safe_load(open(sys.argv[1]))" "$f" 2>/dev/null; then
      echo "  ✅ $f"
      PASS_COUNT=$((PASS_COUNT + 1))
    else
      echo "  ❌ $f" >&2
      python3 -c "import sys, yaml; yaml.safe_load(open(sys.argv[1]))" "$f" 2>&1 | sed 's/^/     /' >&2
      FAIL=$((FAIL + 1))
    fi
  done <<< "$YAML_FILES"
else
  echo "  （无 .yaml/.yml 文件）"
fi

# === Hook 既有测试 ===
if [[ "$PRE_COMMIT_MODE" -eq 0 ]] && [[ -x .claude/hooks/test-validate-task-schema.sh ]]; then
  echo ""
  echo "=== Hook 既有测试套 ==="
  if bash .claude/hooks/test-validate-task-schema.sh > /tmp/_validate_test.out 2>&1; then
    TESTS_PASSED=$(grep -c '✅' /tmp/_validate_test.out || echo 0)
    echo "  ✅ test-validate-task-schema.sh ($TESTS_PASSED 用例通过)"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "  ❌ test-validate-task-schema.sh 失败" >&2
    cat /tmp/_validate_test.out >&2
    FAIL=$((FAIL + 1))
  fi
  rm -f /tmp/_validate_test.out
fi

# === 总结 ===
echo ""
echo "─────────"
if [[ "$FAIL" -gt 0 ]]; then
  echo "❌ Lint 失败：$FAIL 个文件 / 测试套未过；$PASS_COUNT 个通过" >&2
  exit 1
else
  echo "✅ Lint 全过：$PASS_COUNT 个文件 / 测试套"
  exit 0
fi
