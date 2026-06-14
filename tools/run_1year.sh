#!/bin/bash
# 1年期ML回测 — 用引擎+ML重排
cd /Users/rogerluo/程序目录/K线大模型
KRONOS_PG_URL="postgresql://kronos:kronos@localhost:6432/kronos" python3 tools/cb_1year_backtest.py
echo "Exit: $?"
