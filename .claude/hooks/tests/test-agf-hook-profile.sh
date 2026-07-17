#!/bin/bash
# test-agf-hook-profile.sh — agf-hook-guard + agf-hook-flags 的 profile 机制回归
#
# 覆盖：
#   AC-1  minimal profile 跳过 4 个可降级 hook
#   AC-2  standard / 未设 profile 全启用
#   AC-3  安全边界：四层防御 + validate-verdict 在 minimal 下仍启用
#   AC-4  AGF_DISABLED_HOOKS 精确关单个非安全 hook
#   AC-5  安全 hook 即使被列入 DISABLED_HOOKS 仍启用（边界硬约束）
#   AC-6  fail-open：未知 hook id / 未知 profile 值 → 启用
#   AC-7  guard 端到端：minimal 下调可降级 hook → exit 0 不执行 real-script
#   AC-8  guard 端到端：minimal 下调安全 hook → 执行 real-script

set -uo pipefail

GUARD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$GUARD_DIR/agf-hook-flags.lib.sh"
GUARD="$GUARD_DIR/agf-hook-guard.sh"

[ -f "$LIB" ]   || { echo "FAIL: lib 缺失 $LIB"; exit 1; }
[ -x "$GUARD" ] || { echo "FAIL: guard 缺失/不可执行 $GUARD"; exit 1; }

# shellcheck source=../agf-hook-flags.lib.sh
source "$LIB"

PASS=0; FAIL=0; FAIL_LINES=()

# agf_hook_enabled <hookId> → 0=启用 1=跳过
# check_enabled <desc> <expectEnabled 0|1> <hookId>
check_enabled() {
  local desc="$1" expect="$2" hook="$3"
  agf_hook_enabled "$hook"; local rc=$?
  local got; [ $rc -eq 0 ] && got=1 || got=0   # rc0 → enabled=1
  if [ "$got" = "$expect" ]; then PASS=$((PASS+1));
  else FAIL=$((FAIL+1)); FAIL_LINES+=("$desc: hook=$hook expect=enabled($expect) got=enabled($got) rc=$rc"); fi
}

# AC-3 安全 hook 任何 profile 下启用（安全边界）
AGF_HOOK_PROFILE=minimal
check_enabled "AC-3a minimal block-dangerous-bash" 1 block-dangerous-bash
check_enabled "AC-3b minimal scan-secrets"          1 scan-secrets
check_enabled "AC-3c minimal sanitize-tool-output"  1 sanitize-tool-output
check_enabled "AC-3d minimal scan-commit"           1 scan-commit
check_enabled "AC-3e minimal validate-verdict"      1 validate-verdict

# AC-1 minimal 跳过 4 个可降级
check_enabled "AC-1a minimal teammate-keepalive"     0 teammate-keepalive
check_enabled "AC-1b minimal check-progress-file"    0 check-progress-file
check_enabled "AC-1c minimal session-start-context"  0 session-start-context
check_enabled "AC-1d minimal validate-task-schema"   0 validate-task-schema

# AC-2 standard 全启用
AGF_HOOK_PROFILE=standard
check_enabled "AC-2a standard teammate-keepalive"   1 teammate-keepalive
check_enabled "AC-2b standard validate-verdict"     1 validate-verdict

# AC-2 未设 profile = standard
unset AGF_HOOK_PROFILE
check_enabled "AC-2c unset teammate-keepalive"      1 teammate-keepalive

# AC-4 DISABLED 精确关非安全 hook
AGF_HOOK_PROFILE=standard
AGF_DISABLED_HOOKS="teammate-keepalive,check-progress-file"
check_enabled "AC-4a disabled teammate-keepalive"    0 teammate-keepalive
check_enabled "AC-4b disabled check-progress-file"   0 check-progress-file
check_enabled "AC-4c not-disabled session-start"     1 session-start-context
unset AGF_DISABLED_HOOKS

# AC-5 安全 hook 即使在 DISABLED 里仍启用（边界硬约束）
AGF_HOOK_PROFILE=minimal
AGF_DISABLED_HOOKS="block-dangerous-bash,validate-verdict"
check_enabled "AC-5a immutable+disabled block-dangerous-bash" 1 block-dangerous-bash
check_enabled "AC-5b immutable+disabled validate-verdict"     1 validate-verdict
unset AGF_DISABLED_HOOKS

# AC-6 fail-open：未知 hook / 未知 profile
AGF_HOOK_PROFILE=minimal
check_enabled "AC-6a unknown hook"        1 some-unknown-hook
AGF_HOOK_PROFILE=weird-value
check_enabled "AC-6b unknown profile val" 1 teammate-keepalive
unset AGF_HOOK_PROFILE

# AC-7/AC-8 guard 端到端：用一个 sentinel real-script 检测是否被执行
SENTINEL="$(mktemp)"
trap 'rm -f "$SENTINEL"' EXIT
cat > "$SENTINEL" <<'EOF'
#!/usr/bin/env bash
cat > /dev/null   # 消费 stdin
echo "REAL_RAN" >&2
exit 0
EOF
chmod +x "$SENTINEL"

# AC-7 minimal 下可降级 hook → guard exit 0 + real-script 不执行（无 REAL_RAN）
#   guard 是子进程，env 须前置（shell 变量不传子进程；生产环境同理须 export）
out=$(echo '{"test":1}' | AGF_HOOK_PROFILE=minimal "$GUARD" teammate-keepalive "$SENTINEL" 2>&1); rc=$?
if [ $rc -eq 0 ] && ! echo "$out" | grep -q REAL_RAN; then PASS=$((PASS+1));
else FAIL=$((FAIL+1)); FAIL_LINES+=("AC-7: minimal guard 应跳过 real-script (rc=$rc out=$out)"); fi

# AC-8 minimal 下安全 hook → guard 执行 real-script（有 REAL_RAN）
out=$(echo '{"test":1}' | AGF_HOOK_PROFILE=minimal "$GUARD" block-dangerous-bash "$SENTINEL" 2>&1); rc=$?
if echo "$out" | grep -q REAL_RAN; then PASS=$((PASS+1));
else FAIL=$((FAIL+1)); FAIL_LINES+=("AC-8: minimal 安全 hook 应执行 real-script (rc=$rc out=$out)"); fi

unset AGF_HOOK_PROFILE

# summary
echo "=========================================="
echo "test-agf-hook-profile"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
[ $FAIL -gt 0 ] && { printf '  - %s\n' "${FAIL_LINES[@]}"; exit 1; }
exit 0
