# Live Trading — 实盘交易模块 spec

> 基于 PRD §3.11 AC-11.1~11.9 | 日期: 2026-06-10

## Scope
在现有模拟交易(P0-7: Paper Trading + T+1/费率)基础上实现实盘交易。
核心差异：MockBroker → XtquantBroker + 风控网关 + 审计日志 + 熔断。

## AC 映射
| AC | 需求 | 实现方案 |
|----|------|---------|
| AC-11.1 | 界面一致 | 同一 Trade.tsx，mode=live/paper 切换 |
| AC-11.2 | xtquant券商 | XtquantBroker 实现 BrokerInterface ABC |
| AC-11.3 | 风控检查 | RiskGateway: 资金/持仓/涨跌停/仓位上限/单笔上限 |
| AC-11.4 | 大额确认 | >50万触发二次确认弹窗，阈值可配 |
| AC-11.7 | 审计日志 | PostgreSQL audit_logs 表，INSERT-only，无DELETE权限 |
| AC-11.8 | 熔断 | 日亏损超阈值→自动暂停交易，次日复位 |
| AC-11.9 | 模拟↔实盘统一 | 共享 UI 组件，仅 broker 实现不同 |

## Tech Architecture
```
Trade Page (React)
  → POST /api/v1/trade/order { mode: "live"|"paper" }
    → RiskGateway.pre_check()
      → 资金校验 ✓ → 持仓校验 ✓ → 涨跌停 ✓ → 仓位上限 ✓ → 单笔上限 ✓
      → 大额确认? (>50万 → 需要前端二次确认)
    → BrokerInterface.place_order()
      → MockBroker (模拟) | XtquantBroker (实盘)
    → AuditLog.record() (append-only)
    → CircuitBreaker.check_daily_loss()
```

## DB Schema (新增)
```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    action VARCHAR(50) NOT NULL,  -- PLACE_ORDER, CANCEL_ORDER
    mode VARCHAR(10) NOT NULL,      -- live, paper
    details JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()  -- immutable
);
-- 无 UPDATE/DELETE 权限给应用账户
```

## Open Questions

| ID | 问题 | Owner | 状态 | 决议/方向 |
|----|------|-------|------|----------|
| OQ-1 | xtquant 需本地运行客户端，Docker 部署方案？ | tech-lead | Open | 方向：trade-service 容器挂载 xtquant SDK volume + host network mode；备选：独立 xtquant-gateway 宿主机进程通过 localhost socket 通信。待 tech-lead 出 ADR-002 补充决议 |
| OQ-2 | 券商断线后持仓如何处理？ | tech-lead | Open | 方向：CircuitBreaker 触发 HALF_OPEN 后保留本地持仓缓存（`positions_snapshot`），恢复连接后调用 `sync_positions()` 与券商对账。`get_positions()` 返回缓存 + `stale: true` 标记。待 tech-lead 在 ADR-002 或独立 ADR 落盘 |
| OQ-3 | 实盘是否需要独立交易密码（非登录密码）？ | product-lead | Resolved | **不需要**。理由：(a) 已有多因子认证（JWT + httpOnly Cookie + Argon2id），加交易密码增加摩擦但不增加实质安全（XSS/CSRF 已防）；(b) 大额确认弹窗（AC-11.4）已提供操作级二次确认。若合规要求升级可在 Phase B 加 TOTP |
