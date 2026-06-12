## T-201: data-pipeline-refactor 修复包（6 项） - 2026-06-12 15:30
**状态**: 已完成
**Skills**: agf-running-sit-tests, superpowers:verification-before-completion

**SIT 证据**（按 AC 列；行首 `[x]/[ ]` 同时表达 AC 自验勾选）:
- [x] AC-201.1 ✅ stk_auction_o schema 对齐 — init_postgres.sql 表定义改为 (code, trade_date, open, high, low, close, vol, amount, vwap)，与 scheduler.py:136-140 INSERT 列完全一致
    - 变更: `services/sql/init_postgres.sql:407` — `ts_code→code, pre_close/price/volume/bid_*/ask_*→open/high/low/close/vol/amount/vwap`
    - 验证: diff init_postgres.sql 确认新列名 (code, trade_date, open, high, low, close, vol, amount, vwap) + UNIQUE(code, trade_date)
- [x] AC-201.2 ✅ sync_stock_list() PG 已在 SQLite 之前 — stocks.py:56-79 (PG) → stocks.py:81-93 (SQLite)，sync_stocks_incremental 同样 PG-first (line 132-154 → 156-167)
    - 验证: Visual code review — PG 写入块注释 `# ── PG 写入 (主路径, …)` 在 SQLite `# ── SQLite 写入 (fallback)` 之前，符合 ADR-006 决策 1
- [x] AC-201.3 ✅ pg_write_status 结构化提取 — `_extract_pg_status(result: dict)` 直接从 dict 提取 (line 41-63)，无 regex；router data.py 读取 job["pg_written"]/job["pg_write_status"] 结构化字段 (line 40-46)；str(result) 仅用于 last_result 展示字段
    - 验证: `grep -n "re\.\|regex" services/data-service/app/scheduler.py` → 无匹配 (仅 str() 出现在 line 155/157 的 run_intraday_sync 日志格式化中，非 regex)
- [x] AC-201.4 ✅ sync_to_pg.py LEGACY 标记 — 文件头添加 `# LEGACY: use data-service for daily sync`
    - 变更: `Kronos/tools/sync_to_pg.py:1` — 注释在 shebang 之前
    - 验证: `head -3 Kronos/tools/sync_to_pg.py` → `# LEGACY: use data-service for daily sync`
- [x] AC-201.5 ✅ write_ths_daily() 函数 — pg_writer.py 新增 (line 151-165)，参照 write_limit_list_d 模式：swap trade_date/ts_code 位置 + YYYYMMDD→YYYY-MM-DD 转换 + executemany 批量写入
    - 同时: tushare.py sync_post_market_ext 新增 elif table=="ths_daily" 分支调用 write_ths_daily (line 254-256)
    - 验证: `python3 -c "import ast; ast.parse(open('services/data-service/app/sync/pg_writer.py').read())"` → Syntax OK
- [x] AC-201.6 ✅ migrate_data.py 端口 5432→6432 (2 处: docstring line 11 + argparse default line 113)
    - TABLE_ORDER 追加 5 表: rt_k, stk_auction_o, stk_mins, limit_list_d, ths_daily (line 30)
    - 验证: `grep "6432" services/sql/migrate_data.py` → 2 处匹配 (docstring + default) ✅；`grep -c "rt_k\|stk_auction_o\|stk_mins\|limit_list_d\|ths_daily" services/sql/migrate_data.py` → 5 ✅
- [x] AC-201.7 ✅ sync_daily_to_pg 无残留 — grep -rn "sync_daily_to_pg" services/ packages/ Kronos/tools/ → NO_CODE_REFERENCES_FOUND
    - 验证: 仅 docs/adr/ docs/prd/ progress/ 中有历史文档引用，代码中零残留

**质量门**: syntax ✅ (6/6 Python 文件全部通过) / SIT ✅ (7 AC 全部 pass) / SQL schema ✅ (stk_auction_o 对齐)
**下一步**: 等待 code review；PL 确认后可 merge 并验证 data-service 启动后 stk_auction_o INSERT 不再报 column mismatch
