-- ═══════════════════════════════════════════════════════════════
-- 每周数据质量检查脚本 — 输出每张表的异常行数
--
-- 用法: psql -U kronos -d kronos -f services/sql/data_quality_check.sql
-- 建议: 配置 cron 每周六凌晨执行，输出重定向到日志文件
-- ═══════════════════════════════════════════════════════════════

\echo '========================================'
\echo ' 速赢AI 数据质量周检报告'
\echo ' 执行时间: '
SELECT NOW();
\echo '========================================'

-- ──────────────────────────────────────────────────────────────
-- 行情数据 (5 张表)
-- ──────────────────────────────────────────────────────────────

\echo ''
\echo '--- [行情数据] ---'

-- daily_kline: 空值检查
SELECT 'daily_kline' AS table_name,
       'change_pct IS NULL' AS check_item,
       COUNT(*) AS anomaly_count
FROM daily_kline WHERE change_pct IS NULL
UNION ALL
SELECT 'daily_kline', 'close <= 0', COUNT(*)
FROM daily_kline WHERE close <= 0 OR close IS NULL
UNION ALL
SELECT 'daily_kline', 'volume < 0', COUNT(*)
FROM daily_kline WHERE volume < 0;

-- stk_auction_o: 空值检查
SELECT 'stk_auction_o' AS table_name,
       'close IS NULL' AS check_item,
       COUNT(*) AS anomaly_count
FROM stk_auction_o WHERE close IS NULL
UNION ALL
SELECT 'stk_auction_o', 'vwap IS NULL', COUNT(*)
FROM stk_auction_o WHERE vwap IS NULL;

-- stk_mins: 重复检查
SELECT 'stk_mins' AS table_name,
       'duplicate (code,trade_time,freq)' AS check_item,
       SUM(dup_count) AS anomaly_count
FROM (
    SELECT COUNT(*) - 1 AS dup_count
    FROM stk_mins
    GROUP BY code, trade_time, freq
    HAVING COUNT(*) > 1
) dups;

-- index_daily: 空值检查
SELECT 'index_daily' AS table_name,
       'close IS NULL' AS check_item,
       COUNT(*) AS anomaly_count
FROM index_daily WHERE close IS NULL;

-- ths_daily: 空值检查
SELECT 'ths_daily' AS table_name,
       'change_pct IS NULL' AS check_item,
       COUNT(*) AS anomaly_count
FROM ths_daily WHERE change_pct IS NULL
UNION ALL
SELECT 'ths_daily', 'pct_change IS NULL', COUNT(*)
FROM ths_daily WHERE pct_change IS NULL;

-- ──────────────────────────────────────────────────────────────
-- 可转债数据 (4 张表)
-- ──────────────────────────────────────────────────────────────

\echo ''
\echo '--- [可转债数据] ---'

-- cb_daily: 约束违规
SELECT 'cb_daily' AS table_name,
       'close <= 0' AS check_item,
       COUNT(*) AS anomaly_count
FROM cb_daily WHERE close <= 0 OR close IS NULL
UNION ALL
SELECT 'cb_daily', 'amount < 0', COUNT(*)
FROM cb_daily WHERE amount < 0 OR amount IS NULL
UNION ALL
SELECT 'cb_daily', 'duplicate (ts_code,trade_date)', SUM(dup)
FROM (
    SELECT COUNT(*) - 1 AS dup
    FROM cb_daily GROUP BY ts_code, trade_date HAVING COUNT(*) > 1
) d;

-- cb_factor: RSI 越界
SELECT 'cb_factor' AS table_name,
       'rsi_6 out of [0,100]' AS check_item,
       COUNT(*) AS anomaly_count
FROM cb_factor WHERE rsi_6 IS NOT NULL AND (rsi_6 < 0 OR rsi_6 > 100)
UNION ALL
SELECT 'cb_factor', 'rsi_12 out of [0,100]', COUNT(*)
FROM cb_factor WHERE rsi_12 IS NOT NULL AND (rsi_12 < 0 OR rsi_12 > 100)
UNION ALL
SELECT 'cb_factor', 'rsi_24 out of [0,100]', COUNT(*)
FROM cb_factor WHERE rsi_24 IS NOT NULL AND (rsi_24 < 0 OR rsi_24 > 100)
UNION ALL
SELECT 'cb_factor', 'close IS NULL', COUNT(*)
FROM cb_factor WHERE close IS NULL;

-- cb_price_chg: 一致性检查
SELECT 'cb_price_chg' AS table_name,
       'new_price <= 0' AS check_item,
       COUNT(*) AS anomaly_count
FROM cb_price_chg WHERE new_price <= 0 OR new_price IS NULL
UNION ALL
SELECT 'cb_price_chg', 'ts_code NOT IN cb_basic', COUNT(*)
FROM cb_price_chg p
WHERE NOT EXISTS (SELECT 1 FROM cb_basic b WHERE b.ts_code = p.ts_code);

-- cb_basic: 完整性检查
SELECT 'cb_basic' AS table_name,
       'conv_price IS NULL' AS check_item,
       COUNT(*) AS anomaly_count
FROM cb_basic WHERE conv_price IS NULL;

-- ──────────────────────────────────────────────────────────────
-- 基本面数据 (3 张表)
-- ──────────────────────────────────────────────────────────────

\echo ''
\echo '--- [基本面数据] ---'

SELECT 'financial_income' AS table_name,
       'total_revenue IS NULL' AS check_item,
       COUNT(*) AS anomaly_count
FROM financial_income WHERE total_revenue IS NULL;

SELECT 'financial_balance' AS table_name,
       'total_assets IS NULL' AS check_item,
       COUNT(*) AS anomaly_count
FROM financial_balance WHERE total_assets IS NULL;

SELECT 'stocks' AS table_name,
       'market_cap IS NULL' AS check_item,
       COUNT(*) AS anomaly_count
FROM stocks WHERE market_cap IS NULL AND is_st = 0;

-- ──────────────────────────────────────────────────────────────
-- 新鲜度检查 (数据滞后天数)
-- ──────────────────────────────────────────────────────────────

\echo ''
\echo '--- [数据新鲜度] ---'

SELECT 'daily_kline' AS table_name,
       'max trade_date' AS check_item,
       CURRENT_DATE - MAX(trade_date) AS days_behind
FROM daily_kline
UNION ALL
SELECT 'cb_daily', 'max trade_date', CURRENT_DATE - MAX(trade_date)
FROM cb_daily
UNION ALL
SELECT 'cb_factor', 'max trade_date', CURRENT_DATE - MAX(trade_date)
FROM cb_factor
UNION ALL
SELECT 'index_daily', 'max trade_date', CURRENT_DATE - MAX(trade_date)
FROM index_daily
UNION ALL
SELECT 'ths_daily', 'max trade_date', CURRENT_DATE - MAX(trade_date)
FROM ths_daily
UNION ALL
SELECT 'stk_auction_o', 'max trade_date', CURRENT_DATE - MAX(trade_date)
FROM stk_auction_o
UNION ALL
SELECT 'stk_mins', 'max trade_date', CURRENT_DATE - MAX(trade_time)::DATE
FROM stk_mins;

-- ──────────────────────────────────────────────────────────────
-- 汇总
-- ──────────────────────────────────────────────────────────────

\echo ''
\echo '========================================'
\echo ' 质量检查完成'
\echo '========================================'
