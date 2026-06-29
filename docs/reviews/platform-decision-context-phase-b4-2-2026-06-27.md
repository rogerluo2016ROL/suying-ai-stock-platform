# Phase B4-2 DecisionContext 持久化查询记录

日期：2026-06-27

## 范围

- 新增 `decision_contexts` 快照表迁移。
- 新增 trade-service DecisionContext store。
- 下单时如果携带 `decision_context_id`，best-effort 写入上下文快照。
- 新增 `GET /api/v1/trade/decision-contexts` 查询接口。
- 前端新增 DecisionContext 查询类型与 `tradeApi.getDecisionContexts`。

## 关键文件

- `backend/alembic/versions/016_add_decision_contexts.py`
- `services/trade-service/app/decision_context_store.py`
- `services/trade-service/app/routes.py`
- `services/trade-service/tests/test_decision_context_store.py`
- `services/trade-service/tests/test_risk_verdict_routes.py`
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/__tests__/apiClientPlatformContext.test.ts`

## 行为

- `decision_context_id` 唯一，重复写入使用 `ON CONFLICT DO NOTHING`。
- 查询接口按当前 `tenant_id/account_id` 过滤。
- 下单写入失败不阻断风控检查和订单执行。
- 前端查询复用统一 API client，平台 header 自动携带。

## 验证

```bash
pytest services/trade-service/tests/test_decision_context_store.py services/trade-service/tests/test_risk_verdict_routes.py -q
cd frontend && npx vitest run src/__tests__/apiClientPlatformContext.test.ts
```

已执行并通过。

## 下一步

- B4-3：订单列表返回平台字段与 lineage 字段。
- B4-4：交易中心订单表展示来源与 RiskVerdict 详情入口。
- B4-5：自动交易执行器写入同一套 DecisionContext / RiskVerdict lineage。
