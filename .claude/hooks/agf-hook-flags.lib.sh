# .claude/hooks/agf-hook-flags.lib.sh
#
# hook profile 判定库（被 agf-hook-guard.sh source）。仿 ECC run-with-flags.js
# isHookEnabled 的 bash 等价物。AGF hook 全是 shell 脚本（security.md:37 刻意保
# shell 路径以便 git 评审 + 离线测试），不引 Node 包装。
#
# env:
#   AGF_HOOK_PROFILE=minimal|standard  （默认 standard）
#   AGF_DISABLED_HOOKS=id1,id2         （精确关单个非安全 hook）
#
# 安全边界（写死，改 = 改 ADR-014 + security.md）：
#   AGF_HOOK_IMMUTABLE 里的 hook（四层防御 + validate-verdict）永远启用，
#   不响应 profile、也不被 AGF_DISABLED_HOOKS 关 —— 安全 SSOT 不可降级。
#   AGF_HOOK_PROFILEABLE 里的 hook（6 个团队协调类）才看 profile。
#
# 本文件是**库**（被 source，不直接执行）：不设 set、只定义函数 + 数组，
# 避免污染调用者（guard）的 shell 状态。

# 永不响应 profile / DISABLED 的 hook（安全 SSOT，ADR-014）
AGF_HOOK_IMMUTABLE=(
  block-dangerous-bash
  block-config-edit
  enforce-write-scope
  scan-secrets
  sanitize-tool-output
  scan-commit
  validate-verdict
)

# 可降级的 hook（团队协调类，ADR-014）
# gate-deploy-release-auth（ADR-019）：部署/发布门授权归因——属协调类非安全防御，
# fast lane（minimal profile）可降级（fast lane 仍部署 + 冒烟，授权归因不属「步骤」只属「摩擦」）。
AGF_HOOK_PROFILEABLE=(
  teammate-keepalive
  check-progress-file
  session-start-context
  validate-task-schema
  gate-deploy-release-auth
  gate-redo-fuse
)

# agf_hook_enabled <hookId>
#   返回 0 = 启用（执行 real-script）
#   返回 1 = 跳过（profile 不匹配，guard exit 0 放行）
# fail-open：未知 hook id / 未知 profile 值 → 一律启用（不误关，匹配 AGF hook 哲学）
agf_hook_enabled() {
  local hook_id="${1:-}"
  # 无 id → 放行（guard 调用异常时 fail-open）
  [[ -z "$hook_id" ]] && return 0

  # 1) 安全 hook 永远启用（最高优先级，不可被 profile / DISABLED 关）
  local h
  for h in "${AGF_HOOK_IMMUTABLE[@]}"; do
    [[ "$hook_id" == "$h" ]] && return 0
  done

  # 2) AGF_DISABLED_HOOKS 精确关（只对非安全 hook 生效）
  local disabled="${AGF_DISABLED_HOOKS:-}"
  if [[ -n "$disabled" ]]; then
    case ",${disabled}," in
      *",${hook_id},"*) return 1 ;;
    esac
  fi

  # 3) 可降级 hook：看 profile
  local profileable=0
  for h in "${AGF_HOOK_PROFILEABLE[@]}"; do
    [[ "$hook_id" == "$h" ]] && { profileable=1; break; }
  done
  # 不在可降级名单的未知 hook → 保守启用
  [[ $profileable -eq 0 ]] && return 0

  case "${AGF_HOOK_PROFILE:-standard}" in
    minimal) return 1 ;;      # minimal：关所有可降级
    standard|"") return 0 ;;  # standard / 未设：全启用
    *) return 0 ;;            # 未知 profile 值：保守启用（fail-open）
  esac
}
