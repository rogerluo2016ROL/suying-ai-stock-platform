# QA Engineer Progress — 测试覆盖债务审计

- **Date**: 2026-06-12
- **Tester**: qa-engineer (deepseek-v4-pro)
- **Status**: 审计完成 — 产出未覆盖清单

---

## 一、现有 E2E/UAT 覆盖汇总

| Feature | E2E 通过 | UAT 通过 | 关联服务 | Verdict |
|---------|:---:|:---:|------|-----|
| auth-rbac | 12/12 | 8/8 (4 P0 pass^2) | backend :9001, frontend :3000 | Promote → Approve |
| auto-trading | 10/10 | 7/7 | strategy-service :8003 | Promote → Approve |
| diagnosis | 6/6 | 8/8 | diagnosis-service :8009 | Promote → Approve |
| live-trading | 10/10 | 8/8 | trade-service :8006 | Promote → Approve |
| model-training | 5/7 + 1 cond | 8/8 | training-service :8008 | Promote → Approve |

**已覆盖服务**：backend (auth)、strategy-service、diagnosis-service、trade-service、training-service（5/12）

---

## 二、缺少 E2E/UAT 的服务

| 服务 | 端口 | 功能 | 风险等级 | 说明 |
|------|:---:|------|:---:|------|
| **screener-service** | 8001 | 6 模式选股 + 多因子排序 | **HIGH** | 全角色使用的核心功能（选股/排序），无任何 E2E/UAT。PRD auth-rbac 权限矩阵中选股是所有 4 角色共用入口 |
| **prediction-service** | 8002 | Kronos 30 日 K 线预测 | **HIGH** | 全角色使用，AI 核心能力。无独立 E2E/UAT（diagnosis 测试中仅作为下游依赖被间接覆盖，未测预测服务本身的端点） |
| **signal-service** | 8004 | 50 维综合交易信号 | **MEDIUM** | 被 strategy-service 依赖（Mock），无独立 E2E/UAT。自动交易 E2E 使用 Mock 代替真实信号服务 |
| **backtest-service** | 8007 | 历史回测 + IC/ICIR 分析 | **MEDIUM** | 3 角色使用（admin/internal/external），无 E2E/UAT。选股→回测链路未端到端验证 |
| **alert-service** | 8005 | 预警规则 + 实时提醒 | **MEDIUM** | 全角色使用，无 E2E/UAT |
| **data-service** | N/A | 数据管道（采集/同步/物化视图） | **CRITICAL** | **当前 active feature** — PRD `data-pipeline-refactor-2026-06-12.md` 刚 Approved，8 AC 全未测试 |
| **api-gateway** | 8080 | 统一 API 网关 | LOW | 纯代理层，通过各服务测试间接覆盖 |

---

## 三、data-pipeline-refactor AC 未覆盖清单（当前 active feature）

> PRD: `docs/prd/data-pipeline-refactor-2026-06-12.md`，ADR: `docs/adr/006-data-pipeline.md`（6 项决策已落盘）
> 8 AC，0/8 通过。E2E 和 UAT 均尚未执行。

| AC | Priority | 描述 | 状态 |
|----|:---:|------|:---:|
| AC-1 | P0 | `POST /api/v1/data/sync/post_market?date=` 返回后 30s 内 PG daily_kline 有数据 | 未测试 |
| AC-2 | P0 | PG 写入失败不影响 SQLite，scheduler status 含失败计数 | 未测试 |
| AC-3 | P0 | 移除 pg_sync 任务，status jobs 不含 pg_sync | 未测试 |
| AC-4 | P1 | `POST /api/v1/data/sync/stocks` 后 PG stocks >= 4000 行 | 未测试 |
| AC-5 | P1 | 物化视图刷新失败时 status 含失败 view 名 + 原因 | 未测试 |
| AC-6 | P1 | 盘中 rt_min 执行后 PG stk_mins 60s 内可查最新 trade_time | 未测试 |
| AC-7 | P2 | `sync_daily_to_pg()` 函数从 pg_writer.py 移除（subprocess 链路废弃） | 未测试 |
| AC-8 | P2 | status 每个 job 含 pg_write_status 字段（ok/partial/fail/skipped） | 未测试 |

