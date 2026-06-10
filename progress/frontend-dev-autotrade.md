# Frontend Dev Progress: 量化自动交易 (AutoTrade)

**日期**: 2026-06-10
**关联 PRD**: AC-10.6~10.8
**状态**: 完成

---

## 产物清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/pages/Strategy.tsx` | 修改 | 新增 "生成量化策略" 按钮 |
| `frontend/src/pages/AutoTrade.tsx` | 新建 | 策略编辑器 + 执行监控页面 |
| `frontend/src/App.tsx` | 修改 | 新增 "量化交易" 菜单项和路由 |

---

## 实现详情

### 1. Strategy.tsx 扩展 (AC-10.6)
- 确认方案卡片（status=confirmed）增加 "生成量化策略" 按钮（RobotOutlined 图标）
- 点击 → `POST /api/v1/strategy/generate-from-scheme/{id}`
- 成功 → `message.success` + `navigate('/auto-trade')`
- 操作列宽度从 200px 调整为 280px

### 2. AutoTrade.tsx 新页面 (AC-10.7~10.8)

**策略列表**
- 表格列：策略名称、关联方案(Tag)、执行模式(Tag)、状态(🟢🟡🔴🔵 Tag)、累计盈亏、今日收益、下次调仓倒计时、操作
- 操作按钮：启动/暂停/恢复/终止/编辑/删除/详情
- 实时倒计时每秒刷新

**新建/编辑策略 Drawer**
- 基本信息：策略名称、执行模式(Radio: 全自动/半自动)、最大总仓位、单票最大仓位
- 买入条件 Form.List：Switch 启用 + Select 指标 + Select 运算符 + InputNumber 阈值 + InputNumber 周期
- 卖出条件 Form.List：同上结构
- 风控规则 Form.List：Switch 启用 + Select 规则类型 + InputNumber 阈值
- 指标选项：MA/EMA/MACD/RSI/KDJ/BOLL/VOL/OBV
- 运算符选项：>/</>=/<=/上穿/下穿
- 风控选项：单日最大亏损/总回撤上限/连续止损次数/最低现金比例

**策略监控 Drawer**
- 状态标签：🟢运行中 / 🟡暂停 / 🔴已终止 / 🔵已完成
- KPI 卡片：累计盈亏、今日收益、下次调仓倒计时（均带颜色）
- 当前持仓表格：代码/名称/数量/成本/现价/盈亏
- 策略日志 Timeline：按时间线展示操作日志，带颜色图标
- 暂停/恢复/终止按钮

### 3. App.tsx 侧边栏更新
- 新增 RobotOutlined 图标导入
- 菜单项：`{ key: '/auto-trade', icon: <RobotOutlined />, label: '量化交易' }`
- 角色限制：`['admin', 'internal_analyst', 'user']`
- 路由：`{ path: '/auto-trade', element: <AutoTrade /> }`

---

## 验证结果

- `npx tsc -b --noEmit`：零错误
- `npx vite build`：构建成功 (1.86s)
- 未破坏现有 Strategy 页面功能
- UI 与现有 QuantDinger 主题一致（使用 Ant Design 组件、颜色变量）

---

## API 端点约定

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/auto-trade/strategies` | 获取策略列表 |
| POST | `/api/v1/auto-trade/strategies` | 创建新策略 |
| GET | `/api/v1/auto-trade/strategies/{id}` | 获取策略详情 |
| PUT | `/api/v1/auto-trade/strategies/{id}` | 更新策略 |
| DELETE | `/api/v1/auto-trade/strategies/{id}` | 删除策略 |
| POST | `/api/v1/auto-trade/strategies/{id}/start` | 启动策略 |
| POST | `/api/v1/auto-trade/strategies/{id}/pause` | 暂停策略 |
| POST | `/api/v1/auto-trade/strategies/{id}/resume` | 恢复策略 |
| POST | `/api/v1/auto-trade/strategies/{id}/stop` | 终止策略 |
| GET | `/api/v1/auto-trade/strategies/{id}/logs` | 获取策略日志 |
| POST | `/api/v1/strategy/generate-from-scheme/{id}` | 从方案生成策略 |
