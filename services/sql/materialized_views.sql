-- ═══════════════════════════════════════════════════════════════
-- 速赢AI — 物化视图 DDL（盘后预计算，加速选股 Dashboard）
--
-- 用法: psql -U kronos -d kronos -f services/sql/materialized_views.sql
-- 刷新: REFRESH MATERIALIZED VIEW CONCURRENTLY <view_name>;
-- 调度: data-service scheduler cron "30 18 * * 1-5" 自动刷新
-- ═══════════════════════════════════════════════════════════════

-- ── 1. 今日强势股视图 ──
-- 筛选涨幅 7%-12% 的强势股（排除涨停板），含封板检测
DROP MATERIALIZED VIEW IF EXISTS mv_today_strong_stocks;
CREATE MATERIALIZED VIEW mv_today_strong_stocks AS
SELECT
    d.code,
    s.name,
    s.industry,
    d.close,
    sl.pre_close,
    ((d.close / NULLIF(sl.pre_close, 0) - 1) * 100)::numeric(6,2) AS gain_pct,
    (d.amount / 1e8)::numeric(10,1) AS amount_yi,
    d.volume,
    sl.up_limit,
    CASE
        WHEN d.close >= (sl.up_limit * 0.995) THEN true
        ELSE false
    END AS is_limit_up
FROM daily_kline d
JOIN stk_limit sl ON d.code = sl.code AND d.trade_date = sl.trade_date
JOIN stocks s ON d.code = s.code
WHERE d.trade_date = (SELECT MAX(trade_date) FROM daily_kline)
  AND sl.pre_close > 0
  AND d.close > 0
  AND s.name NOT LIKE '%ST%'
  AND ((d.close / sl.pre_close - 1) * 100) >= 7
  AND ((d.close / sl.pre_close - 1) * 100) <= 12;

CREATE UNIQUE INDEX idx_mv_strong_code ON mv_today_strong_stocks(code);


-- ── 2. 行业动量视图 ──
-- 按申万行业聚合涨幅 ≥7% 的强势股，至少 2 只才纳入
DROP MATERIALIZED VIEW IF EXISTS mv_sector_momentum;
CREATE MATERIALIZED VIEW mv_sector_momentum AS
SELECT
    s.industry,
    count(*) AS strong_count,
    avg((d.close / NULLIF(sl.pre_close, 0) - 1) * 100)::numeric(6,2) AS avg_gain,
    sum(d.amount / 1e8)::numeric(12,1) AS total_amount_yi,
    max((d.close / NULLIF(sl.pre_close, 0) - 1) * 100)::numeric(6,2) AS max_gain
FROM daily_kline d
JOIN stk_limit sl ON d.code = sl.code AND d.trade_date = sl.trade_date
JOIN stocks s ON d.code = s.code
WHERE d.trade_date = (SELECT MAX(trade_date) FROM daily_kline)
  AND sl.pre_close > 0
  AND s.name NOT LIKE '%ST%'
  AND ((d.close / sl.pre_close - 1) * 100) >= 7
GROUP BY s.industry
HAVING count(*) >= 2
ORDER BY count(*) DESC, avg_gain DESC;

CREATE UNIQUE INDEX idx_mv_sector_ind ON mv_sector_momentum(industry);


-- ── 3. 资金净流入 Top 50 视图 ──
-- 按日资金净流入排序，仅包含正流入个股
DROP MATERIALIZED VIEW IF EXISTS mv_top_capital_inflow;
CREATE MATERIALIZED VIEW mv_top_capital_inflow AS
SELECT
    mf.code,
    s.name,
    s.industry,
    (mf.net_mf_amount / 1e8)::numeric(12,2) AS net_inflow_yi,
    d.close,
    ((d.close / NULLIF(sl.pre_close, 0) - 1) * 100)::numeric(6,2) AS gain_pct,
    (d.amount / 1e8)::numeric(10,1) AS amount_yi
FROM moneyflow mf
JOIN daily_kline d ON mf.code = d.code AND mf.trade_date = d.trade_date
JOIN stk_limit sl ON mf.code = sl.code AND mf.trade_date = sl.trade_date
JOIN stocks s ON mf.code = s.code
WHERE mf.trade_date = (SELECT MAX(trade_date) FROM moneyflow)
  AND d.trade_date = (SELECT MAX(trade_date) FROM daily_kline)
  AND mf.net_mf_amount > 0
  AND s.name NOT LIKE '%ST%'
ORDER BY mf.net_mf_amount DESC
LIMIT 50;

CREATE UNIQUE INDEX idx_mv_cap_code ON mv_top_capital_inflow(code);


-- ── 4. 每日综合排名视图 ──
-- 综合评分: 涨幅(0-40) + 资金净流入(0-35) + 换手率(0-25) → 0-100
DROP MATERIALIZED VIEW IF EXISTS mv_daily_composite_ranking;
CREATE MATERIALIZED VIEW mv_daily_composite_ranking AS
SELECT
    d.code,
    s.name,
    s.industry,
    d.close,
    sl.pre_close,
    ((d.close / NULLIF(sl.pre_close, 0) - 1) * 100)::numeric(6,2) AS gain_pct,
    (d.amount / 1e8)::numeric(10,1) AS amount_yi,
    d.turnover_rate,
    COALESCE(mf.net_mf_amount, 0)::numeric(12,2) AS net_mf_amount,
    COALESCE(dbl.pe, 0)::numeric(8,2) AS pe,
    COALESCE(dbl.pb, 0)::numeric(8,2) AS pb,
    (dbl.total_mv / 1e8)::numeric(12,1) AS total_mv_yi,
    (
        CASE WHEN sl.pre_close > 0 THEN
            LEAST(((d.close / sl.pre_close - 1) * 100 + 10) * 3, 40)
        ELSE 0 END
        +
        CASE WHEN COALESCE(mf.net_mf_amount, 0) > 0 THEN
            LEAST(LN(GREATEST(COALESCE(mf.net_mf_amount, 1), 1)) * 3, 35)
        ELSE 0 END
        +
        CASE WHEN d.turnover_rate > 0 THEN
            LEAST(d.turnover_rate * 2, 25)
        ELSE 0 END
    )::numeric(6,2) AS composite_score,
    d.trade_date
FROM daily_kline d
JOIN stk_limit sl ON d.code = sl.code AND d.trade_date = sl.trade_date
JOIN stocks s ON d.code = s.code
LEFT JOIN daily_basic dbl ON d.code = dbl.code AND d.trade_date = dbl.trade_date
LEFT JOIN moneyflow mf ON d.code = mf.code AND d.trade_date = mf.trade_date
WHERE d.trade_date = (SELECT MAX(trade_date) FROM daily_kline)
  AND d.close > 0
  AND sl.pre_close > 0
  AND s.name NOT LIKE '%ST%'
  AND s.name NOT LIKE '%退市%';

CREATE UNIQUE INDEX idx_mv_composite_code ON mv_daily_composite_ranking(code);