**ADR-006 决策覆盖缺口**：

| 决策 | 验证项 | QA 覆盖 |
|------|------|:---:|
| 决策 1: PG-first 写入顺序 | PG 先写成功 → SQLite 后写（失败仅 WARN） | 未覆盖 |
| 决策 2: 全 P0+P1 表 upsert 直写 | 8 张表幂等写入验证 | 未覆盖 |
| 决策 3: 消除 subprocess 桥 | pg_sync job 移除 + sync_to_pg.py LEGACY 标记 | AC-3/AC-7 部分覆盖 |
| 决策 4: stocks 同步 | stock_basic → PG + SQLite 双写 | AC-4 部分覆盖 |
| 决策 5: 物化视图 | 3 现存 + 1 新增 mv_daily_composite_ranking | 未覆盖 |
| 决策 6: 错误处理 | 3 次退避重试 + 数据量门禁 + PG 连接失败降级 | 未覆盖 |

---

## 四、整体测试债务评估

### 4.1 按服务统计

| 类别 | 数量 |
|------|:---:|
| 总微服务数 | 12 |
| 有完整 E2E+UAT | 5 |
| 部分覆盖（仅策略框架） | 0 |
| 完全无覆盖 | 7 |
| E2E/UAT 覆盖率 | **42%** (5/12) |

### 4.2 按 PRD 统计

| PRD | E2E | UAT | 状态 |
|-----|:---:|:---:|------|
| auth-rbac | Y | Y | 完成 |
| auto-trading | Y | Y | 完成 |
| live-trading | Y | Y | 完成 |
| model-training | Y | Y | 完成 |
| diagnosis | Y | Y | 完成 |
| **data-pipeline-refactor** | **N** | **N** | **当前 active，待 E2E+UAT** |

### 4.3 风险排序

1. **CRITICAL — data-pipeline-refactor**: 当前 active feature，8 AC 未测。数据管道是所有下游服务的基石，失败影响面全平台。
2. **HIGH — screener-service + prediction-service**: 选股和预测是用户核心功能，无独立 E2E/UAT 意味着回归靠手工。
3. **MEDIUM — signal-service + backtest-service + alert-service**: 被其他 feature 间接引用但未独立验证。

---

## 五、推荐的测试执行顺序

1. **data-pipeline-refactor** E2E + UAT（当前 active feature，最高优先）
2. **screener-service** E2E + UAT（全角色高频使用）
3. **prediction-service** E2E + UAT（AI 核心能力，独立端点未验证）
4. **signal-service** E2E + UAT（被 auto-trading 依赖，Mock 无法替代真实集成）
5. **backtest-service** E2E + UAT（回测→选股→交易闭环关键节点）
6. **alert-service** E2E + UAT（实时通知链路未验证）

---

## 六、下一阶段

- data-pipeline-refactor 需 code-review (含 SIT Audit) 通过后进入 E2E
- E2E 通过后进入 UAT
- 其他未覆盖服务建议按风险排序逐步补齐，至少完成 HIGH 级别服务的 E2E

---

## 质量门

- [x] 所有 QA 报告已审核
- [x] 服务覆盖率统计完整
- [x] PRD AC 逐条对账
- [x] ADR 决策覆盖评估
- [x] 风险排序清晰
- [x] 未覆盖清单可操作

---

## ADR-013 E2E + UAT — 2026-06-22

- **Stage**: E2E + UAT 合段（含 deploy-engineer 冒烟尾部）
- **Branch / commit**: feature/suying-ai-stock-platform @ 0ba2a3e
- **Environment**: UAT 隔离栈 `uat-adr013` (PG 16432 / API-GW 18080 / 10 services 18001-18009/19001/18080)
- **Report**: `docs/reviews/adr-013-e2e-uat-report-2026-06-22.md`

### AC 总览 (10 项)

