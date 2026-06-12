#!/bin/bash
# Git pre-commit hook: scan staged diff for secrets that the UserPromptSubmit
# hook would have blocked at chat time but could leak via Edit/Write through
# disk → git stage path.
#
# Install (run once per clone):
#   ln -sf ../../.claude/hooks/scan-commit.sh .git/hooks/pre-commit
#   chmod +x .claude/hooks/scan-commit.sh
#
# Behavior:
# - Exits 0 (allow commit) when staged diff is clean
# - Exits 1 (block commit) when any secret pattern matches; prints which file + which pattern
# - Bypass for true emergencies: `git commit --no-verify` (logged in security.md as
#   discouraged; please open an incident note)
#
# Patterns mirror .claude/hooks/scan-secrets.sh — 覆盖面 parity 由
# hooks/tests/test-secret-pattern-parity.sh 机器强制（加厂商只改一边会 fail），无需人工盯。
# EXCEPT rule #11 which is commit-only by design (see #11 inline comment for rationale).
# Reference: https://github.com/dwarvesf/claude-guardrails (scan-commit pattern)

set -uo pipefail

# Capture staged diff (text only — binary files are skipped automatically by -G/-S
# patterns, but we explicitly use --diff-filter to skip deletions).
DIFF=$(git diff --staged --diff-filter=ACMR --no-color 2>/dev/null)

if [ -z "$DIFF" ]; then
  exit 0
fi

# Only inspect added lines (start with `+` but not `+++` file marker) so renames
# and deletions don't trip the scanner on already-existing patterns.
ADDED=$(echo "$DIFF" | grep -E '^\+[^+]' || true)

if [ -z "$ADDED" ]; then
  exit 0
fi

FAIL=0
report() {
  local pattern="$1"
  local sample="$2"
  echo ""
  echo "🚫 scan-commit: blocked — $pattern"
  echo "   Sample line (first match):"
  echo "   $sample" | head -c 200
  echo ""
  FAIL=1
}

# 1) AWS access key
m=$(echo "$ADDED" | grep -E '\b(AKIA|ASIA)[0-9A-Z]{16}\b' | head -1 || true)
[ -n "$m" ] && report "AWS access key (AKIA/ASIA)" "$m"

# 2) GitHub tokens
m=$(echo "$ADDED" | grep -E '\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b' | head -1 || true)
[ -n "$m" ] && report "GitHub token (ghp_/github_pat_)" "$m"

# 3) Anthropic key
m=$(echo "$ADDED" | grep -E '\bsk-ant-[A-Za-z0-9_-]{20,}\b' | head -1 || true)
[ -n "$m" ] && report "Anthropic API key (sk-ant-)" "$m"

# 4) OpenAI-style key (excluding Anthropic prefix)
m=$(echo "$ADDED" | grep -E '\bsk-(proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b' | grep -vE '\bsk-ant-' | head -1 || true)
[ -n "$m" ] && report "OpenAI-style key (sk-...)" "$m"

# 5) Google API key
m=$(echo "$ADDED" | grep -E '\bAIza[0-9A-Za-z_-]{35}\b' | head -1 || true)
[ -n "$m" ] && report "Google API key (AIza)" "$m"

# 6) Slack token
m=$(echo "$ADDED" | grep -E '\bxox[abprs]-[A-Za-z0-9-]{10,}\b' | head -1 || true)
[ -n "$m" ] && report "Slack token (xox.-)" "$m"

# 7) PEM private keys
m=$(echo "$ADDED" | grep -E '\-\-\-\-\-BEGIN[[:space:]]+(RSA|EC|DSA|OPENSSH|PGP|PRIVATE|ENCRYPTED)[[:space:]]*(PRIVATE[[:space:]]+)?KEY\-\-\-\-\-' | head -1 || true)
[ -n "$m" ] && report "PEM private key block" "$m"

# 8) China LLM provider keys (inline KEY=value)
m=$(echo "$ADDED" | grep -E '\b(DEEPSEEK_API_KEY|ARK_API_KEY|DASHSCOPE_API_KEY|MINIMAX_API_KEY|QWEN_API_KEY|DOUBAO_API_KEY)[[:space:]]*=[[:space:]]*[A-Za-z0-9_.+/=-]{20,}' | head -1 || true)
[ -n "$m" ] && report "China-LLM provider key (DeepSeek/Doubao/Qwen/MiniMax)" "$m"

# 8b) Apple signing credentials (mirror scan-secrets.sh rule 8b; .p8 content = PEM → rule #7)
m=$(echo "$ADDED" | grep -E '\b(APP_STORE_CONNECT_API_KEY|ASC_API_KEY|MATCH_PASSWORD|FASTLANE_PASSWORD|FASTLANE_SESSION)[[:space:]]*=[[:space:]]*[^[:space:]]{8,}' | head -1 || true)
[ -n "$m" ] && report "Apple signing credentials (ASC API key / match password)" "$m"

# 9) BIP39 mnemonic — keyword + 12+ short lowercase words on the same diff line
m=$(echo "$ADDED" | grep -iE '\b(bip[ -]?39|mnemonic|seed[[:space:]]+phrase|recovery[[:space:]]+phrase|wallet[[:space:]]+phrase)\b' \
                 | grep -E '\b([a-z]{3,8}[[:space:]]+){11,}[a-z]{3,8}\b' | head -1 || true)
[ -n "$m" ] && report "BIP39 mnemonic / wallet seed phrase" "$m"

# 10) PuTTY private key
m=$(echo "$ADDED" | grep -E 'PuTTY-User-Key-File-[23]:' | head -1 || true)
[ -n "$m" ] && report "PuTTY private key" "$m"

# 11) Generic high-entropy: long base64-ish token preceded by *_TOKEN= / *_SECRET= / *_KEY=
# COMMIT-ONLY BY DESIGN — scan-secrets.sh deliberately omits this catch-all because
# conversational prompts contain commit hashes / UUIDs / random strings that would
# trigger false-positives. See scan-secrets.sh header "Generic high-entropy detection
# is intentionally NOT applied here". Do NOT port this rule to scan-secrets.sh.
m=$(echo "$ADDED" | grep -E '\b[A-Z][A-Z0-9_]{2,}_(TOKEN|SECRET|KEY|PASSWORD|PASSWD|PWD|API_KEY)[[:space:]]*=[[:space:]]*["'\'']?[A-Za-z0-9_.+/=-]{32,}' | head -1 || true)
[ -n "$m" ] && report "Generic *_TOKEN/_SECRET/_KEY= with high-entropy value" "$m"

if [ "$FAIL" -ne 0 ]; then
  echo ""
  echo "Commit blocked. Remove the secret(s) and re-stage."
  echo "If this is a documented test fixture (and you accept the risk), bypass with:"
  echo "    git commit --no-verify"
  echo "(--no-verify usage should be logged in docs/reviews/ per .claude/standards/security.md)"
  exit 1
fi

# Secret scan 通过后，跑 lint-all（语法/JSON/YAML 校验）on staged files
# 注：可通过 SKIP_LINT_ALL=1 临时跳过（仅 emergency；ditto with secret bypass）
if [ -z "${SKIP_LINT_ALL:-}" ] && [ -x .claude/scripts/lint-all.sh ]; then
  if ! bash .claude/scripts/lint-all.sh --pre-commit; then
    echo "" >&2
    echo "Commit blocked by lint-all. Fix the failures above and re-stage." >&2
    echo "Emergency bypass: SKIP_LINT_ALL=1 git commit ..." >&2
    exit 1
  fi
fi

exit 0
