#!/bin/bash
# UserPromptSubmit hook: suggest relevant skills/commands based on prompt keywords + paths.
# SOFT advisory — never blocks. Exit 0 + WARNING-style stderr.
#
# Reads rules from .claude/hooks/skill-rules.json. Each rule has:
#   matches.prompt_regex   — list of POSIX-extended regex run with `grep -E`
#   matches.path_patterns  — list of POSIX-extended regex matched against the prompt text
#                            (we extract path-like tokens with a coarse regex first)
#   suggest.skill          — name shown in the suggestion
#   suggest.reason         — one-line WHY
#
# Design notes:
# - Conservative: at most 3 suggestions emitted per prompt, dedup'd by rule.id
# - Hook is registered alongside scan-secrets.sh on UserPromptSubmit (both run, both must pass)
# - jq dependency: same as scan-secrets.sh
#
# Reference: skill-rules.json hook engine pattern from ChrisWiles/claude-code-showcase

set -uo pipefail

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')

if [ -z "$PROMPT" ]; then
  exit 0
fi

RULES_FILE="$(dirname "$0")/skill-rules.json"
if [ ! -f "$RULES_FILE" ]; then
  exit 0
fi

# Flatten newlines for line-based grep matching.
PROMPT_FLAT=$(printf '%s' "$PROMPT" | tr '\n\r' '  ')

# Extract path-like tokens (anything looking like dir/file or ./dir/file).
# Coarse: tokens with at least one '/' and ending with .md|.py|.ts|.tsx|.js|.jsx|.json|.yml|.yaml|.sh
# or starting with docs/ / backend/ / frontend/ / miniapp/ / .claude/
PATH_TOKENS=$(printf '%s' "$PROMPT_FLAT" | grep -oE '(\.?\/?(docs|backend|frontend|miniapp|\.claude)\/[A-Za-z0-9_./*\-]+)|([A-Za-z0-9_\-]+\.(md|py|ts|tsx|js|jsx|json|ya?ml|sh))' | head -20)

SUGGESTIONS=()
SEEN_IDS=""

# Single jq call extracts all rules into TSV (was 4+ jq forks per rule × 10 rules = ~41 forks).
# Per-rule fields tab-separated; patterns within a field separated by US (\x1f) since
# skill-rules.json patterns never contain tab or US.
RULES_TSV=$(jq -r '
  .rules[] | [
    .id,
    .suggest.skill,
    .suggest.reason,
    ((.matches.prompt_regex // []) | join("")),
    ((.matches.path_patterns // []) | join(""))
  ] | @tsv
' "$RULES_FILE")

while IFS=$'\t' read -r ID SKILL REASON PROMPT_PATS PATH_PATS; do
  [ -z "$ID" ] && continue
  case " $SEEN_IDS " in *" $ID "*) continue ;; esac

  MATCHED=0

  if [ -n "$PROMPT_PATS" ]; then
    IFS=$'\x1f' read -ra PATS <<< "$PROMPT_PATS"
    for pat in "${PATS[@]}"; do
      [ -z "$pat" ] && continue
      if printf '%s' "$PROMPT_FLAT" | grep -qE "$pat"; then MATCHED=1; break; fi
    done
  fi

  if [ "$MATCHED" -eq 0 ] && [ -n "$PATH_TOKENS" ] && [ -n "$PATH_PATS" ]; then
    IFS=$'\x1f' read -ra PATS <<< "$PATH_PATS"
    for pat in "${PATS[@]}"; do
      [ -z "$pat" ] && continue
      if printf '%s' "$PATH_TOKENS" | grep -qE "$pat"; then MATCHED=1; break; fi
    done
  fi

  if [ "$MATCHED" -eq 1 ]; then
    SUGGESTIONS+=("  💡 [$ID] use skill \`$SKILL\` — $REASON")
    SEEN_IDS="$SEEN_IDS $ID"
    [ "${#SUGGESTIONS[@]}" -ge 3 ] && break
  fi
done <<< "$RULES_TSV"

if [ "${#SUGGESTIONS[@]}" -gt 0 ]; then
  {
    echo "skill-suggester: matched ${#SUGGESTIONS[@]} rule(s) for this prompt"
    for s in "${SUGGESTIONS[@]}"; do
      echo "$s"
    done
    echo "  (advisory only — hooks never auto-invoke skills; consider whether to call Skill tool)"
  } >&2
fi

exit 0
