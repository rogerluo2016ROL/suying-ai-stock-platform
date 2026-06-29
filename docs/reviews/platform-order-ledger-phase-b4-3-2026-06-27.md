# Phase B4-3 Order Ledger 查询强化记录

日期：2026-06-27

## 范围

- 新增 `trade_orders` 平台化订单 ledger 迁移。
- 新增 trade-service Order store。
- 下单成功后 best-effort 写入订单快照。
- 增强 `GET /api/v1/trade/orders`，按 tenant/account 查询订单 ledger。
- 前端 `TradeOrder/OrdersResponse` 补充平台字段和 lineage 字段。

## 关键文件

- `backend/alembic/versions/017_add_trade_orders.py`
- `services/trade-service/app/order_store.py`
- `services/trade-service/app/routes.py`
- `services/trade-service/tests/test_order_store.py`
- `services/trade-service/tests/test_risk_verdict_routes.py`
- `frontend/src/api/types.ts`

## 行为

- `order_id` 唯一，重复写入使用 `ON CONFLICT DO NOTHING`。
- 订单列表按当前 `tenant_id/account_id` 过滤。
- ledger 查询失败时回退旧 paper engine 订单列表，避免未迁移环境中断。
- 下单写入失败不阻断主交易流程。

## 验证

```bash
pytest services/trade-service/tests/test_order_store.py services/trade-service/tests/test_risk_verdict_routes.py -q
```

已执行并通过。

## 下一步

- B4-4：交易中心订单表展示来源、方案和风控入口。
- B4-5：风控闸门页面读取 RiskVerdict 历史与规则详情。
- B4-6：自动交易执行器写入同一套 DecisionContext / Order / RiskVerdict lineage。