| AC | Priority | Verdict | 备注 |
|----|----------|---------|------|
| AC-1 health × 10 | P0 | ❌ Fail | backend 19001 restart-loop (exit 3) |
| AC-2 data-service 宿主进程 | P1 | ✅ Pass | UAT 端口 18010 启动成功 |
| AC-3 cb_sync + change_pct 100% 非 NULL | P0 | ✅ Pass^2 (2/2) | 3015 行，change_pct fill rate 100.00% |
| AC-4 登录链路 | P0 | ⚠️ Blocked | backend 不可达 |
| AC-5 端到端 happy path | P0 | ⚠️ Blocked | 依赖 AC-4 + 缺基础数据 |
| AC-6 ths_daily fallback 消除 | P1 | ✅ Pass | signal/screener 日志无 fallback 警告 |
| AC-7 抽 3-5 股 | P1 | ⚠️ Blocked | 依赖 AC-4 |
| AC-8 validator warnings=0 | P0 | ✅ Pass^2 (2/2) | checked 47 tables, 0 warn / 0 err |
| AC-9 合并报告输出 | P1 | ✅ Pass | 本报告 |
| AC-10 verdict 判定 | P0 | ❌ Block | 决策树推出 |

**Summary**: 4 pass / 0 fail / 6 blocked (其中 1 P0 Fail, 3 P0 Blocked)

### 关键发现

1. **ADR-013 主线核心验证 PASS**：`ths_daily.change_pct` 列 100% 非 NULL（3015/3015 rows），sync_ths_daily 写入成功，validator 0 warnings，下游 fallback 警告消除。**ADR-013 schema 对齐目标本身已达成**。

2. **P0 阻塞 (DEF-1 Critical)**：UAT backend Docker 镜像缺少 Alembic 008-011 migrations。`uat-adr013-deploy.sh` retag 了旧的 `suying-uat-backend:latest` 镜像而非从当前代码 rebuild，导致 backend 容器启动时执行 `alembic upgrade head` 报 `Can't locate revision '011'`，exit 3 后被 compose `restart: unless-stopped` 持续拉起。

3. **DEF-2 High**：UAT PG 基础数据未填充（stocks=0, daily_kline=0），导致下游业务接口（选股/诊断/信号）即使有 auth 也不可用。

### Hand-off

立即升 PL，**不自行 hack 修复**（遵守 task §7 + iron rule #7）。


---

## ADR-013 E2E + UAT — Re-run Round 2 — 2026-06-22

**Trigger**: deploy-engineer + dev 修复 P0 阻塞后（rebuild backend + alembic 001-007 + stamp 011 + restart）PL 重派 Task #6。

### Round 2 AC 总览

| AC | P | Round 1 | Round 2 | pass^2 |
|----|---|---------|---------|--------|
| AC-1 health × 10 | P0 | ❌ Fail | ✅ Pass | 2/2 |
| AC-3 change_pct | P0 | ✅ | ✅ | 2/2 |
| AC-4 登录 | P0 | ⚠️ Blocked | ✅ Pass | 2/2 |
| AC-5 happy path | P0 | ⚠️ Blocked | ⚠️ Conditional | — |
| AC-8 validator | P0 | ✅ | ✅ | 2/2 |
| AC-10 verdict | P0 | ❌ | ⚠️ Conditional | — |

**Round 2 final**: 8 Pass / 0 Fail / 2 Conditional, P0 pass^2 = 4/4

### Verdict

⚠️ **Conditional Promote** — ADR-013 schema 对齐主线完整达成，可 merge。

### 新发现 (round 2 only)

- **DEF-3 Medium**: api-gateway:18080 路由到 `localhost:9001` 错（容器内寻址），auth 走 gateway 失败；绕过直连 backend 19001 OK
- **DEF-4 Medium**: docker-compose.yml 业务微服务缺 `JWT_SECRET_KEY` env，跨服务 JWT 验签用 default secret 失败

两者均 **pre-existing 配置 bug, 与 ADR-013 无关**，建议单开 follow-up issue。

