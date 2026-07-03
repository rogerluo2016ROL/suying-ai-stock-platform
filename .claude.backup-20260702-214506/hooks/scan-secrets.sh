#!/bin/bash
# UserPromptSubmit hook: block prompts containing secret/credential patterns.
# Exit 2 = block + show stderr message; Exit 0 = allow.
#
# Design:
# - Runs on every user prompt before it reaches the model. If a known secret
#   pattern (AWS key / OpenAI key / GitHub token / Anthropic key / private key
#   header) is found, block immediately so the secret is never logged in
#   conversation history or sent to the API.
# - Patterns are conservative: chosen for low false-positive rate. Generic
#   high-entropy detection is intentionally NOT applied here because the prompt
#   is human text and would over-block (commit hashes, UUIDs, etc.).
# - This is a *flow gate*, not exhaustive DLP. Determined paste of unrecognized
#   secret formats cannot be prevented; pair with `.claude/standards/security.md`
#   "Secrets Handling" rule.
#
# Reference: https://github.com/dwarvesf/claude-guardrails (UserPromptSubmit pattern)

set -uo pipefail

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')

if [ -z "$PROMPT" ]; then
  exit 0
fi

# Flatten newlines for line-based grep matching across multi-line prompts.
PROMPT_FLAT=$(printf '%s' "$PROMPT" | tr '\n\r' '  ')

# ---- Fast path ---------------------------------------------------------------
# Single combined regex covering rules #1-#8 + PuTTY string from #10.
# Rule #9 (BIP39) is two-factor so we short-circuit on the keyword first.
# Clean prompts (99%+) exit here, avoiding ~10 individual grep forks.
COMBINED='\b(AKIA|ASIA)[0-9A-Z]{16}\b'
COMBINED="$COMBINED"'|\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b'
COMBINED="$COMBINED"'|\bgithub_pat_[A-Za-z0-9_]{60,}\b'
COMBINED="$COMBINED"'|\bsk-(ant-|proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b'
COMBINED="$COMBINED"'|\bAIza[0-9A-Za-z_-]{35}\b'
COMBINED="$COMBINED"'|\bxox[abprs]-[A-Za-z0-9-]{10,}\b'
COMBINED="$COMBINED"'|\-\-\-\-\-BEGIN[[:space:]]+(RSA|EC|DSA|OPENSSH|PGP|PRIVATE|ENCRYPTED)[[:space:]]*(PRIVATE[[:space:]]+)?KEY\-\-\-\-\-'
COMBINED="$COMBINED"'|\b(DEEPSEEK_API_KEY|ARK_API_KEY|DASHSCOPE_API_KEY|MINIMAX_API_KEY|QWEN_API_KEY|DOUBAO_API_KEY)[[:space:]]*=[[:space:]]*[A-Za-z0-9_.+/=-]{20,}'
COMBINED="$COMBINED"'|\b(APP_STORE_CONNECT_API_KEY|ASC_API_KEY|MATCH_PASSWORD|FASTLANE_PASSWORD|FASTLANE_SESSION)[[:space:]]*=[[:space:]]*[^[:space:]]{8,}'
COMBINED="$COMBINED"'|PuTTY-User-Key-File-[23]:'

if ! printf '%s' "$PROMPT_FLAT" | grep -qE "$COMBINED"; then
  # No high-confidence pattern matched. Final check: BIP39 keyword absence.
  if ! printf '%s' "$PROMPT_FLAT" | grep -qiE '\b(bip[ -]?39|mnemonic|seed[[:space:]]+phrase|recovery[[:space:]]+phrase|wallet[[:space:]]+phrase)\b'; then
    exit 0
  fi
  # BIP39 keyword present — fall through to slow path #9 second-factor check.
fi

# ---- Slow path (only on suspicious prompts) ----------------------------------

# 1) AWS Access Key ID (AKIA / ASIA prefix + 16 base32 chars)
if printf '%s' "$PROMPT_FLAT" | grep -qE '\b(AKIA|ASIA)[0-9A-Z]{16}\b'; then
  echo "Blocked: prompt contains an AWS access key. Remove the secret and use env vars / secret manager." >&2
  exit 2
fi

# 2) GitHub tokens (ghp_/gho_/ghu_/ghs_/ghr_/github_pat_ prefix)
if printf '%s' "$PROMPT_FLAT" | grep -qE '\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b'; then
  echo "Blocked: prompt contains a GitHub token. Revoke it and use env vars / GitHub Actions secrets." >&2
  exit 2
fi

# 3) Anthropic API keys (sk-ant- prefix) — checked BEFORE generic sk- so the
# more specific message wins.
if printf '%s' "$PROMPT_FLAT" | grep -qE '\bsk-ant-[A-Za-z0-9_-]{20,}\b'; then
  echo "Blocked: prompt contains an Anthropic API key. Remove the secret and use env vars." >&2
  exit 2
fi

