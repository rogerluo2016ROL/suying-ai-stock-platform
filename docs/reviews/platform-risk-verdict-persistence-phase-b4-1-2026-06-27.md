# Phase B4-1 RiskVerdict 持久化查询记录

日期：2026-06-27

## 范围

- 新增 `risk_verdicts` append-only 表迁移。
- 新增 trade-service RiskVerdict 持久化 store。
- 下单成功与风控拒绝均 best-effort 写入 RiskVerdict。
- 新增 `GET /api/v1/trade/risk-verdicts` 查询接口。
- 前端新增 RiskVerdict 查询类型与 `tradeApi.getRiskVerdicts`。

## 关键文件

- `backend/alembic/versions/015_add_risk_verdicts.py`
- `services/trade-service/app/risk_verdict_store.py`
- `services/trade-service/app/routes.py`
- `services/trade-service/tests/test_risk_verdict_store.py`
- `services/trade-service/tests/test_risk_verdict_routes.py`
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/__tests__/apiClientPlatformContext.test.ts`

## 行为

- `RiskVerdict.result` 支持 `pass/warn/reject/manual_review`。
- 查询接口按当前 `tenant_id/account_id` 过滤，避免跨账户读取私有风控记录。
- 写入失败不阻断下单主链路，失败会 rollback 并记录日志。
- 前端查询复用统一 API client，平台 header 自动携带。

## 验证

```bash
pytest services/trade-service/tests -q
cd frontend && npx vitest run src/__tests__/apiClientPlatformContext.test.ts
```

已执行并通过。

## 下一步

- B4-2：DecisionContext 事件/快照模型。
- B4-3：订单列表返回平台字段和 lineage 字段。
- B4-4：风控闸门页面展示 RiskVerdict 历史和规则详情。
