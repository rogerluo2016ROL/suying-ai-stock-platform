#!/bin/bash
# Tests for .claude/hooks/block-dangerous-bash.sh
#
# Run: bash .claude/hooks/test-block-dangerous-bash.sh
# Exits 0 if all assertions pass, 1 otherwise.
#
# Test categories:
#   A. False-positive scenarios — message/echo content mentioning a
#      dangerous string, must NOT be blocked.
#   B. True-positive scenarios — real dangerous invocations, MUST be blocked.
#   C. Chained scenarios — dangerous command after &&, ;, |, &, ||.
#   D. Edge cases — combined short flags, --force-with-lease, multi-line
#      heredoc commit messages, plain non-dangerous commands.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$HOOK_DIR/block-dangerous-bash.sh"

if [ ! -x "$HOOK" ]; then
  echo "FATAL: hook not executable at $HOOK" >&2
  exit 1
fi

PASS=0
FAIL=0
FAIL_LINES=()

run_hook() {
  local cmd="$1"
  local input
  input=$(jq -nc --arg c "$cmd" '{tool_input: {command: $c}}')
  local rc
  printf '%s' "$input" | "$HOOK" >/dev/null 2>&1
  rc=$?
  printf '%d\n' "$rc"
}

assert_block() {
  local desc="$1" cmd="$2"
  local rc
  rc=$(run_hook "$cmd")
  if [ "$rc" -eq 2 ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    FAIL_LINES+=("BLOCK expected (rc=2), got rc=$rc — [$desc] cmd=<<<$cmd>>>")
  fi
}

assert_pass() {
  local desc="$1" cmd="$2"
  local rc
  rc=$(run_hook "$cmd")
  if [ "$rc" -eq 0 ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    FAIL_LINES+=("PASS expected (rc=0), got rc=$rc — [$desc] cmd=<<<$cmd>>>")
  fi
}

# --------------------------------------------------------------------------
# Category B: True-positive — real dangerous commands MUST be blocked
# --------------------------------------------------------------------------

# AC-1: real recursive force delete blocked
assert_block "real recursive delete (rf)"        "rm -rf data/"
assert_block "real recursive delete (fr order)"  "rm -fr /tmp/scratch"
assert_block "real recursive delete (mixed)"     "rm -rfv /tmp/x"
assert_block "real recursive delete (caps)"      "rm -Rf /tmp/x"

# AC-2a: hard reset blocked
assert_block "hard reset"                         "git reset --hard HEAD~1"
assert_block "hard reset to ref"                  "git reset --hard origin/main"

# AC-2b: force push blocked (long flag)
assert_block "force push long flag"               "git push --force origin main"
assert_block "force push bare --force at EOL"     "git push --force"
assert_block "force chained with semicolon"       "git push --force; echo done"
assert_block "force chained with &&"              "git push --force && echo done"
assert_pass  "force-with-lease (safe variant)"    "git push --force-with-lease origin"
assert_pass  "force-with-lease no extra args"     "git push --force-with-lease"
assert_pass  "force-with-lease=ref form"          "git push --force-with-lease=feature:abc origin"
assert_pass  "force-if-includes (git 2.30+)"      "git push --force-if-includes origin feature"

# AC-2c: force push blocked (short flag, combined)
assert_block "force push short -f"                "git push -f"
assert_block "force push short -f with args"      "git push -f origin feature/x"
assert_block "force push combined -uf"            "git push -uf origin main"
assert_block "force push combined -fu"            "git push -fu origin main"

# AC-2d: schema drop blocked when invoked via SQL client
assert_block "psql DROP TABLE"                    "psql -h db -c 'DROP TABLE users'"
assert_block "psql drop database lowercase"       "psql -c \"drop database app\""
assert_block "mysql DROP SCHEMA"                  "mysql -e 'DROP SCHEMA legacy'"
assert_block "mariadb DROP TABLE"                 "mariadb -u root -e 'DROP TABLE x'"
assert_block "sqlite3 DROP TABLE"                 "sqlite3 db.sqlite 'DROP TABLE x;'"
assert_block "mongosh DROP DATABASE"              "mongosh --eval 'DROP DATABASE foo'"

# --------------------------------------------------------------------------
# Category A: False-positive — literal dangerous strings inside benign
# content commands. Must PASS (this is the bug fixed by this revision).
# --------------------------------------------------------------------------

# AC-3: commit message containing rm-recursive literal does NOT block
assert_pass "commit msg literal rf"               'git commit -m "fix: prevent rm -rf in production"'
assert_pass "commit msg literal fr order"         'git commit -m "fix: prevent rm -fr abuse"'
assert_pass "commit msg banner"                   'git commit -m "docs: forbid recursive deletes (rm -rf data/)"'

# AC-4: commit message containing schema-drop literal does NOT block
assert_pass "commit msg literal DROP TABLE"       'git commit -m "docs: ban DROP TABLE in tests"'
assert_pass "commit msg literal drop database"    'git commit -m "fix: avoid drop database on rerun"'

# AC-3b: commit message containing force-push literal does NOT block
assert_pass "commit msg literal force"            'git commit -m "policy: git push --force is forbidden"'
assert_pass "commit msg literal -f"               'git commit -m "policy: never run git push -f"'
assert_pass "commit msg literal hard reset"       'git commit -m "policy: forbid git reset --hard"'

# AC-5: commit -F just reads a file path; hook must not be confused by the
# literal "-F" flag and must not try to inspect the file content.
assert_pass "commit -F message file"              'git commit -F /tmp/msg.txt'
assert_pass "commit --file message file"          'git commit --file=/tmp/msg.txt'

# echo / printf with dangerous literal arguments: pass
assert_pass "echo literal rf"                     'echo "rm -rf is bad"'
assert_pass "printf literal DROP TABLE"           'printf "%s\n" "DROP TABLE example"'

# --------------------------------------------------------------------------
# Category C: Chained scenarios — dangerous command after a real chain
# operator MUST be blocked.
# --------------------------------------------------------------------------

# AC-6a: && chain
assert_block "chained && rm -rf"                  "echo done && rm -rf data"
assert_block "chained && reset --hard"            "git fetch && git reset --hard origin/main"
assert_block "chained && force push"              'git commit -m "msg" && git push --force'

# AC-6b: ; chain
assert_block "chained ; rm -rf"                   "echo done; rm -rf data"

# AC-6c: KNOWN LIMITATION (segment-internal hook scope, by design):
# Pipe-stdin SQL injection (echo "DROP TABLE x" | psql) is intentionally
# NOT blocked. The hook is a command-line flow gate, not a data-flow
# security boundary. Mitigation: standards/security.md "Hook Coverage
# Boundary" + "No Equivalent Bypass" agent discipline rules.
# Asserting PASS locks in the documented scope; failure here means the
# hook accidentally widened beyond design intent.
assert_pass "pipe-stdin SQL DROP (known limit)"   "echo 'DROP TABLE x' | psql mydb"

# AC-6d: || chain
assert_block "chained || rm -rf"                  "false || rm -rf /tmp/x"

# AC-6e: & (background) — single ampersand also a boundary
assert_block "chained & rm -rf"                   "long_task & rm -rf /tmp/x"

# Sanity: chained AFTER a benign commit message containing literal must
# still detect the chained dangerous command (this is the strongest false-
# positive-vs-false-negative discriminator).
assert_block "commit literal then real rm"        'git commit -m "fix: prevent rm -rf bug" && rm -rf /tmp/scratch'

# --------------------------------------------------------------------------
# Category D: Edge cases / regression sanity
# --------------------------------------------------------------------------

# AC-7a: benign git commands that look adjacent to dangerous ones — must pass
assert_pass "plain git push"                      "git push origin main"
assert_pass "plain git push -u"                   "git push -u origin feature/branch-fix"
assert_pass "plain git push branch with f"        "git push origin feature/fix"
assert_pass "plain git reset"                     "git reset HEAD"
assert_pass "plain git reset --soft"              "git reset --soft HEAD~1"
assert_pass "plain git reset --mixed"             "git reset --mixed"

# Plain rm without recursive flag: pass
assert_pass "plain rm single file"                "rm /tmp/scratch.txt"
assert_pass "rm -i prompt"                        "rm -i /tmp/scratch.txt"
assert_pass "rm -v verbose"                       "rm -v /tmp/scratch.txt"

# AC-8: BRE/ERE alternation pipe (|) inside a quoted regex pattern is data,
# not a shell chain operator. Quote-stripping in the hook removes the entire
# quoted run before anchor matching, which subsumes this case for any
# regex/text-processing tool (grep / awk / sed / rg / ag / perl / python -c
# etc.). Below covers the specific scenarios reported by reviewer + the
# inverse ordering that triggers the actual bug (dangerous verb directly
# after the BRE pipe).
assert_pass "grep BRE pipe before"                'grep "rm -rf\|other" file'
assert_pass "grep BRE pipe after (the actual bug)" 'grep "foo\|rm -rf" file'
assert_pass "grep ERE pipe -E"                    'grep -E "foo|rm -rf" file'
assert_pass "grep BRE pipe force"                 'grep "foo\|git push --force" file'
assert_pass "grep BRE pipe hard reset"            'grep "foo\|git reset --hard" file'
assert_pass "awk regex with pipe"                 'awk "/foo|rm -rf/" file'
assert_pass "sed s/// with pipe"                  'sed "s/foo|rm -rf/X/" file'
assert_pass "rg ripgrep BRE pipe"                 'rg "foo|rm -rf" .'
assert_pass "perl -e with pipe"                   'perl -e "print q(rm -rf)"'
assert_pass "cat | grep dangerous literal"        'cat foo | grep "rm -rf"'

# AC-8 negative: real chain after a grep/sed/awk segment must still block.
# The chain operator (&&, ;, ||) is OUTSIDE the quoted regex; the dangerous
# command after the chain is real top-level execution.
assert_block "grep BRE pipe + real && rm chain"   'grep "foo\|other" file && rm -rf data'
assert_block "grep BRE pipe + real ; rm chain"    'grep "foo\|other" file; rm -rf data'
assert_block "sed regex + real && force push"     'sed "s/x|y/z/" file && git push --force'

# DROP TABLE without SQL client invocation: pass (commit message in
# AC-4 already covers content-bearing case; this covers free-text use).
assert_pass "documentation prose with DROP"       'echo "DROP TABLE is destructive"'
assert_pass "shell var name DROP_TABLE"           'export DROP_TABLE_GUARD=1'

# Innocent commands
assert_pass "ls"                                  "ls -la"
assert_pass "cat README"                          "cat README.md"
assert_pass "touch file"                          "touch /tmp/x"
assert_pass "empty command"                       ""

# Multi-line heredoc commit message containing dangerous literals on its
# own line — must pass (this was a residual false-positive vector before
# the newline-flatten step in the hook).
HEREDOC_MSG=$'git commit -F /dev/stdin <<\'EOF\'\nfix: forbid rm -rf at runtime\nDROP TABLE forbidden in migrations\ngit push --force banned\nEOF'
assert_pass "multi-line heredoc commit message"   "$HEREDOC_MSG"

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

echo
echo "=========================================="
echo "block-dangerous-bash.sh test results"
echo "=========================================="
echo "PASS: $PASS"
echo "FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo
  echo "Failures:"
  for line in "${FAIL_LINES[@]}"; do
    echo "  - $line"
  done
  exit 1
fi
echo "All assertions passed."
exit 0