# 4) OpenAI API keys (sk- + 32+ chars, sk-proj- variant, sk-svcacct- variant)
# Negative lookahead is not POSIX, so we explicitly exclude sk-ant- via a separate
# anchor check.
if printf '%s' "$PROMPT_FLAT" | grep -qE '\bsk-(proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b' \
   && ! printf '%s' "$PROMPT_FLAT" | grep -qE '\bsk-ant-'; then
  echo "Blocked: prompt contains an OpenAI-style API key (sk-...). Remove the secret and use env vars." >&2
  exit 2
fi

# 5) Google API keys (AIza prefix + 35 chars)
if printf '%s' "$PROMPT_FLAT" | grep -qE '\bAIza[0-9A-Za-z_-]{35}\b'; then
  echo "Blocked: prompt contains a Google API key. Remove the secret and rotate it." >&2
  exit 2
fi

# 6) Slack tokens (xox[abprs]- prefix)
if printf '%s' "$PROMPT_FLAT" | grep -qE '\bxox[abprs]-[A-Za-z0-9-]{10,}\b'; then
  echo "Blocked: prompt contains a Slack token. Remove the secret and rotate it." >&2
  exit 2
fi

# 7) PEM private key headers
if printf '%s' "$PROMPT_FLAT" | grep -qE '\-\-\-\-\-BEGIN[[:space:]]+(RSA|EC|DSA|OPENSSH|PGP|PRIVATE|ENCRYPTED)[[:space:]]*(PRIVATE[[:space:]]+)?KEY\-\-\-\-\-'; then
  echo "Blocked: prompt contains a private key block. Never paste private keys into chat — use a secret manager." >&2
  exit 2
fi

# 8) China LLM provider tokens — defensive for project's actual stack
# DeepSeek / Doubao / Qwen / MiniMax usually use long opaque base64-ish tokens
# under env names like DEEPSEEK_API_KEY=, ARK_API_KEY=, DASHSCOPE_API_KEY=,
# MINIMAX_API_KEY=. Catch the inline `KEY=value` form when value looks
# secret-like (>=20 chars, mixed case + digits/symbols).
if printf '%s' "$PROMPT_FLAT" | grep -qE '\b(DEEPSEEK_API_KEY|ARK_API_KEY|DASHSCOPE_API_KEY|MINIMAX_API_KEY|QWEN_API_KEY|DOUBAO_API_KEY)[[:space:]]*=[[:space:]]*[A-Za-z0-9_.+/=-]{20,}'; then
  echo "Blocked: prompt contains a China-LLM provider API key. Remove the secret and use env vars / .env file (gitignored)." >&2
  exit 2
fi

# 8b) Apple signing credentials (App Store Connect API key env / fastlane match
# password / fastlane session) — defensive for the apple-* track (ADR-009).
# Note: pasted .p8 file CONTENT is a PEM "BEGIN PRIVATE KEY" block → already
# caught by rule #7; this rule catches the inline `KEY=value` credential form.
if printf '%s' "$PROMPT_FLAT" | grep -qE '\b(APP_STORE_CONNECT_API_KEY|ASC_API_KEY|MATCH_PASSWORD|FASTLANE_PASSWORD|FASTLANE_SESSION)[[:space:]]*=[[:space:]]*[^[:space:]]{8,}'; then
  echo "Blocked: prompt contains Apple signing credentials (App Store Connect API key / match password). Use env vars / Keychain — never paste signing secrets." >&2
  exit 2
fi

# 9) BIP39 mnemonic / wallet seed phrases (heuristic, low-FP)
# Two-factor match: explicit keyword (mnemonic/seed phrase/recovery phrase/BIP39) AND
# a sequence of 12+ short lowercase ASCII words separated by spaces (typical BIP39 form).
# Single-factor would over-block ordinary prose; both factors together is rare outside
# real seed phrases.
if printf '%s' "$PROMPT_FLAT" | grep -qiE '\b(bip[ -]?39|mnemonic|seed[[:space:]]+phrase|recovery[[:space:]]+phrase|wallet[[:space:]]+phrase)\b' \
   && printf '%s' "$PROMPT_FLAT" | grep -qE '\b([a-z]{3,8}[[:space:]]+){11,}[a-z]{3,8}\b'; then
  echo "Blocked: prompt may contain a BIP39 mnemonic / wallet seed phrase. Never paste recovery phrases — use a hardware wallet or password manager." >&2
  exit 2
fi

# 10) Generic high-entropy private key indicators that slip past PEM check
# (e.g. ed25519 raw bytes block, ssh authorized_keys-formatted private content)
if printf '%s' "$PROMPT_FLAT" | grep -qE 'BEGIN[[:space:]]+OPENSSH[[:space:]]+PRIVATE[[:space:]]+KEY' \
   || printf '%s' "$PROMPT_FLAT" | grep -qE 'PuTTY-User-Key-File-[23]:'; then
  echo "Blocked: prompt contains an SSH/PuTTY private key block. Never paste private keys — use ssh-agent / secret manager." >&2
  exit 2
fi

exit 0
