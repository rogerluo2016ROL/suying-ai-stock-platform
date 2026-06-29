# Phase B4-4 交易中心链路可视化记录

日期：2026-06-27

## 范围

- 交易中心委托记录表新增“来源”列。
- 下单成功后本地订单行保留 `decision_context_id/candidate_id/plan_id`。
- 修复下单成功后刷新账户时把本地订单列表重置为空的问题。
- Trade 页面测试覆盖订单表来源列和多处 lineage 展示。

## 关键文件

- `frontend/src/pages/Trade.tsx`
- `frontend/src/__tests__/TradeFormValidation.test.tsx`
- `docs/design/New design/01 PRD 文档/0.5 平台化详细方案设计.md`

## 行为

- 右侧最新风控卡显示 RiskVerdict。
- 左侧委托记录表显示 Plan / Candidate / DecisionContext。
- 下单成功后只刷新账户和持仓，不再立即重新拉空订单列表。

## 验证

```bash
cd frontend && npx vitest run src/__tests__/TradeFormValidation.test.tsx
```

已执行并通过。

## 下一步

- B4-5：风控闸门页面读取 RiskVerdict 历史。
- B4-6：订单详情展开 DecisionContext 与 RiskVerdict。
