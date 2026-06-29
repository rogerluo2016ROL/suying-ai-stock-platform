# 平台化主链路 B7 API Smoke 验证

日期：2026-06-27

## 范围

验证 P0 主链路在本地服务层面的模拟盘闭环：

```text
POST /api/v1/trade/order
  -> risk verdict
  -> decision context
  -> order ledger
```

## 环境

```text
PostgreSQL: docker-postgres-1, localhost:6432, healthy
Redis: docker-redis-1, localhost:7379, healthy
Alembic: 017 (head)
trade-service: 127.0.0.1:18006
trade_mode: paper
```

## 命令

```bash
cd services/trade-service
../../backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18006
```

```bash
python3 tools/b6_platform_chain_smoke.py \
  --base-url http://127.0.0.1:18006 \
  --token "$TOKEN"
```

`TOKEN` 为本地开发 JWT，用于通过 trade-service 的 RBAC 校验；不读取 `.env`，不使用生产密钥。

## 结果

```json
{
  "status": "ok",
  "order_id": "ORD0001",
  "decision_context_id": "CTX-b6-smoke-300750-1782566266",
  "candidate_id": "CAND-b6-smoke-300750",
  "plan_id": "PLAN-b6-smoke"
}
```

## 结论

通过。当前 P0 主链路已具备本地模拟盘 API 联调能力：

```text
Order / RiskVerdict / DecisionContext 三对象共享同一组 lineage
前端可通过 order_id / decision_context_id / candidate_id / plan_id 做下钻
策略自动执行器已使用 JSON body 对接 trade-service
```

## 风险边界

本次未触碰：

```text
BrokerInterface
XtquantBroker / QMT
live circuit breaker
真实券商账户配置
```

进入 MockBroker/QMT sandbox 前，需要单独设计券商账户配置、连接状态、模拟/实盘隔离与审计口径。
