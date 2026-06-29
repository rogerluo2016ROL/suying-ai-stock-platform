# 平台化主链路 B10/B11 API Gateway 与前端 Client 收口

日期：2026-06-27

## 范围

本阶段收口前后端联通底座：

```text
frontend api/client.ts
  -> /api/v1/*
  -> api-gateway
  -> 各业务微服务
```

## 变更

后端：

```text
services/api-gateway/app/main.py
services/api-gateway/tests/test_gateway_routes.py
```

前端：

```text
frontend/src/api/client.ts
frontend/src/__tests__/apiClientPlatformContext.test.ts
```

## 验收点

```text
网关核心前缀映射到正确服务端口
/api/v1/<service>/health 重写到服务 /api/v1/health
前端 gateway health 走 root /health，不再误拼成 /api/v1/health
前端 screener/prediction/strategy/signal/alert/trade/backtest/diagnosis/chain API 都走 /api/v1
平台上下文头继续自动注入
```

## 测试

```text
services/api-gateway/tests/test_gateway_routes.py
frontend/src/__tests__/apiClientPlatformContext.test.ts
```

已验证：

```text
api-gateway route tests: 4 passed
frontend api client tests: 6 passed
frontend TypeScript: passed
frontend build: passed
git diff --check: passed
```

## 边界

本阶段不启动全部微服务做 E2E，只完成网关路由和前端 client 契约收口。下一阶段进入页面级真实接口联调：智能看板、选股、预测、信号、诊断、产业链、交易、回测、模型训练。
