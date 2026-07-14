# 定时模型运行与三群推送实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前 Mac 的 data-service 中注册四个交易日模型任务，每次计算一次并把含市场强弱、板块共振、Top 10 和报告链接的结果发送到三个飞书群。

**Architecture:** data-service 只负责 cron 触发，新的 `scheduled_research.py` 负责交易日、幂等和统一流水线调用。统一流水线增加午后时点、市场宽度和多群发送能力；竞价任务复用已有 Tushare 主源与东方财富备用源逻辑。

**Tech Stack:** Python 3.14、pytest、PostgreSQL、项目内 asyncio cron、lark-cli

## Global Constraints

- 只在 `trade_cal.is_open=1` 的 A 股交易日执行。
- 09:25 先查 Tushare，当天数据为空、过期或关键字段不可用时使用东方财富备用源。
- 14:00 和 14:30 必须按各自截止时点独立运行。
- 每次模型只计算一次，向三个群分别发送并保存三个消息 ID。
- 群消息包含市场强弱、板块共振、Top 10 和完整报告链接。
- 数据不足时明确说明，不编造行情、字段或清单。
- 不保存或输出应用密钥、访问令牌和登录缓存。
- Mac 或 data-service 未运行时不补发过时任务。
- 不提交 `outputs/` 中的运行证据和测试报告。

---

### Task 1: 午后时点和真实市场宽度

**Files:**
- Create: `services/screener-service/app/market_strength.py`
- Create: `services/screener-service/tests/test_market_strength.py`
- Modify: `services/screener-service/app/domains/screening/service.py:4146-4178`
- Modify: `tools/run_research_pipeline.py`
- Modify: `tools/tests/test_run_research_manifest.py`

**Interfaces:**
- Produces: `compute_market_strength(trade_date: str, cutoff_time: str, rows: list[dict[str, Any]]) -> dict[str, Any]`
- Produces: `load_market_strength(trade_date: str, cutoff_time: str, pg_url: str) -> dict[str, Any]`
- Extends: `_run_afternoon_mode(mode, top_n, trade_date, time_slot="14:30")`
- Extends: `_run_registered_mode(mode, top_n, trade_date, time_slot=None)`

- [ ] **Step 1: 写市场宽度失败测试**

```python
def test_compute_market_strength_uses_latest_common_snapshot():
    rows = [
        {"code": "000001", "snapshot_time": "2026-07-14 14:00:00", "close": 10.5, "pre_close": 10.0},
        {"code": "000002", "snapshot_time": "2026-07-14 14:00:00", "close": 9.0, "pre_close": 10.0},
        {"code": "000003", "snapshot_time": "2026-07-14 14:00:00", "close": 10.1, "pre_close": 10.0},
    ]
    result = compute_market_strength("2026-07-14", "14:00", rows)
    assert result["snapshot_time"] == "2026-07-14 14:00:00"
    assert result["advancers"] == 2
    assert result["decliners"] == 1
    assert result["above_5pct"] == 1
    assert result["below_minus_5pct"] == 1
    assert result["median_pct"] == 1.0
```

- [ ] **Step 2: 运行测试并确认模块不存在**

Run: `../../.venv/bin/pytest -q services/screener-service/tests/test_market_strength.py`

Expected: FAIL，错误包含 `app.market_strength` 不存在。

- [ ] **Step 3: 实现市场宽度计算和 PG 查询**

PG 查询只取 `trade_time <= <trade-date> <cutoff_time>` 的每只股票最后一条分钟记录，优先使用当天 `stk_auction_o.close` 作为昨收，缺失时取 `daily_kline` 中早于当天的最近收盘。返回字段固定为：

```python
{
    "status": "ok",
    "scope": "intraday_market_breadth",
    "snapshot_time": "2026-07-14 14:00:00",
    "coverage": 3,
    "advancers": 2,
    "decliners": 1,
    "flat": 0,
    "median_pct": 1.0,
    "above_5pct": 1,
    "below_minus_5pct": 1,
}
```

查询失败或有效股票少于 100 只时返回 `status: insufficient` 和实际覆盖数，不输出强弱结论。

- [ ] **Step 4: 写 14:00 时点失败测试**

```python
def test_registered_afternoon_mode_receives_requested_time_slot(monkeypatch):
    seen = {}
    monkeypatch.setattr(pipeline, "_run_afternoon_with_time_slot", lambda mode, top_n, trade_date, time_slot: seen.setdefault("slot", time_slot) or {"picks": []})
    pipeline._run_registered_mode("leader_afternoon", 20, "2026-07-14", time_slot="14:00")
    assert seen["slot"] == "14:00"
```

- [ ] **Step 5: 运行测试并确认当前代码固定使用 14:30**

Run: `../../.venv/bin/pytest -q tools/tests/test_run_research_manifest.py -k time_slot`

