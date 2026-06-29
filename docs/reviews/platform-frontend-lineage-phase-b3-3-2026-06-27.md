# Platform Frontend Lineage Phase B3-3 Review

> Date: 2026-06-27  
> Scope: Candidate -> Plan -> Order frontend lineage, order panel prefill, RiskVerdict display  
> Verdict: Pass for B3-3.

## Changes Reviewed

- Strategy plan detail now exposes `candidate_id` beside each pick when available.
- Each Plan pick has a “下单” action that builds a trade URL with:
  - `code`
  - `price`
  - `plan_id`
  - `candidate_id`
  - `decision_context_id`
- Trade page reads those query fields and pre-fills the order form.
- Trade order form has a compact “决策链路” section:
  - `DecisionContext`
  - `Candidate`
  - `Plan`
- `useLiveTrade.placeOrder` and `liveTradeApi.placeOrder` now send the complete order payload:
  - `trade_mode`
  - `decision_context_id`
  - `candidate_id`
  - `plan_id`
- After a successful order, Trade page displays latest `RiskVerdict` with verdict id, result, account, rules count and lineage ids.

## Verification

Commands run:

```bash
cd frontend && npx vitest run src/__tests__/TradeFormValidation.test.tsx src/__tests__/useLiveTrade.test.tsx src/__tests__/useLiveTradeRisk.test.tsx src/__tests__/StrategyLineage.test.ts
cd frontend && npx tsc -b --noEmit
cd frontend && npm run build
```

Results:

- Frontend focused tests: 13 passed.
- TypeScript check passed.
- Frontend build passed.

Known warnings:

- Existing jsdom warning from Ant Design: `Window's getComputedStyle() method: with pseudo-elements`.
- Existing Vite chunk-size warning for `antd` and `echarts`.

## Residual Risk

- `decision_context_id` is generated on the frontend until backend `DecisionContext` persistence lands.
- Plan detail is still a modal, not a full execution workspace.
- RiskVerdict display currently shows the latest order only; historical verdict lookup should come from RiskVerdict persistence in B4.

## Next Phase

B4 should persist `DecisionContext`, `Candidate`, `Order` platform fields and `RiskVerdict`, then expose them through account-scoped APIs and risk/audit views.
