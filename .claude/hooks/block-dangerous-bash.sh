#!/bin/bash
# PreToolUse hook: block destructive Bash commands.
# Exit 2 = block + show stderr message; Exit 0 = allow.
#
# Design (precision hardening, revised):
# - Patterns are anchored to command boundaries (^, ;, &, &&, |, ||) so a
#   dangerous verb only matches when it is the *executed* command, not when
#   it appears inside quoted argument content (e.g. a commit message that
#   discusses destructive operations).
# - Two-layer false-positive defense for fs/git patterns:
#     Layer 1 (anchor): dangerous verb must be at command-boundary position
#       (^ / ; / & / && / | / ||). Catches the bulk of commit-message
#       false-positives such as `git commit -m "fix: rm -rf"`.
#     Layer 2 (quote-strip): single + double quoted runs replaced with a
#       single space before pattern matching. Provides additional protection
#       for BRE/ERE pipe-alternation cases like `grep "foo|rm -rf" file`
#       where the `|` inside the quoted regex would otherwise match as a
#       shell chain operator at layer 1's anchor position.
# - For DROP TABLE/DATABASE/SCHEMA, the regex requires a known SQL/DB client
#   as the segment's leading verb. Quote stripping is NOT applied here, since
#   real `psql -c "DROP TABLE ..."` carries DROP inside quotes; the SQL_CLIENT
#   leading-verb gate is what prevents commit-message false-positives.
# - Multi-line commands (heredocs etc.) are flattened to a single line before
#   pattern matching, so multi-line message bodies mentioning dangerous
#   strings on their own line are not flagged. Trade-off: pure newline-
#   separated command chains (cmd1\\nrm) are not caught — agents in
#   practice use ; / && chains, which remain covered.
#
# This hook is a *flow gate*, not a security boundary. Determined bypass
# (eval, bash -c, shutil.rmtree, etc.) cannot be prevented by string
# matching. See `.claude/standards/security.md` "No Equivalent Bypass" for
# the agent-level rule that complements this hook.

set -uo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [ -z "$COMMAND" ]; then
  exit 0
fi

# Flatten newlines so heredoc / multi-line message bodies don't fool grep's
# line-based matching into thinking the body is a fresh top-level command.
COMMAND_FLAT=$(printf '%s' "$COMMAND" | tr '\n\r' '  ')

