# Tech Lead — 架构合规审查

- 角色：tech-lead
- 审查日期：2026-06-12
- 触发：product-lead 派单"阅读全部 6 个 ADR，对照基线检查代码合规"
- 审查范围：ADR-001 ~ ADR-006 全量 + CLAUDE.md 一致性 + 实际代码

## 审查发现

### P0 — 必须立即修复

#### P0-1: stk_auction_o 表 schema 与 INSERT 代码不匹配

- **文件**：`services/data-service/app/scheduler.py:136-140` vs `services/sql/init_postgres.sql:407`
- **问题**：`collect_auction_snapshot()` INSERT 列 `(code, trade_date, open, high, low, close, vol, amount, vwap)` 与表定义 `(ts_code, trade_date, pre_close, price, volume, amount, bid_volume, ask_volume, bid_amount, ask_amount)` 完全不同。列名和数量均不匹配，运行时必抛异常。
- **影响**：9:25 集合竞价快照写入失败，所有交易日影响
- **修复**：`init_postgres.sql:407` 和 `scheduler.py:136` 择一改动，统一 schema。建议以 scheduler.py INSERT 为基准，将表改为 `(code, trade_date, open, high, low, close, volume, amount, vwap)`

#### P0-2: 全部微服务无 RBAC 权限控制

- **ADR-001 要求**：8 个现有微服务各加 `Depends(require_role(...))` 调用
- **实际**：screener-service、signal-service、trade-service、strategy-service 全部搜索零 `require_role` / `Depends(role)`。所有微服务端点公开无保护
- **影响**：与 ADR-001 风险描述一致——「任何知晓服务地址的人均可访问所有 API」

#### P0-3: 共享 RBAC 包 `packages/kronos-auth/` 缺失

- **ADR-001 决策**：共享 Python 包 `kronos-auth` 含 `require_role(role)` 依赖注入
- **实际**：`packages/` 下仅 kronos-core、kronos-data、kronos-factors，无 kronos-auth
- **影响**：P0-2 修复缺少基础组件，每个服务需自行实现角色校验

### P1 — 应尽快修复

#### P1-1: 认证内嵌 backend 而非独立 auth-service（架构漂移）

- **ADR-001 决策**：独立 auth-service（FastAPI，端口 8010）
- **实际**：认证在 `backend/`（端口 9001），`services/auth-service/` 不存在
- **评估**：JWT/Argon2id/httpOnly Cookie 实现正确符合 ADR-001。将 auth 嵌入 backend 是务实的简化，但 ADR-001 未记录此决策变更
- **建议**：更新 ADR-001 记录「auth 合并入 backend，不独立部署」决策

#### P1-2: sync_to_pg.py 缺 LEGACY 标记

- **ADR-006 决策 3**：文件头加 `# LEGACY: use data-service for daily sync`
- **实际**：未添加

#### P1-3: ths_daily 表无 PG 直写函数

- **ADR-006 决策 2**：P1 直写范围含 ths_daily
- **实际**：`init_postgres.sql:447` 有 ths_daily 表，`pg_writer.py` 无对应 `write_ths_daily()`

#### P1-4: materialized_views.sql 独立文件不存在

- **ADR-006 后续工作**：修改 `materialized_views.sql` 新增 `mv_daily_composite_ranking`
- **实际**：文件不存在，物化视图 DDL 内联在 `init_postgres.sql`

### CLAUDE.md 文档漂移

| # | 位置 (行) | 写什么 | 实际 |
|---|-----------|--------|------|
| D1 | ADR 基线表 | `002-broker-trading.md` | `002-live-trading-broker.md` |
| D2 | ADR 基线表 | `004-model-training.md` | `004-model-training-pipeline.md` |
| D3 | 目录表 L99 | `5 个 ADR` | 实际 6 个 |
| D4 | 目录表 L98 | `11 个 FastAPI 微服务` | 正确（alert/api-gateway/backtest/data/diagnosis/prediction/screener/signal/strategy/trade/training = 11），但 docker-compose 仅覆盖 8 个 |

## ADR-006 合规矩阵

| 决策 | 状态 |
|------|------|
| 决策 1: PG-first 写入 | ✅ pg_writer.py `_pg_write()` |
| 决策 2: P0+P1 表直写 | ⚠️ 缺 ths_daily（P1-3） |
| 决策 3: 消除 subprocess 桥 | ✅ | scheduler 注释确认、pg_sync 步骤已移除 |
| 决策 3: sync_to_pg.py LEGACY 标记 | ❌ 未实现（P1-2） |
| 决策 4: stocks 同步（周全量+日增量） | ✅ stocks.py + cron (周六 02:00 + 工作日 08:00) |
| 决策 5: 物化视图（含 mv_daily_composite_ranking） | ✅ pg_writer.py 刷新 4 视图，init_postgres.sql 含 DDL |
| 决策 6: 错误处理（3 次指数退避+数据量门禁） | ✅ `_pg_write()` 重试 + `_check_data_volume()` |

## ADR-001 合规矩阵

| 决策 | 状态 |
|------|------|
| PyJWT 2.x + HS256 | ✅ `backend/app/config.py` |
| Argon2id (3/65536/2) | ✅ `backend/app/config.py` |
| httpOnly Refresh Cookie | ✅ `backend/app/routers/auth.py` |
| 独立 auth-service (8010) | ❌ 内嵌 backend (9001)（P1-1） |
| 共享包 kronos-auth | ❌ 缺失（P0-3） |
| RBAC Depends 覆盖 8 服务 | ❌ 全未实现（P0-2） |

## Skills 使用

- 未使用 — 审查任务不需要 skill 辅助

## SIT 证据

不适用 — tech-lead 不写代码。

## 质量门

- [x] 全部 6 个 ADR 已阅读
- [x] CLAUDE.md 与代码交叉验证完成
- [x] 发现 P0-1 运行时 bug（stk_auction_o schema 冲突）
- [x] 发现 P0-2/P0-3 RBAC 安全缺口
- [x] 4 项 CLAUDE.md 漂移已标记

## 下一步

1. P0-1 需 backend-dev 立即修复 schema 冲突
2. P0-2/P0-3 需 product-lead 排入下个 sprint——当前所有微服务无访问控制
3. P1-2 一行注释即可修复
4. CLAUDE.md D1-D4 漂移由 tech-lead 修复（下一个 commit）
