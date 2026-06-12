## T-306 Backtest Criticals 修复 - 2026-06-12
**状态**: 已完成
**Skills**: superpowers:verification-before-completion

**SIT 证据**（按 AC 列）:
- [x] C-1 认证拦截器绕过修复 ✅ — `fetch('/api/v1/strategy/plans')` 已移除；`strategyPlans` state 与 loading effect 一并清理（`strategy_id` 字段随 C-2 移除后为死代码）
- [x] C-2 移除 4 个 no-op 表单字段 ✅ — `date_range`/`strategy_id`/`initial_capital`/`benchmark` 已从 Form 删除；相关死代码（`DatePicker` import、`RangePicker`、`BENCHMARK_OPTIONS`、`strategyPlans` state）已清理
- [x] AC-306.3 tsc + build 通过 ✅
    - 命令: `cd frontend && npx tsc -b --noEmit`
    - 输出: (无错误，exit 0)
    - 命令: `cd frontend && npm run build`
    - 输出: `✓ built in 3.24s` (3681 modules, dist/assets/index-CtKc1L8b.js 2697.94 kB)

**质量门**: lint ✅ / typecheck ✅ / unit ✅ / SIT ✅

**下一步**: 等待 code-review
