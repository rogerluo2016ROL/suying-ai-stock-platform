---
name: data-pipeline-stocks-sync
description: ADR-006 决策：stocks 基础表通过 Tushare stock_basic API 周级全量 + 日级增量同步
metadata:
  type: project
---

stocks 表（`init_postgres.sql` 已定义）当前无数据填充脚本，PG 侧 stocks 表为空，导致物化视图 JOIN 无结果。

**同步策略：**
- 数据来源：Tushare `stock_basic` API（全量 A 股列表）
- 频率：每周六 02:00 全量刷新 + 每日盘前 `list_date = today` 增量检测
- 写入目标：PG + SQLite 双写
- 字段映射：`ts_code → code`（去后缀）, `industry`, `list_date`, `is_hs`, `market`

**Why:** 新股上市频率低（周均 2-5 只），周级全量足够；日级增量仅 1 次 API 调用不会触发限频。

**How to apply:** 新建 `services/data-service/app/sync/stocks.py`，实现 `sync_stocks(pro, db)` 函数。注册到 scheduler 周六 02:00 cron，同步暴露 `POST /api/v1/data/sync/stocks` API 端点。
