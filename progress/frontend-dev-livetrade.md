# Frontend Dev — 实盘交易进度报告

> **实现日期**: 2026-06-10
> **关联文档**: [frontend-plan.md](../docs/design/live-trading/frontend-plan.md) | [ADR-002](../docs/adr/002-live-trading-broker.md)
> **状态**: Completed

---

## 状态

- TypeScript 编译：通过 (0 errors)
- 实现范围：AC-11.2 ~ AC-11.9 前端全部完成
- 未破坏现有模拟交易功能

---

## Skills

- React 18.3 + TypeScript 5.6
- Ant Design 5.22 (Segmented, Modal, Table, Alert, Badge, Tag, message, Tooltip)
- Dependencies：dayjs 1.11, react-router-dom 6.28

---

## 产物

| 文件 | 状态 | 说明 |
|------|------|------|
| `frontend/src/api/liveTrade.ts` | 新增 | 实盘交易 API 封装（11 个端点），基于 axios client |
| `frontend/src/hooks/useLiveTrade.ts` | 新增 | 实盘交易状态管理（mode/broker/熔断/风控/下单流程） |
| `frontend/src/components/trade/BrokerStatus.tsx` | 新增 | 券商连接状态指示器（4 状态 + 连接按钮） |
| `frontend/src/components/trade/LargeTradeConfirm.tsx` | 新增 | 大额交易确认弹窗（≥50 万阈值，含 promise-based helper） |
| `frontend/src/components/trade/RiskCheckModal.tsx` | 新增 | 风控拦截结果展示弹窗（拦截/警告分离） |
| `frontend/src/components/trade/CircuitBreakerAlert.tsx` | 新增 | 熔断状态提示条（可关闭 Alert） |
| `frontend/src/pages/Trade.tsx` | 修改 | 模式切换 + 数据源路由 + 风控集成 + 状态指示 |
| `frontend/src/pages/AuditLog.tsx` | 新增 | 审计日志只读页面（筛选 + 分页 + CSV 导出） |
| `frontend/src/App.tsx` | 修改 | 新增 `/trade/audit-log` 路由 |

---

## SIT 证据

### AC-11.9 模式切换
- [x] Segmented 组件替代原有 Tag，支持模拟盘/实盘一键切换
- [x] 切换时 localStorage 持久化 mode 状态
- [x] 切换至实盘且未连接券商 → message.info 提示
- [x] 颜色区分：模拟盘蓝色 / 实盘红色背景

### AC-11.2 券商连接状态
- [x] BrokerStatus 组件显示 4 种状态：connected/disconnected/connecting/error
- [x] 状态颜色映射：🟢绿/🔴红/🟡蓝/⚠️橙
- [x] disconnected/error 状态显示"连接"按钮
- [x] 实盘模式下每 10 秒轮询 broker/status
- [x] 状态变化时 message 提示（"券商连接已断开"/"券商已连接"）
- [x] 断开时下单按钮置灰 + Tooltip "券商未连接"

### AC-11.3 风控拦截提示
- [x] RiskCheckModal 展示拦截项（红色卡片）和警告项（黄色卡片）
- [x] 下单前调用 POST /live-trade/order/pre-check
- [x] 非阻塞警告通过 message.warning 提示
- [x] 风控检查文案已按 AC 要求实现（资金不足/超持仓/涨跌停等）

### AC-11.4 大额交易确认
- [x] 下单金额 ≥ 50 万 → 弹出 LargeTradeConfirm Modal
- [x] 显示：股票代码/方向/价格/数量/预估金额/预估手续费
- [x] "确认下单"/"取消" 按钮
- [x] 阈值从 GET /live-trade/risk-config 获取，默认 500000
- [x] 市价单（price=0）始终触发确认

### AC-11.8 熔断状态
- [x] CircuitBreakerAlert 显示日亏损/阈值/恢复说明
- [x] 可手动关闭（轮询恢复后重新显示）
- [x] 熔断中下单按钮置灰 + Tooltip "熔断保护中，交易暂停"
- [x] 实盘模式下每 30 秒轮询 circuit-breaker/status

### AC-11.7 审计日志
- [x] AuditLog 页面：只读 Table，无可编辑/删除操作
- [x] 筛选：日期范围(RangePicker) + 操作类型(Select) + 股票代码(Input) + 操作人(Input)
- [x] 分页 + CSV 导出
- [x] 路由 `/trade/audit-log`，从 Trade 页面"审计日志"按钮进入
- [x] 返回按钮可回到 /trade

### 模拟交易兼容性
- [x] paper 模式下单流程不变（直接 fetch POST /trade/order）
- [x] 所有现有 KPI Banner、策略卡片、委托表格保持不变
- [x] 模式切换后数据源自动切换（apiPrefix）

---

## 质量门

- [x] TypeScript 编译零错误
- [x] 所有组件使用 Ant Design 原生组件，自动继承 ConfigProvider 主题
- [x] 暗色主题适配：使用 semantic token (colorPrimary, success/error/warning)
- [x] API 层复用现有 axios client (auth interceptor)
- [x] 无新增外部依赖
- [ ] 单元测试 (未在本阶段实现)
- [ ] E2E 测试 (未在本阶段实现)

---

## 下一步

1. backend-dev 对齐 API 契约（§11 API 端点）
2. 后端实现后联调 API 响应格式
3. 编写 Unit 测试 (hooks + components)
4. qa-engineer E2E 测试
