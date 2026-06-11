# Tech Lead — 数据管道架构审查

- 日期：2026-06-12
- 触发：product-lead 派单"数据管道架构审查"
- 产物：`docs/adr/006-data-pipeline.md`

## 审查发现

### 基线缺口

数据管道没有 ADR 覆盖。现有 5 个 ADR（001-005）分别覆盖认证/交易/策略/训练/诊断，数据管道作为全平台数据基础，缺乏架构基线记录。已通过 ADR-006 补齐。

### 架构风险（按严重度排序）

1. **subprocess 桥反模式（高）** — `pg_writer.sync_daily_to_pg()` 通过 subprocess 调用 `sync_to_pg.py`，SQLite 写成功但 subprocess 失败时 PG 数据静默丢失。ADR-006 决策 3：消除 subprocess 桥，改为 sync 函数内直写 PG。

2. **写入路径不一致（高）** — rt_min 直写 PG，但 post_market 仅写 SQLite。ADR-006 决策 1+2：统一为 PG-first + SQLite fallback。

3. **stocks 表无数据（高）** — PG 侧 stocks 表长期为空，物化视图 JOIN 无结果。ADR-006 决策 4：Tushare stock_basic API 周级全量 + 日级增量同步。

4. **无速率控制（中）** — `tushare.py` 声明的 `_RATE_LIMIT=400` 从未执行。ADR-006 决策 2：统一 rate limiter。

5. **错误处理 best-effort（中）** — 所有异常 DEBUG log，无重试/告警/数据质量门禁。ADR-006 决策 6：3 次指数退避重试 + 分级日志 + 数据量门禁。

6. **代码双轨（低）** — `data-service/app/sync/` 和 `Kronos/tools/sync_all.py` 两套 Tushare sync 实现。ADR-006 决策：data-service 为增量同步主路径，sync_all.py 保留为 CLI 全量工具。

### 已验证的技术基线

以下方面当前实现合理，不需变更：
- **调度框架**：asyncio 内建调度器（scheduler.py），适合当前 < 10 个定时任务，无外部依赖
- **物化视图数量**：3 个物化视图覆盖核心查询场景，不过度膨胀
- **pandas + tushare SDK**：选型合理，Tushare 返回 DataFrame 与 pandas 生态无缝集成
- **PostgreSQL 15-alpine**：与 ADR-001/003/004 一致，EOL 2027-11 仍有充足生命周期

## Skills 使用

- `agf-writing-adr`：生成 `docs/adr/006-data-pipeline.md` 的模板与结构指引

## SIT 证据

不适用 — tech-lead 不写代码，做架构审查与 ADR 撰写。

## 质量门

- [x] ADR-006 包含至少 1 个备选方案 + 否决理由
- [x] ADR-006 包含版本与查证表
- [x] ADR-006 包含影响评估（代码/团队/成本/运维）
- [x] CLAUDE.md Tech Stack 已同步更新
- [x] 技术记忆已更新（.claude/agent-memory/tech-lead/）

## 下一步

- product-lead: review ADR-006，确认 stocks 同步频率
- backend-dev: 按 ADR-006「后续工作」清单落地实现
- tech-lead: ADR accepted 后追踪 CLAUDE.md 同步更新
