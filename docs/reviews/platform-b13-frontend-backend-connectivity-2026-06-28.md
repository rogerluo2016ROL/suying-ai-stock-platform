# Platform B13 — 前后端联通验证记录

日期：2026-06-28

## 范围

- 前端统一 API 客户端与 Vite 开发代理
- API Gateway 路由映射
- UAT 端口组前端代理验证
- 主链路只读接口：认证、候选池/看板、数据状态、方案管理、交易账户/订单、回测、个股诊断

## 修复点

1. `/api/v1/dashboard/*` 在 API Gateway 和 Vite 代理中统一指向 `screener-service`，匹配融合选股看板、竞价、run-pipeline 的实际归属。
2. Vite 开发代理增加 `/<service>/health` 显式 rewrite：
   - `auth/admin` -> `/api/health`
   - 其他服务 -> `/api/v1/health`
3. `DataUpdate` 从旧 `/data/*` 页面裸请求切换为 `signalApi`：
   - `/signal/data-status`
   - `/signal/trigger-sync`
   - `/signal/sync-schedules`
4. `diagnosis-service` UAT 运行态补齐：
   - `JWT_SECRET_KEY`
   - `DATABASE_URL=postgresql+asyncpg://kronos:kronos@postgres:5432/kronos`
5. `packages/kronos-factors/pyproject.toml` 显式声明 `kronos_factors*` 包发现范围，修复 Docker build 中 setuptools 将 `configs` 误识别为第二顶层包的问题。

## 验证结果

### 单元/构建

- `backend/.venv/bin/pytest services/api-gateway/tests/test_gateway_routes.py -q`：5 passed
- `cd frontend && npx vitest run src/__tests__/Dashboard.test.tsx src/__tests__/DataUpdate.test.tsx src/__tests__/apiClientPlatformContext.test.ts`：3 files / 10 tests passed
- `cd frontend && npx tsc -b --noEmit`：passed
- `cd frontend && npm run build`：passed
- `python3 -m pip wheel --no-deps --no-cache-dir packages/kronos-factors -w /tmp/suying-wheel-test`：passed

### UAT 前端代理 smoke

验证前端地址：`http://127.0.0.1:3001/`

UAT 代理目标：

- Auth：19001
- Screener：18001
- Prediction：18002
- Strategy：18003
- Signal：18004
- Alert：18005
- Trade：18006
- Backtest：18007
- Diagnosis：18009
- Gateway：18080

真实注册 token 下接口结果：

- `POST /api/v1/auth/register`：201
- `GET /api/v1/auth/me`：200
- `GET /api/v1/screener/modes`：200
- `GET /api/v1/dashboard/summary`：200
- `GET /api/v1/signal/data-status`：200
- `GET /api/v1/strategy/plans`：200
- `GET /api/v1/trade/account`：200
- `GET /api/v1/trade/orders`：200
- `GET /api/v1/backtest/factors`：200
- `GET /api/v1/diagnosis/history`：200

## 剩余风险

- `GET /api/v1/signal/data-status` 当前 UAT 响应耗时约 24-28 秒，功能可用但需要后续做缓存/轻量化统计。
- `GET /api/v1/dashboard/summary` 当前返回 `status=no_data`，接口可用，业务数据需要运行融合选股流水线后产生。
- Docker compose 对 `diagnosis-service` 重新 build 会拉取非常大的 Linux CUDA 依赖；本轮为避免无谓下载，使用旧镜像手动刷新运行环境。后续应单独优化 `kronos-core` 的 Docker 依赖策略或固定 CPU-only torch 源。
