#!/usr/bin/env bash
# test-secret-pattern-parity.sh — 断言 scan-secrets.sh 与 scan-commit.sh 覆盖同一组厂商密钥。
#
# 背景：两个 scanner 各存一份厂商正则（scan-commit 注释原写"keep both in sync manually"）。
# 人工同步 = 漂移源：加一个国产 LLM 厂商时只改一边，另一边静默漏扫。
# 本测试用"机器校验覆盖面 parity"取代人工纪律，**不改两个安全 hook 一个字**——
# 避免在 fast-path COMBINED 这种安全正则上动刀引 bug（本仓库踩过 `s`-排除类回归）。
# 加新厂商：两个 scanner 都加 → 本测试自然通过；只改一边 → 本测试 fail。
#
# 由 lint-all.sh（全量模式）+ init-team.sh 自动跑。

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS="$DIR/scan-secrets.sh"
COMMIT="$DIR/scan-commit.sh"
PASS=0; FAIL=0

[[ -f "$SECRETS" && -f "$COMMIT" ]] || { echo "❌ 找不到 scan-secrets.sh / scan-commit.sh" >&2; exit 1; }

# 1) 厂商 *_API_KEY 环境变量名集合必须一致（最易漂移：新增国产 LLM 厂商）
S_ENV=$(grep -oE '[A-Z][A-Z0-9_]+_API_KEY' "$SECRETS" | sort -u | tr '\n' ' ')
C_ENV=$(grep -oE '[A-Z][A-Z0-9_]+_API_KEY' "$COMMIT"  | sort -u | tr '\n' ' ')
if [[ "$S_ENV" == "$C_ENV" ]]; then
  echo "  ✅ 厂商 *_API_KEY 环境变量名集合一致：$S_ENV"; PASS=$((PASS+1))
else
  echo "  ❌ *_API_KEY 集合漂移：" >&2
  echo "     scan-secrets: $S_ENV" >&2
  echo "     scan-commit : $C_ENV" >&2
  FAIL=$((FAIL+1))
fi

# 2) 稳定厂商前缀 / 私钥标志必须两文件都覆盖
for MARK in 'AKIA|ASIA' 'github_pat' 'sk-ant' 'AIza' 'xox' 'PuTTY-User-Key-File' 'OPENSSH' 'mnemonic'; do
  s=0; c=0
  grep -qE "$MARK" "$SECRETS" && s=1
  grep -qE "$MARK" "$COMMIT"  && c=1
  if [[ "$s" == 1 && "$c" == 1 ]]; then
    echo "  ✅ 前缀/标志 [$MARK] 两文件都覆盖"; PASS=$((PASS+1))
  else
    echo "  ❌ [$MARK] 漂移：scan-secrets=$s scan-commit=$c（加/删厂商时两 scanner 须同步）" >&2
    FAIL=$((FAIL+1))
  fi
done

echo "─────────"
if (( FAIL )); then
  echo "❌ 密钥正则 parity 漂移：$FAIL 项 — scan-secrets.sh 与 scan-commit.sh 覆盖面不一致" >&2
  exit 1
fi
echo "✅ scan-secrets / scan-commit 厂商覆盖面一致（$PASS 项校验通过）"
