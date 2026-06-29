# 平台化主链路 B8 QMT Sandbox 账户配置

日期：2026-06-27

## 范围

本阶段补齐券商账户配置的最小可用链路：

```text
前端交易中心账户配置
  -> POST /api/v1/trade/broker/connect JSON body
  -> mock_qmt sandbox 连接状态
  -> broker/status 可见 environment / adapter / trade_mode
```

## 变更

后端：

```text
services/trade-service/app/schemas.py
services/trade-service/app/routes.py
services/trade-service/tests/test_risk_verdict_routes.py
```

前端：

```text
frontend/src/api/types.ts
frontend/src/api/liveTrade.ts
frontend/src/hooks/useLiveTrade.ts
frontend/src/components/trade/BrokerStatus.tsx
frontend/src/pages/Trade.tsx
frontend/src/__tests__/useLiveTrade.test.tsx
```

## 验收点

```text
mock_qmt 只允许 sandbox
sandbox 连接返回 trade_mode=paper
前端 connectBroker(config) 发送 JSON 配置
交易中心默认显示 QMT Sandbox
Xtquant/QMT 实盘选项禁用，避免误触真实连接
```

## API Smoke

本地当前代码启动：

```bash
cd services/trade-service
../../backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18006
```

调用：

```text
POST /api/v1/trade/broker/connect
GET  /api/v1/trade/broker/status
```

结果：

```json
{
  "connect": {
    "broker_name": "mock_qmt",
    "account_id": "sandbox-qmt-001",
    "status": "connected",
    "environment": "sandbox",
    "adapter": "mock",
    "trade_mode": "paper"
  },
  "status": {
    "connected": true,
    "broker_name": "mock_qmt",
    "account_id": "sandbox-qmt-001",
    "environment": "sandbox",
    "adapter": "mock",
    "trade_mode": "paper",
    "status": "connected"
  }
}
```

## 风险边界

未修改：

```text
XtquantBroker
BrokerInterface
真实券商下单
live circuit breaker
生产密钥/账户托管
```

后续打开实盘前，必须补齐单独评审和 UAT：账户隔离、实盘二次确认、风控闸门、熔断演练、审计追踪、撤单和异常恢复。
