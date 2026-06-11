---
name: data-pipeline-no-subprocess-bridge
description: ADR-006 决策：消除 pg_sync subprocess 桥，改为 sync 函数内直写 PG
metadata:
  type: project
---

`pg_writer.sync_daily_to_pg()` 通过 `subprocess.run()` 调用 `Kronos/tools/sync_to_pg.py` 是一种架构反模式。已否决，不再使用。

**Why:** subprocess 有独立进程、独立连接池、独立错误上下文。SQLite 写成功但 subprocess 失败时 PG 数据静默丢失。硬编码相对路径、300s 硬超时、输出截断 200 字符，排查困难。

**How to apply:** 
- 调度器中移除 `pg_sync` (15:36) 步骤
- `sync_to_pg.py` 保留为独立全量迁移工具（加 `# LEGACY` 标记），不删除
- 所有 post_market sync 函数在写 SQLite 后直接调用 `pg_writer.write_table()` 写 PG
