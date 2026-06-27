# 复盘：为何竞价数据没有定时采集

> 日期：2026-06-25
> 触发：跑毕师傅选股时发现库里竞价数据只到 06-24，今早 06-25 需手动 `sync_stk_auction_o` 才有
> 范围：data-service 定时采集链路（不止竞价，所有 L0-L4 定时任务同此机制）

## 一、结论先行（TL;DR）

**根因：data-service 进程当前没有运行。** 调度器（scheduler）不是独立的 cron/systemd，而是**寄生在 data-service FastAPI 进程内的一个 asyncio 循环**——进程一旦不在，所有定时采集（竞价、实时分钟线、盘后全量、凌晨回补…共 40+ 任务）全部静默停摆，且**无任何告警**。

竞价数据 5 月以来几乎天天有（5400+ 只/日），说明采集机制本身正确、Tushare 权限正常；断点只在 data-service 进程没起来的日子（如今天 06-25、以及 06-18）。这不是代码 bug，是**运维/部署缺陷**：关键常驻进程没有被守护。

## 二、证据链

### 1. 调度器架构：进程内 asyncio，非独立守护

- `services/data-service/app/main.py:35-43` — FastAPI `lifespan` 里 `start_scheduler()`，进程关闭时 `stop_scheduler()`。
- `scheduler.py:_scheduler_loop()` — `while _running: ... await asyncio.sleep(30)`，每 30 秒扫一遍 cron 表。
- **含义：调度生命周期 == data-service 进程生命周期。进程死 = 调度死。**

### 2. 竞价任务配置本身正确

`scheduler.py:1197` —
```python
{"id": "auction", "name": "[L0]竞价快照", "cron": "25 9 * * 1-5", "fn": collect_auction_snapshot}
```
工作日 9:25 触发，逻辑：Tushare `stk_auction`（实时）→ mootdx fallback。配置无误。

### 3. data-service 进程不在运行（核心证据）

- data-service 默认端口 **8010**（`main.py:6`）。
- `lsof -iTCP -sTCP:LISTEN` 当前监听：8002/8003/8004/8005/8006/8007/8008/8009/8080 + screener 的 8001/18001 —— **没有 8010，没有任何 data-service 进程**。
- `ps aux | grep data` 无结果。
- CLAUDE.md 部署表已注明：data-service 属于"**3 个需手动启动**"的服务（backend/data-service/training-service），**不在 docker compose 编排内**。
- docker 容器此刻为空（postgres/redis 是本次会话临时 `docker start` 的）。

### 4. 历史断点与"进程不常驻"吻合

| 日期 | daily_kline | 竞价 | 判定 |
|---|---|---|---|
| 2026-06-25(今) | 0(未收盘) | 0→手动补 | **进程没起，9:25 任务未执行** |
| 2026-06-24 | 5461 | 5461 | OK（那天进程在跑） |
| 2026-06-18 | 4974 | **0** | **交易日但竞价缺失（采集漏）** |
| 2026-06-19 | 0 | 0 | 非交易日，正常 |
| 5月全月 | — | 5400+/日 | OK |

竞价数据**大部分日子都有** → 机制正确；**零星断点** → data-service 进程时起时停，靠人工手动拉起，没有守护进程保证常驻。

### 5. 无日志、无告警

- 未找到 data-service / scheduler 的持久化日志文件。
- 调度失败后无任何通知机制——**数据缺失只能等下游（选股、回测）报错才被动发现**，本次正是如此。

## 三、根因分层

| 层级 | 问题 | 严重度 |
|---|---|---|
| **直接原因** | data-service 进程当前没运行，9:25 竞价任务未触发 | P0 |
| **架构缺陷** | 调度器寄生在业务进程内，无独立守护；进程退出=全链路采集停 | P0 |
| **部署缺陷** | data-service 不在 docker compose，靠人工 `uvicorn` 手动起，机器重启/进程崩溃后不自愈 | P0 |
| **可观测性缺陷** | 无心跳、无任务执行日志落盘、无失败告警；数据缺口靠下游报错被动发现 | P1 |
| **数据自愈缺陷** | 有 `[L4]data_integrity 0 4 * * *` 回补任务，但它同样寄生在死掉的进程里→回补也没跑→缺口不自愈 | P1 |

> 致命闭环：进程死 → 采集停 → 回补任务（本该补缺口）也死 → 缺口永久留存，直到人工介入。

## 四、整改建议（按优先级）

### P0 — 让 data-service 常驻自愈
1. **进程守护**：把 data-service 纳入 docker compose（`restart: unless-stopped`），或用 systemd / supervisor / pm2 守护，机器重启与进程崩溃后自动拉起。
2. **启动校验**：开机/部署脚本加一步 `curl localhost:8010/health` 确认调度器活着。

### P0 — 调度与业务解耦（架构）
3. 中长期把 scheduler 从 FastAPI lifespan 抽出为**独立进程/容器**（或迁移到系统 cron + 独立 worker），业务 API 重启不影响采集。

### P1 — 可观测性
4. **任务执行落盘**：每个 job 的 last_run/last_status 写入 PG 表或日志文件（`_job_status` 已在内存，持久化即可）。
5. **缺口告警**：每日 9:30 / 15:40 检查当日关键表（竞价、daily_kline、rt_k）行数，缺失即告警（邮件/webhook/钉钉）。

### P1 — 数据自愈兜底
6. `[L4]data_integrity` 回补任务改为**独立 cron 触发**（不依赖 data-service 常驻），或在选股/回测入口加"数据新鲜度门控"：缺当日数据时先尝试即时补拉再跑（本次手动 `sync_stk_auction_o` 即是临时版）。

## 五、本次临时处置（已完成）
- 手动执行 `sync_stk_auction_o("20260625")` → 06-25 竞价 5431 只入库。
- 已用 06-25 竞价重跑毕师傅选股（结果见对话）。
- ⚠️ 06-18 竞价缺口仍在，如需可手动补：`sync_stk_auction_o("20260618")`（Tushare `stk_auction_o` EOD 接口仍可拉历史）。

## 六、待人工决策
- 是否立即拉起 data-service 常驻（今天后续 13:00 盘中同步 / 15:30 盘后全量都依赖它）？
- 整改走哪条路：纳入 docker compose（快） vs 调度独立化（彻底）？
