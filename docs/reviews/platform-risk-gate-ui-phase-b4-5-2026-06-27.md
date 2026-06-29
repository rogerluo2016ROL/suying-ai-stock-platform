# Phase B4-5 风控闸门页面记录

日期：2026-06-27

## 范围

- 新增 `frontend/src/pages/RiskVerdicts.tsx`。
- 新增 `/trade/risk-verdicts` 路由。
- 交易中心顶部新增“风控闸门”入口。
- 风控闸门读取 `tradeApi.getRiskVerdicts`，展示判定历史与规则级明细。

## 关键文件

- `frontend/src/pages/RiskVerdicts.tsx`
- `frontend/src/pages/Trade.tsx`
- `frontend/src/App.tsx`
- `frontend/src/__tests__/RiskVerdicts.test.tsx`
- `frontend/src/__tests__/TradeFormValidation.test.tsx`

## 行为

- 支持按判定结果、交易模式、股票代码筛选。
- 表格展示 `RiskVerdict`、来源链路、账户和规则明细。
- 规则明细常显前三条，展开行可查看完整规则列表。
- 页面入口不新增一级菜单，保持交易中心下钻结构。

## 验证

```bash
cd frontend && npx vitest run src/__tests__/TradeFormValidation.test.tsx src/__tests__/RiskVerdicts.test.tsx
```

已执行并通过。

## 下一步

- B4-6：订单行、RiskVerdict、DecisionContext 互相跳转。
- B4-7：自动交易执行器写入同一套 lineage。
- B4-8：回测复盘读取 Order / RiskVerdict / DecisionContext。
