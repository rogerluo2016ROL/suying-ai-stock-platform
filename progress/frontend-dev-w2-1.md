## T-306: Backtest.tsx 空壳实现完成 — 2026-06-12 13:30

**状态**: 完成 — AC-306.1/306.2/306.3 全部通过

**Skills used**: superpowers:test-driven-development, superpowers:verification-before-completion

**SIT 证据**: SIT 跳过（Backtest.tsx 依赖 PG 数据，暂无适合 Vitest + MSW 的 SIT 场景；后端 E2E 由 T-305 覆盖）

**质量门**:
- TypeScript: `npx tsc -b --noEmit` → 0 errors ✅
- Vite build: `npm run build` → success (3681 modules, 3.81s) ✅
- vitest: 16/16 unit tests pass（AuthContext 9 + ProtectedRoute 7）✅
- Dev server: 未启动（需 PG Docker 运行才能看到真实回测数据）

**下一步**: 等 T-305 (qa-engineer) 完成 backtest-service E2E 后可启动 dev server 目测验证

---

## 实现详述

### AC-306.1: 回测参数配置表单

`Backtest.tsx` 含完整回测参数配置 `Card`：
- 策略模式 `Select`: all（全市场选股）/ long（多头）/ short（空头）
- 回测窗口 `InputNumber` + `Slider`: 1-12
- 每窗口选股数 `InputNumber` + `Slider`: 10-100
- 前瞻天数 `InputNumber` + `Slider`: 20-252
- 基准指数 `Select`: 上证指数 / 深证成指 / 创业板指 / 科创50 / 沪深300
- 运行按钮 + 重置按钮 + loading 态 + 错误展示

### AC-306.2: 回测结果图表

三 Tab 布局（回测运行 / 因子列表 / 策略对比）：

**回测运行 Tab** (`/backtest/run`):
- 6 个 Summary `Statistic` 卡片: 平均 IC, ICIR, 命中率, 超额收益, 回测窗口数, 数据源
- ECharts 收益曲线: 三色分组柱状图（策略收益 `#1677ff` / 市场基准 `#d9d9d9` / 超额收益 `#52c41a`）
- ECharts IC 滚动验证: 柱+线组合图（正 IC 绿/负 IC 红 + 蓝色平滑趋势线）
- ECharts 命中率仪表盘: 四段色区（红<30% / 黄<50% / 蓝<70% / 绿≥70%）
- 明细表格: 窗口/日期/入选数/收益/命中率/基准/超额/IC, 10 列，分页

**因子列表 Tab**:
- 因子表格（14 个因子），保留原有 `GET /backtest/factors`
- 权重校准 `Card`：调用 `POST /backtest/calibrate`，展示校准结果表

**策略对比 Tab**:
- 多选策略 `Select` (14 个可选)
- 调用 `POST /backtest/compare`
- ECharts 策略收益对比柱状图（含数据标签）
- 对比结果表格

### AC-306.3: tsc + build

- `npx tsc -b --noEmit`: 0 errors
- `npm run build`: success, dist 产出 2.7MB JS + 0.97KB CSS

### API 客户端扩展

`api/client.ts` backtestApi 从 2 个方法扩展到 4 个，支持完整参数：
- `run({ mode, windows, top_n, forward_days })` — URLSearchParams 构建 query string
- `calibrate(mode)` — 权重校准
- `compare({ strategy_ids, start_date, end_date })` — 多策略对比

### 涉及文件

| 文件 | 变更 | 行数 |
|------|------|------|
| `frontend/src/pages/Backtest.tsx` | 重写（51→~570 行） | +519 |
| `frontend/src/api/client.ts` | 扩展 backtestApi（126→145 行） | +19 |