Expected: FAIL，错误指向 `_run_registered_mode` 不接受 `time_slot`。

- [ ] **Step 6: 接入 `--time-slot` 和市场宽度**

解析器增加 `--time-slot`。午后模式把它传给 `AfternoonLeaderEngine.run(..., time_slot=time_slot)`；统一流水线在模型结束后调用 `load_market_strength`，把结果写入 `result["market_strength"]`。`result["pipeline"]` 同时保存计划时点和实际 `snapshot_time`。

- [ ] **Step 7: 运行 Task 1 测试**

Run: `../../.venv/bin/pytest -q services/screener-service/tests/test_market_strength.py tools/tests/test_run_research_manifest.py`

Expected: 全部通过，0 failures。

---

### Task 2: 三群发送和摘要内容

**Files:**
- Modify: `services/screener-service/app/lark_bot.py:2174-2215,2958-3075,3340-3385`
- Modify: `services/screener-service/tests/test_lark_bot.py`
- Modify: `tools/run_research_pipeline.py`
- Modify: `tools/tests/test_run_research_manifest.py`
- Modify: `configs/model_pipeline.json`

**Interfaces:**
- Produces: `resolve_chat_targets(args, config) -> list[dict[str, str]]`
- Produces: `deliver_feishu_messages(..., targets: list[dict[str, str]]) -> dict[str, Any]`
- Extends: `_format_group_reply(result, doc)`，输出市场强弱、板块共振、Top 10 和文档链接

- [ ] **Step 1: 写摘要内容失败测试**

```python
def test_group_reply_contains_market_resonance_top10_and_doc():
    result = {
        "mode": "leader_afternoon",
        "trade_date": "2026-07-14",
        "market_strength": {"status": "ok", "snapshot_time": "2026-07-14 14:00:00", "advancers": 3200, "decliners": 1500, "median_pct": 1.2},
        "sector_resonance": [{"sector": "半导体", "count": 4, "score": 88}],
        "picks": [{"code": f"00000{i}", "name": f"股票{i}", "total_score": 90-i} for i in range(10)],
    }
    text = lark_bot._format_group_reply(result, {"title": "报告", "url": "https://example/doc"})
    assert "市场强弱" in text
    assert "上涨 3200" in text
    assert "板块共振" in text
    assert "半导体" in text
    assert "10. 000009 股票9" in text
    assert "https://example/doc" in text
```

- [ ] **Step 2: 运行测试并确认摘要缺少这些字段**

Run: `../../.venv/bin/pytest -q services/screener-service/tests/test_lark_bot.py -k group_reply_contains`

Expected: FAIL，摘要只包含 Top 5，且没有市场强弱或板块共振。

- [ ] **Step 3: 扩展摘要格式**

`_format_group_reply` 使用 `market_strength`；竞价债券使用 `_cb_market_diagnosis` 的竞价口径。板块部分复用 `_sector_resonance_lines` 或 `_cb_resonance_lines`。清单显示 Top 10，文档 URL 缺失时写“完整文档生成失败”。

- [ ] **Step 4: 写多群部分失败测试**

```python
def test_deliver_feishu_messages_continues_after_one_chat_fails(monkeypatch, tmp_path):
    sent = []
    def fake_one(**kwargs):
        sent.append(kwargs["chat_id"])
        if kwargs["chat_id"] == "oc_bad":
            raise RuntimeError("send failed")
        return {"push_status": "confirmed", "chat_id": kwargs["chat_id"], "message_id": "om_" + kwargs["chat_id"]}
    monkeypatch.setattr(pipeline, "deliver_feishu_message", fake_one)
    state = pipeline.deliver_feishu_messages(
        run_dir=tmp_path,
        result={"pipeline": {}},
        targets=[{"key": "a", "name": "A", "chat_id": "oc_ok"}, {"key": "b", "name": "B", "chat_id": "oc_bad"}, {"key": "c", "name": "C", "chat_id": "oc_ok2"}],
        message="test",
        sender=lambda *_: {},
    )
    assert sent == ["oc_ok", "oc_bad", "oc_ok2"]
    assert state["status"] == "partial_delivery"
    assert len(state["deliveries"]) == 3
```

- [ ] **Step 5: 运行测试并确认多群函数不存在**

Run: `../../.venv/bin/pytest -q tools/tests/test_run_research_manifest.py -k deliver_feishu_messages`

Expected: FAIL，错误包含 `deliver_feishu_messages` 不存在。

- [ ] **Step 6: 实现多群配置和发送**

`configs/model_pipeline.json` 增加 `chat_targets`。`--chat-id` 改为可重复参数，并继续接受单个旧参数。每个目标群最多重试三次，只重试未确认群；聚合状态为 `success`、`partial_delivery` 或 `failed_delivery`。逐群状态写入 `result.json` 和 `pipeline.json` 的 `feishu_deliveries`。

