# 平台化主链路 B9 账户级 Sandbox 预填

日期：2026-06-27

## 范围

把交易中心的券商账户配置从前端常量升级为登录用户画像驱动：

```text
auth user profile
  -> broker_connect_config
  -> AuthContext.brokerConnectConfig
  -> Trade 券商账户配置预填
```

## 变更

后端：

```text
backend/app/schemas/auth.py
backend/app/routers/auth.py
backend/tests/test_auth_platform_profile.py
```

前端：

```text
frontend/src/contexts/AuthContext.tsx
frontend/src/pages/Trade.tsx
frontend/src/__tests__/AuthContext.test.tsx
frontend/src/__tests__/TradeFormValidation.test.tsx
```

## 验收点

```text
登录/刷新用户画像包含 broker_connect_config
AuthContext 支持 snake_case -> camelCase 归一化
交易中心优先使用 user.brokerConnectConfig 预填账户
没有画像字段时降级到 user.defaultTradeAccountId
仍固定为 mock_qmt/sandbox，不打开真实 QMT
```

## 测试

```text
backend/tests/test_auth_platform_profile.py
frontend/src/__tests__/AuthContext.test.tsx
frontend/src/__tests__/TradeFormValidation.test.tsx
```

已验证：

```text
backend auth profile: 3 passed
backend auth SIT: 16 passed
trade-service tests: 36 passed
frontend Auth/Trade/useLiveTrade: 23 passed
```

说明：`backend/tests/test_auth_platform_profile.py` 与 `backend/tests/sit/test_auth_integration.py` 放在同一个 pytest 进程运行时，本地 asyncpg 在 Python 3.14 环境出现 event loop 绑定冲突；SIT 单独运行通过。

## 风险边界

未做：

```text
真实券商凭证存储
BrokerInterface / XtquantBroker 改造
live circuit breaker 改造
实盘账户启用
数据库迁移
```

后续如需实盘账户托管，需要新增独立设计：凭证加密、租户隔离、账户授权、连接审计、二次确认、熔断演练和异常恢复。
