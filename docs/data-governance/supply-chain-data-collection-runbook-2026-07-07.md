# 产业链三层数据采集中心运行手册

日期：2026-07-07

## 1. 目标

本手册用于运行产业链三层数据采集中心，持续更新产业链证据、研发/商用阶段、三高评分、市场预期分、景气分和预期差分。

核心原则：

- 不伪造数据。
- 强证据、半强证据、弱信号分层处理。
- 弱信号只进入待复核，不直接改变阶段和选股理由。
- 授权源未配置时只标记为 `license_required` 或 `not_configured`。

## 2. 常用命令

数据库连接示例：

```bash
export DATABASE_URL="postgresql://kronos:kronos@localhost:6432/kronos"
```

查看来源目录和授权状态：

```bash
python3 tools/supply_chain_data_collection_center.py quality-report --pg-url "$DATABASE_URL"
```

查看调度计划：

```bash
python3 tools/supply_chain_data_collection_center.py schedule-plan
```

运行每日核心批次：

```bash
python3 tools/supply_chain_data_collection_center.py run-scheduled-batch --pg-url "$DATABASE_URL" --batch daily_core --limit 100
```

刷新预期差和三高评分：

```bash
python3 tools/supply_chain_data_collection_center.py refresh-expectation-scores --pg-url "$DATABASE_URL" --limit 3000
```

运行 UAT：

```bash
python3 tools/run_supply_chain_collection_uat.py --pg-url "$DATABASE_URL" --source-limit 10
```

注册产业链预期差选股模型，并写入最新交易日 TopN 快照：

```bash
python3 tools/register_supply_chain_expectation_gap_model.py --pg-url "$DATABASE_URL" --top-n 30 --min-gap 8
```

回填最近五年历史 as-of 评分：

```bash
python3 tools/backfill_supply_chain_expectation_gap_history.py --pg-url "$DATABASE_URL" --years 5 --commit-every 50 --replace
```

运行最近五年严格回测：

```bash
python3 tools/backtest_supply_chain_expectation_gap_model.py --pg-url "$DATABASE_URL" --years 5 --top-n 30 --min-gap 8 --hold-days 1,3,5,10 --update-db
```

## 3. 批次说明

| 批次 | 频率 | 内容 |
|---|---|---|
| `daily_core` | 交易日盘后 | 来源目录、研报/盈利预测、财经新闻、政府项目、产业指数代理、评分刷新、质量报告 |
| `weekly_official_and_ip` | 每周 | 官网/IR、巨潮 PDF、专利事件、招投标事件、证据同步、评分刷新 |
| `manual_weak_signal` | 人工触发 | 弱信号 JSONL 导入和质量报告 |

## 4. 弱信号导入

弱信号必须用 JSONL，每行一条：

```json
{"title":"来源标题","content_text":"原文片段或摘要","company_code":"002708.SZ","company_name":"光洋股份","url":"https://example.com/source","publish_time":"2026-07-07"}
```

导入命令：

```bash
python3 tools/supply_chain_data_collection_center.py import-weak-signals --pg-url "$DATABASE_URL" --file weak_signals.jsonl --source market_community_signal
```

限制：

- `source` 必须是 weak 来源。
- 必须包含 `title`、`content_text`、`company_code`。
- 同步到 L8 事件时固定为 `pending_review`。
- 不允许自动升级研发阶段或商用阶段。

## 5. 当前已验证数据

截至 2026-07-07：

| 指标 | 数量 |
|---|---:|
| 产业链 | 18 |
| 候选公司 | 1195 |
| 业务映射 | 2255 |
| raw 文档 | 33579 |
| 结构化 facts | 33425 |
| 2026-07-06 预期差评分 | 2255 |
| 2026-07-06 三高评分 | 2255 |

第二层来源当前真实落库：

| 来源 | raw docs |
|---|---:|
| `broker_expectation_local` | 200 |
| `financial_news_authoritative` | 119 |
| `government_project_notice` | 115 |
| `industry_index_proxy_local` | 425 条指标 |

## 6. 模型注册与快照

当前已注册模型：

| 字段 | 值 |
|---|---|
| model_key | `supply_chain_expectation_gap_v1` |
| display_name | `产业链预期差选股模型 V1.0` |
| version_tag | `v1.0` |
| stage | `staging` |
| category | `产业链` |
| snapshot_time_slot | `close` |

写入位置：

| 表 | 作用 |
|---|---|
| `screening_models` | 选股模型入口，前端/ChatBI 可按 `model_key` 调用 |
| `model_registry` | 模型注册信息、参数、指标和脚本路径 |
| `model_versions` | 当前版本记录，`v1.0` 为 current |
| `screening_snapshots` | 每个交易日 TopN 选股快照 |

当前口径：

- 数据日：`2026-07-06`
- 观察池候选阈值：`expectation_gap_score >= 8`
- 强信号候选阈值：`expectation_gap_score >= 15`
- 当前观察池候选：69
- 已写入快照：Top30
- 最近五年严格回测窗口：`2021-07-07` 至 `2026-07-06`
- 当前已落库评分日期：1210 个交易日
- 当前已落库预期差评分：1,483,997 条
- 五年窗口正向预期差评分：177 条
- 实际触发选股日期：5 个，分别为 `2026-06-30`、`2026-07-01`、`2026-07-02`、`2026-07-03`、`2026-07-06`
- 观察池整体 T+1：92 笔，胜率 41.30%，平均收益 -0.1627%，复利收益 -0.7349%
- 强信号 T+1：60 笔，胜率 43.33%，平均收益 0.0772%，复利收益 0.1336%
- 观察信号 T+1：32 笔，胜率 37.50%，平均收益 -0.6124%，复利收益 -0.8674%
- 观察信号 T+3：32 笔，胜率 37.50%，平均收益 -1.1492%，复利收益 -1.9183%
- T+5/T+10 暂无可验证样本，因为数据库最新行情停在 `2026-07-06`，最新信号还没有足够后续交易日。
- 最新快照结构：Top30 中强信号 29 个、观察信号 1 个，平均动量分分别约 74.78、92.75。
- 当前为 `staging`，原因是还需要回填 T+1/T+3/T+5 收益、胜率和回撤后，才能升级为 production。
- 模型是“候选排序”，不是自动买入清单。

## 7. 已知缺口

| 缺口 | 当前处理 |
|---|---|
| Wind/Choice/iFinD/财联社等授权源 | 仅保留来源目录，不伪造数据 |
| CNIPA 全量专利接口 | 暂未接入，只保存已采官方原文中的专利事件 |
| 真实商品价格/库存/供需 | 暂用东方财富板块指数作为景气代理 |
| 官网/IR | 当前有 partial_success，需要继续优化站点适配和失败原因记录 |
| 脑机接口景气代理 | 本地指数库暂无匹配，保留缺口 |

## 8. 质量判断

质量报告重点看：

- `source_health.last_status`
- `source_health.last_started_at`
- `source_health.duplicate_rate`
- `source_health.failed_total`
- `recent_issue_jobs`

若出现 `failed` 或 `partial_success`：

1. 先看 `recent_issue_jobs`。
2. 判断是否是授权、网络、站点结构或解析问题。
3. 不要用模型补假数据。
4. 修复后重跑对应 source 或批次。