- [ ] **Step 7: 运行 Task 2 测试**

Run: `../../.venv/bin/pytest -q services/screener-service/tests/test_lark_bot.py tools/tests/test_run_research_manifest.py`

Expected: 全部通过，0 failures。

---

### Task 3: 定时任务编排、交易日和竞价主备源

**Files:**
- Create: `configs/scheduled_research.json`
- Create: `services/data-service/app/scheduled_research.py`
- Create: `services/data-service/tests/test_scheduled_research.py`

**Interfaces:**
- Produces: `load_scheduled_research_config(path=None) -> dict[str, Any]`
- Produces: `is_open_trading_day(trade_date: str, pg_url: str) -> bool`
- Produces: `build_pipeline_command(task: dict[str, Any], trade_date: str, chat_ids: list[str]) -> list[str]`
- Produces: `run_scheduled_research_task(task_id: str, now: datetime | None = None, executor=None) -> dict[str, Any]`
- Produces: `build_scheduled_research_jobs() -> list[dict[str, Any]]`

- [ ] **Step 1: 写配置和四任务失败测试**

```python
def test_config_registers_four_requested_tasks():
    config = scheduled.load_scheduled_research_config()
    assert [(x["id"], x["cron"], x["model"], x.get("time_slot")) for x in config["tasks"]] == [
        ("cb_auction_t0_0925", "25 9 * * 1-5", "cb_auction_t0", None),
        ("bi_trend_launch_0930", "30 9 * * 1-5", "bi_trend_launch", None),
        ("qishen_afternoon_1400", "0 14 * * 1-5", "qishen_afternoon", "14:00"),
        ("qishen_afternoon_1430", "30 14 * * 1-5", "qishen_afternoon", "14:30"),
    ]
    assert len(config["chat_targets"]) == 3
```

- [ ] **Step 2: 运行测试并确认模块不存在**

Run: `../../.venv/bin/pytest -q services/data-service/tests/test_scheduled_research.py -k config_registers`

Expected: FAIL，错误包含 `app.scheduled_research` 不存在。

- [ ] **Step 3: 创建配置读取和 job 构建**

配置精确写入四个 cron、模型 key、午后时点、三个群配置键。09:25 任务配置 `trigger_auction: true` 和 `eastmoney_fallback: true`。群 ID 从项目已核验的三个群读取，不使用应用密钥。

- [ ] **Step 4: 写交易日失败关闭测试**

```python
def test_non_trading_day_skips_without_executor(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduled, "is_open_trading_day", lambda *_: False)
    called = []
    result = scheduled.run_scheduled_research_task(
        "bi_trend_launch_0930",
        now=datetime(2026, 7, 18, 9, 30),
        executor=lambda cmd: called.append(cmd),
        state_root=tmp_path,
    )
    assert result["status"] == "skipped_non_trading_day"
    assert called == []
```

交易日查询异常的测试必须断言 `status: failed_trade_calendar`，不能按工作日猜测。

- [ ] **Step 5: 写竞价命令和午后时点失败测试**

```python
def test_auction_command_enables_tushare_then_eastmoney_fallback():
    task = {"model": "cb_auction_t0", "trigger_auction": True, "eastmoney_fallback": True}
    cmd = scheduled.build_pipeline_command(task, "2026-07-14", ["oc_a", "oc_b", "oc_c"])
    assert "--trigger-auction" in cmd
    assert "--eastmoney-fallback" in cmd
    assert cmd.count("--chat-id") == 3


def test_afternoon_command_pins_time_slot():
    cmd = scheduled.build_pipeline_command({"model": "qishen_afternoon", "time_slot": "14:00"}, "2026-07-14", ["oc_a"])
    assert cmd[cmd.index("--time-slot") + 1] == "14:00"
```

- [ ] **Step 6: 实现命令构建、幂等和状态文件**

命令包含 `--sync-doc --send-feishu` 和重复的 `--chat-id`。09:25 额外包含主备源参数。状态路径为 `outputs/scheduled_research/<date>/<task-id>.json`；`success`、`partial_delivery`、`failed_delivery` 和 `skipped_non_trading_day` 不重复执行。执行器从统一流水线最后一个 JSON 输出读取 `run_dir` 和送达状态。

- [ ] **Step 7: 运行 Task 3 测试**

Run: `../../.venv/bin/pytest -q services/data-service/tests/test_scheduled_research.py`

Expected: 全部通过，0 failures。

---

### Task 4: data-service 注册和运行状态

**Files:**
- Modify: `services/data-service/app/scheduler.py:1271-1455`
- Modify: `services/data-service/tests/test_runtime_readiness.py`