# Strip quoted-string contents (single + double quoted runs replaced with a
# single space) for fs/git pattern checks. Rationale:
# - rm/git push/git reset destructive operations are NEVER expressed inside
#   quoted argument contents in legitimate invocations; if `rm -rf` appears
#   inside quotes, it is data (commit message, grep/awk/sed pattern, echo
#   text, doc string) and should not block.
# - This is layer 2 in the defense (anchor matching is layer 1). Layer 2
#   provides additional protection for BRE/ERE pipe-alternation cases like
#   `grep "foo|rm -rf" file` where the `|` inside the quoted regex would
#   otherwise satisfy layer 1's anchor as if it were a shell chain operator.
# - SQL DROP detection (#4 below) intentionally runs against the unstripped
#   flat command, because real `psql -c "DROP TABLE ..."` carries DROP inside
#   double quotes; the SQL_CLIENT segment-leading-verb gate prevents the
#   commit-message false-positive there.
#
# KNOWN LIMITATION (nested escaped quotes):
# - `cmd "outer \"inner\" rm -rf"` — escaped inner double-quotes within an
#   outer double-quoted run cause the regex `"[^"]*"` to terminate at the
#   first inner `\"`, leaving part of the outer run unstripped.
# - This is an extreme corner case (bash agent invocations almost never use
#   nested escaped double-quotes; typical patterns use heredoc or single-
#   quote-wraps-double for literal quotes). When it does happen, the side
#   effect is **false positive only** (potential over-block of a legitimate
#   command), never false negative (no real destructive op slips through).
# - Mitigation if encountered: rephrase the command (heredoc, separate
#   args, single-quote wrap), or escalate to product-lead for manual run
#   per `.claude/standards/security.md` "No Equivalent Bypass".
COMMAND_STRIPPED=$(printf '%s' "$COMMAND_FLAT" | sed -E 's/"[^"]*"/ /g; s/'\''[^'\'']*'\''/ /g')

# Anchor: position at the very start of the command or immediately after a
# chain operator. Single `&` matches both `&` (background) and the first
# `&` of `&&` — both are real command boundaries.
ANCHOR='(^|;|&&|&|\|\||\|)[[:space:]]*'

# SQL client gate — used by rule #4 (defined here for fast path).
SQL_CLIENT='(psql|mysql|mariadb|sqlite|sqlite3|sqlcmd|mongo|mongosh|clickhouse-client|cqlsh)'

# ---- Fast path ---------------------------------------------------------------
# Two combined regexes (STRIPPED + FLAT) cover all four rules. Clean commands
# (the vast majority of Bash tool calls) exit here after 2 grep forks instead
# of 4. Slow path below re-checks each rule individually to emit a specific
# block message.
FAST_STRIPPED="${ANCHOR}rm[[:space:]]+-[a-zA-Z]*[rR][a-zA-Z]*f"
FAST_STRIPPED="$FAST_STRIPPED|${ANCHOR}rm[[:space:]]+-[a-zA-Z]*f[a-zA-Z]*[rR]"
FAST_STRIPPED="$FAST_STRIPPED|${ANCHOR}git[[:space:]]+push\b([^;&|]*[[:space:]])?-[a-z]{0,3}f[a-z]{0,3}\b"
FAST_STRIPPED="$FAST_STRIPPED|${ANCHOR}git[[:space:]]+push\b[^;&|]*--force([[:space:];&|]|$)"
FAST_STRIPPED="$FAST_STRIPPED|${ANCHOR}git[[:space:]]+reset[[:space:]]+--hard\b"
FAST_FLAT="${ANCHOR}${SQL_CLIENT}\b[^;&|]*\bDROP[[:space:]]+(TABLE|DATABASE|SCHEMA)\b"

if ! printf '%s' "$COMMAND_STRIPPED" | grep -qE "$FAST_STRIPPED" \
   && ! printf '%s' "$COMMAND_FLAT" | grep -qiE "$FAST_FLAT"; then
  exit 0
fi

# ---- Slow path (only on suspicious commands) ---------------------------------

# 1) Recursive force delete — flag cluster contains both r/R and f (any order,
# possibly mixed with other letters). Capital R is a valid recursive flag on
# BSD/macOS rm (equivalent to -r), so the pattern accepts both r and R.
# Runs against COMMAND_STRIPPED (quoted contents removed).
if printf '%s' "$COMMAND_STRIPPED" | grep -qE \
  "${ANCHOR}rm[[:space:]]+-[a-zA-Z]*[rR][a-zA-Z]*f|${ANCHOR}rm[[:space:]]+-[a-zA-Z]*f[a-zA-Z]*[rR]"; then
  echo "Blocked: recursive force delete is not allowed. Use targeted file removal instead." >&2
  exit 2
fi

# 2) Force push — covers --force, short -f, and combined short clusters
# (-af, -fu, -uf). Explicitly does NOT block the safer variants:
#   --force-with-lease (refuses overwrite if remote has unseen commits)
#   --force-if-includes (git 2.30+, requires our base to include remote's tip)
# Both are accepted-by-default in agent workflows because they fail closed
# under conflict. The boundary `([[:space:];&|]|$)` after `--force` ensures
# we only match the bare `--force` flag, not `--force-with-lease` etc.
#
# Short-flag cluster is capped at 7 chars (3 letters before f + f + 3 after)
# to avoid matching long arg names that contain 'f' (e.g. branch name
# "feature/fix"). Real git short-flag clusters always fit easily.
# Runs against COMMAND_STRIPPED.
if printf '%s' "$COMMAND_STRIPPED" | grep -qE \
  "${ANCHOR}git[[:space:]]+push\b([^;&|]*[[:space:]])?-[a-z]{0,3}f[a-z]{0,3}\b|${ANCHOR}git[[:space:]]+push\b[^;&|]*--force([[:space:];&|]|$)"; then
  echo "Blocked: force push is not allowed (use --force-with-lease for safe history rewrites)." >&2
  exit 2
fi

# 3) Hard reset. Runs against COMMAND_STRIPPED.
if printf '%s' "$COMMAND_STRIPPED" | grep -qE \
  "${ANCHOR}git[[:space:]]+reset[[:space:]]+--hard\b"; then
  echo "Blocked: hard reset requires manual confirmation." >&2
  exit 2
fi

# 4) Schema drop via known SQL/DB client (segment-internal: client is the
# segment's leading verb followed by an inline DROP keyword). Bare DROP
# strings inside commit messages / echo / printf / heredoc are not flagged.
#
# KNOWN LIMITATION (segment-internal scope, by design):
# - Direct invocation `psql -c "DROP TABLE..."` ← blocked.
# - Pipe-stdin / heredoc / file input data flow (e.g.
#   `echo "DROP TABLE x" | psql mydb`, `psql -f migration.sql`) is NOT
#   blocked. This hook is a *command-line flow gate*, not a *data-flow
#   security boundary*. Mitigation: agent-level discipline per
#   `.claude/standards/security.md` "Hook Coverage Boundary" + "No
#   Equivalent Bypass" rules.
if printf '%s' "$COMMAND_FLAT" | grep -qiE \
  "${ANCHOR}${SQL_CLIENT}\b[^;&|]*\bDROP[[:space:]]+(TABLE|DATABASE|SCHEMA)\b"; then
  echo "Blocked: schema drop requires manual execution." >&2
  exit 2
fi

exit 0
