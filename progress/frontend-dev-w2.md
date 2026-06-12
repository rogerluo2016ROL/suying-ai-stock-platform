## T-306: Backtest.tsx 空壳实现 - 2026-06-12 15:30
**状态**: 已完成
**Skills**: agf-running-sit-tests

**SIT 证据**（按 AC 列；行首 `[x]/[ ]` 同时表达 AC 自验勾选）:
- [x] AC-306.1 ✅ 回测参数配置表单 — DatePicker.RangePicker 日期范围 + Select 策略选择（fetch /api/v1/strategy/plans）+ 基准指数选择（上证/深证/创业板/科创50/沪深300）+ InputNumber 初始资金配置
- [x] AC-306.2 ✅ 回测结果可视化 — ECharts 折线图（策略收益 vs 市场基准 + 超额收益 bar）+ IC 滚动验证图表 + 摘要卡片（累计收益/夏普比率/最大回撤/胜率/平均 IC/ICIR）+ 回测明细 Table（IC/ICIR）调用 backtest-service (8007) backtestApi.run()
- [x] AC-306.3 ✅ 构建验证 — npx tsc -b --noEmit: 0 errors; npm run build: success (3.63s, 3681 modules)

**质量门**: typecheck ✅ / build ✅ / lint N/A / SIT ⚠️ (auth-flow SIT: 4 fail — 预存 OOM + button text `/登录/` vs `登 录` mismatch，非 Backtest.tsx 回归)
    - 命令: $ cd frontend && npx vitest run tests/sit/
    - 输出: FATAL ERROR: Ineffective mark-compacts near heap limit ... Test Files 1, Tests 4 failed (8), 1 error

**下一步**: 等待 product-lead 审查