**Interfaces:**
- Consumes: `build_scheduled_research_jobs()`
- Extends: `start_scheduler()`，把四个研究任务加入 `_jobs`

- [ ] **Step 1: 写调度注册失败测试**

```python
def test_scheduler_registers_four_research_jobs(monkeypatch):
    scheduler = importlib.import_module("app.scheduler")
    monkeypatch.setattr(scheduler, "validate_pipeline_consistency", lambda: {})
    monkeypatch.setattr(scheduler, "build_scheduled_research_jobs", lambda: [
        {"id": "cb_auction_t0_0925", "name": "竞价", "cron": "25 9 * * 1-5", "fn": lambda: {}},
        {"id": "bi_trend_launch_0930", "name": "趋势", "cron": "30 9 * * 1-5", "fn": lambda: {}},
        {"id": "qishen_afternoon_1400", "name": "午后14", "cron": "0 14 * * 1-5", "fn": lambda: {}},
        {"id": "qishen_afternoon_1430", "name": "午后1430", "cron": "30 14 * * 1-5", "fn": lambda: {}},
    ])
    scheduler.start_scheduler()
    assert {j["id"] for j in scheduler._jobs}.issuperset({"cb_auction_t0_0925", "bi_trend_launch_0930", "qishen_afternoon_1400", "qishen_afternoon_1430"})
    scheduler.stop_scheduler()
```

- [ ] **Step 2: 运行测试并确认研究任务未注册**

Run: `../../.venv/bin/pytest -q services/data-service/tests/test_runtime_readiness.py -k research_jobs`

Expected: FAIL，scheduler 没有 `build_scheduled_research_jobs`。

- [ ] **Step 3: 导入并追加研究任务**

`start_scheduler()` 在现有数据采集任务列表完成后执行 `_jobs.extend(build_scheduled_research_jobs())`。研究任务返回的 `success`、`partial_delivery`、`failed_delivery` 和跳过状态写入现有 `_job_status`，不影响数据采集任务。

- [ ] **Step 4: 运行 data-service 回归测试**

Run: `PYTHONPATH=services/data-service:packages/kronos-data ../../.venv/bin/pytest -q services/data-service/tests/test_runtime_readiness.py services/data-service/tests/test_scheduled_research.py`

Expected: 全部通过，0 failures。

---

### Task 5: 预检、真实验收和提交

**Files:**
- Runtime only: `outputs/scheduled_research_uat/2026-07-14/`

- [ ] **Step 1: 运行完整相关测试**

Run: `PYTHONPATH=services/data-service:packages/kronos-data ../../.venv/bin/pytest -q services/data-service/tests/test_runtime_readiness.py services/data-service/tests/test_scheduled_research.py services/screener-service/tests/test_market_strength.py services/screener-service/tests/test_lark_bot.py tools/tests/test_run_research_manifest.py`

Expected: 全部通过，0 failures。

- [ ] **Step 2: 运行配置、语法和差异检查**

Run: `../../.venv/bin/python -m json.tool configs/model_pipeline.json >/dev/null && ../../.venv/bin/python -m json.tool configs/scheduled_research.json >/dev/null && ../../.venv/bin/python -m py_compile services/data-service/app/scheduled_research.py services/data-service/app/scheduler.py services/screener-service/app/market_strength.py tools/run_research_pipeline.py && git diff --check`

Expected: exit code 0。

- [ ] **Step 3: 执行四任务只生成 UAT**

手动触发四个任务的 dry-run 或 `--no-send-feishu` 模式，核对模型 key、计划时间、交易日、午后 `time_slot` 和三个目标群。历史日期不得伪装成当日实时模型结果。

- [ ] **Step 4: 检查并加入三个群的机器人**

以用户身份读取三个群的机器人列表。只对缺少当前应用机器人的群执行成员添加，不删除现有机器人。操作结果不打印应用密钥或令牌。

- [ ] **Step 5: 向三个群发送功能测试并反查**

消息内容固定为：

```text
定时模型三群推送功能测试
日期：2026-07-14
说明：这是调度与送达验收消息，不是选股或选债建议。
```

三个群必须返回三个不同的 `message_id`，并由群消息列表反查确认。证据只写入 `outputs/scheduled_research_uat/2026-07-14/`。

- [ ] **Step 6: 检查 data-service 当前运行方式**

确认当前 Mac 的 data-service 是宿主机进程还是 Docker 容器。宿主机进程必须能执行项目 Python 和 `lark-cli`；容器必须配置飞书开放平台身份并能访问本地 PostgreSQL。任一前提不满足时，停止启用并报告阻断项。

- [ ] **Step 7: 只提交任务文件**

暂存配置、调度器、编排模块、市场宽度、统一流水线、报告格式及对应测试。不得暂存 `outputs/`。

Commit: `feat: schedule research models to Feishu groups`

