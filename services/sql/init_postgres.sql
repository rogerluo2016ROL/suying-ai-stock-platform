-- ═══════════════════════════════════════════════════════════════
-- 速赢AI 证券投资管理平台 — PostgreSQL 初始化脚本
--
-- 从 Kronos SQLite (48 张表) 迁移到 PostgreSQL 15
-- 用法: psql -U kronos -d kronos -f init_postgres.sql
-- ═══════════════════════════════════════════════════════════════

-- ── 行情数据 (8 张表) ──

CREATE TABLE IF NOT EXISTS stocks (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    board TEXT NOT NULL,
    industry TEXT,
    market_cap DOUBLE PRECISION,
    float_mv DOUBLE PRECISION,
    pe_ratio DOUBLE PRECISION,
    pb_ratio DOUBLE PRECISION,
    listed_date DATE,
    is_st INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_kline (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL REFERENCES stocks(code),
    trade_date DATE NOT NULL,
    open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION,
    volume DOUBLE PRECISION, amount DOUBLE PRECISION,
    turnover_rate DOUBLE PRECISION, change_pct DOUBLE PRECISION, amplitude DOUBLE PRECISION,
    UNIQUE(code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_daily_kline_code ON daily_kline(code);
CREATE INDEX IF NOT EXISTS idx_daily_kline_date ON daily_kline(trade_date);

CREATE TABLE IF NOT EXISTS weekly_kline (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL REFERENCES stocks(code),
    trade_date DATE NOT NULL,
    open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION,
    volume DOUBLE PRECISION, amount DOUBLE PRECISION,
    UNIQUE(code, trade_date)
);

CREATE TABLE IF NOT EXISTS monthly_kline (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL REFERENCES stocks(code),
    trade_date DATE NOT NULL,
    open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION,
    volume DOUBLE PRECISION, amount DOUBLE PRECISION,
    UNIQUE(code, trade_date)
);

CREATE TABLE IF NOT EXISTS adj_factor (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    adj_factor DOUBLE PRECISION,
    PRIMARY KEY(code, trade_date)
);

CREATE TABLE IF NOT EXISTS daily_basic (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    pe DOUBLE PRECISION, pb DOUBLE PRECISION,
    total_mv DOUBLE PRECISION, circ_mv DOUBLE PRECISION,
    turnover_rate DOUBLE PRECISION, volume_ratio DOUBLE PRECISION,
    PRIMARY KEY(code, trade_date)
);

CREATE TABLE IF NOT EXISTS stk_limit (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    pre_close DOUBLE PRECISION, up_limit DOUBLE PRECISION, down_limit DOUBLE PRECISION,
    limit_status TEXT,
    PRIMARY KEY(code, trade_date)
);

CREATE TABLE IF NOT EXISTS index_daily (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION,
    volume DOUBLE PRECISION, amount DOUBLE PRECISION,
    change_pct DOUBLE PRECISION,
    PRIMARY KEY(code, trade_date)
);

CREATE TABLE IF NOT EXISTS index_basic (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT,
    publisher TEXT
);

CREATE TABLE IF NOT EXISTS sw_daily (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION,
    change_pct DOUBLE PRECISION,
    PRIMARY KEY(code, trade_date)
);

-- ── 资金面数据 (8 张表) ──

CREATE TABLE IF NOT EXISTS moneyflow (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    buy_sm_amount DOUBLE PRECISION, sell_sm_amount DOUBLE PRECISION,
    buy_md_amount DOUBLE PRECISION, sell_md_amount DOUBLE PRECISION,
    buy_lg_amount DOUBLE PRECISION, sell_lg_amount DOUBLE PRECISION,
    buy_elg_amount DOUBLE PRECISION, sell_elg_amount DOUBLE PRECISION,
    net_mf_amount DOUBLE PRECISION,
    PRIMARY KEY(code, trade_date)
);

CREATE TABLE IF NOT EXISTS moneyflow_hsgt (
    trade_date DATE PRIMARY KEY,
    north_net_inflow DOUBLE PRECISION,
    south_net_inflow DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS hk_holdings (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    vol DOUBLE PRECISION, ratio DOUBLE PRECISION,
    PRIMARY KEY(code, trade_date)
);

CREATE TABLE IF NOT EXISTS margin_detail (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    rzye DOUBLE PRECISION, rzmre DOUBLE PRECISION, rzche DOUBLE PRECISION,
    rqye DOUBLE PRECISION, rqmcl DOUBLE PRECISION, rqchl DOUBLE PRECISION,
    PRIMARY KEY(code, trade_date)
);

CREATE TABLE IF NOT EXISTS margin_summary (
    trade_date DATE PRIMARY KEY,
    rzye DOUBLE PRECISION, rqye DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS top_list (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    reason TEXT,
    buy_amount DOUBLE PRECISION, sell_amount DOUBLE PRECISION, net_amount DOUBLE PRECISION,
    PRIMARY KEY(code, trade_date)
);

CREATE TABLE IF NOT EXISTS top_inst (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    inst_name TEXT, buy_amount DOUBLE PRECISION, sell_amount DOUBLE PRECISION, net_amount DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS block_trade_data (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    price DOUBLE PRECISION, volume DOUBLE PRECISION, amount DOUBLE PRECISION,
    buyer_broker TEXT, seller_broker TEXT
);

-- ── 基本面数据 (8 张表) ──

CREATE TABLE IF NOT EXISTS financial_income (
    code TEXT NOT NULL,
    end_date DATE NOT NULL,
    report_type TEXT,
    total_revenue DOUBLE PRECISION, operating_profit DOUBLE PRECISION,
    net_profit DOUBLE PRECISION, net_profit_parent DOUBLE PRECISION,
    PRIMARY KEY(code, end_date, report_type)
);

CREATE TABLE IF NOT EXISTS financial_balance (
    code TEXT NOT NULL,
    end_date DATE NOT NULL,
    report_type TEXT,
    total_assets DOUBLE PRECISION, total_liabilities DOUBLE PRECISION,
    shareholders_equity DOUBLE PRECISION,
    PRIMARY KEY(code, end_date, report_type)
);

CREATE TABLE IF NOT EXISTS financial_cashflow (
    code TEXT NOT NULL,
    end_date DATE NOT NULL,
    report_type TEXT,
    net_cash_flow_oper DOUBLE PRECISION, net_cash_flow_invest DOUBLE PRECISION,
    net_cash_flow_finance DOUBLE PRECISION,
    PRIMARY KEY(code, end_date, report_type)
);

CREATE TABLE IF NOT EXISTS financial_indicator (
    code TEXT NOT NULL,
    end_date DATE NOT NULL,
    roe DOUBLE PRECISION, roa DOUBLE PRECISION,
    gross_margin DOUBLE PRECISION, net_margin DOUBLE PRECISION,
    debt_ratio DOUBLE PRECISION, current_ratio DOUBLE PRECISION,
    eps DOUBLE PRECISION, bps DOUBLE PRECISION,
    revenue_growth DOUBLE PRECISION, profit_growth DOUBLE PRECISION,
    PRIMARY KEY(code, end_date)
);

CREATE TABLE IF NOT EXISTS financial_abstracts (
    code TEXT PRIMARY KEY,
    data JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS forecast_data (
    code TEXT NOT NULL,
    end_date DATE NOT NULL,
    forecast_type TEXT,
    forecast_net_profit DOUBLE PRECISION,
    PRIMARY KEY(code, end_date, forecast_type)
);

CREATE TABLE IF NOT EXISTS profit_forecasts (
    code TEXT NOT NULL,
    report_date DATE NOT NULL,
    forecast_eps DOUBLE PRECISION, forecast_net_profit DOUBLE PRECISION,
    analyst_count INTEGER,
    PRIMARY KEY(code, report_date)
);

CREATE TABLE IF NOT EXISTS dividend_data (
    code TEXT NOT NULL,
    ex_date DATE NOT NULL,
    dividend_plan TEXT,
    cash_div DOUBLE PRECISION, bonus_share_ratio DOUBLE PRECISION,
    PRIMARY KEY(code, ex_date)
);

-- ── 机构与股东数据 (6 张表) ──

CREATE TABLE IF NOT EXISTS stk_holdertrade (
    code TEXT NOT NULL,
    ann_date DATE NOT NULL,
    holder_name TEXT, holder_type TEXT,
    change_vol DOUBLE PRECISION, change_ratio DOUBLE PRECISION,
    after_holding DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS stk_holdernumber (
    code TEXT NOT NULL,
    end_date DATE NOT NULL,
    holder_num INTEGER,
    PRIMARY KEY(code, end_date)
);

CREATE TABLE IF NOT EXISTS share_float (
    code TEXT NOT NULL,
    float_date DATE NOT NULL,
    float_share DOUBLE PRECISION, float_ratio DOUBLE PRECISION,
    PRIMARY KEY(code, float_date)
);

CREATE TABLE IF NOT EXISTS pledge_detail (
    code TEXT NOT NULL,
    end_date DATE NOT NULL,
    pledge_amount DOUBLE PRECISION, pledge_ratio DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS repurchase (
    code TEXT NOT NULL,
    ann_date DATE NOT NULL,
    repurchase_amount DOUBLE PRECISION, repurchase_price DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS cyq_chips (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    avg_cost DOUBLE PRECISION,
    concentration_90 DOUBLE PRECISION,
    profit_ratio DOUBLE PRECISION,
    PRIMARY KEY(code, trade_date)
);

-- ── 研究与新闻数据 (4 张表) ──

CREATE TABLE IF NOT EXISTS research_reports (
    code TEXT NOT NULL,
    pub_date DATE NOT NULL,
    title TEXT, broker TEXT,
    rating TEXT, target_price DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS research_reports_tushare (
    code TEXT NOT NULL,
    pub_date DATE NOT NULL,
    title TEXT, broker TEXT,
    rating TEXT, target_price DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS stock_news (
    code TEXT NOT NULL,
    pub_time TIMESTAMP NOT NULL,
    title TEXT, content TEXT, source TEXT
);

CREATE TABLE IF NOT EXISTS stock_news_tushare (
    code TEXT NOT NULL,
    pub_time TIMESTAMP NOT NULL,
    title TEXT, content TEXT, source TEXT
);

-- ── 其他 (11 张表) ──

CREATE TABLE IF NOT EXISTS stock_profiles (
    code TEXT PRIMARY KEY,
    full_name TEXT, province TEXT, reg_capital DOUBLE PRECISION,
    main_business TEXT, website TEXT
);

CREATE TABLE IF NOT EXISTS broker_recommend (
    code TEXT NOT NULL,
    month TEXT NOT NULL,
    broker TEXT,
    PRIMARY KEY(code, month, broker)
);

CREATE TABLE IF NOT EXISTS announcements (
    code TEXT NOT NULL,
    ann_date DATE NOT NULL,
    title TEXT, ann_type TEXT, content TEXT
);

CREATE TABLE IF NOT EXISTS fina_mainbz (
    code TEXT NOT NULL,
    end_date DATE NOT NULL,
    biz_item TEXT, biz_income DOUBLE PRECISION, biz_ratio DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS rt_sw_k (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION,
    PRIMARY KEY(code, trade_date)
);

-- ── 应用层表 ──

CREATE TABLE IF NOT EXISTS screening_scores (
    id SERIAL PRIMARY KEY,
    batch_id TEXT NOT NULL,
    code TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    grade TEXT NOT NULL,
    momentum DOUBLE PRECISION, volume_factor DOUBLE PRECISION,
    technical DOUBLE PRECISION, quality DOUBLE PRECISION, risk DOUBLE PRECISION,
    kronos_trend_score DOUBLE PRECISION, kronos_pred_return DOUBLE PRECISION,
    fund_score DOUBLE PRECISION, signal TEXT, reason TEXT, strategy TEXT,
    target_price DOUBLE PRECISION, stop_loss DOUBLE PRECISION, rank INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS screening_batches (
    batch_id TEXT PRIMARY KEY,
    total_stocks INTEGER, scored_stocks INTEGER,
    elapsed DOUBLE PRECISION, status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    pred_version TEXT NOT NULL,
    pred_date TIMESTAMP DEFAULT NOW(),
    pred_30d_close DOUBLE PRECISION, pred_return DOUBLE PRECISION,
    max_drawdown DOUBLE PRECISION, confidence DOUBLE PRECISION,
    pred_data JSONB
);

CREATE TABLE IF NOT EXISTS prediction_versions (
    version TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prediction_details (
    id SERIAL PRIMARY KEY,
    prediction_id INTEGER REFERENCES predictions(id),
    day_offset INTEGER, pred_open DOUBLE PRECISION,
    pred_high DOUBLE PRECISION, pred_low DOUBLE PRECISION, pred_close DOUBLE PRECISION,
    pred_volume DOUBLE PRECISION, pred_amount DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS backtest_records (
    id SERIAL PRIMARY KEY,
    batch_id TEXT NOT NULL,
    code TEXT NOT NULL,
    pred_score DOUBLE PRECISION,
    actual_return_5d DOUBLE PRECISION, actual_return_10d DOUBLE PRECISION,
    actual_return_20d DOUBLE PRECISION, actual_return_60d DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS watchlist (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL REFERENCES stocks(code),
    added_at TIMESTAMP DEFAULT NOW(),
    note TEXT
);

-- 实时日K线 (rt_k, Level-2 权限)
CREATE TABLE IF NOT EXISTS rt_k (id SERIAL PRIMARY KEY, ts_code TEXT NOT NULL, trade_date DATE NOT NULL, open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION, pre_close DOUBLE PRECISION, change DOUBLE PRECISION, pct_chg DOUBLE PRECISION, vol DOUBLE PRECISION, amount DOUBLE PRECISION, UNIQUE(ts_code, trade_date));

-- 开盘集合竞价 (stk_auction_o, 从 9:30 首根5min K线采集 — scheduler.collect_auction_snapshot)
CREATE TABLE IF NOT EXISTS stk_auction_o (id SERIAL PRIMARY KEY, code TEXT NOT NULL, trade_date DATE NOT NULL, open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION, vol DOUBLE PRECISION, amount DOUBLE PRECISION, vwap DOUBLE PRECISION, UNIQUE(code, trade_date));

-- 实时分钟线 (stk_mins, 来自 Tushare rt_min API + PG 直写)
CREATE TABLE IF NOT EXISTS stk_mins (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    trade_time TIMESTAMP NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    amount DOUBLE PRECISION,
    freq TEXT NOT NULL DEFAULT '5min',
    UNIQUE(code, trade_time, freq)
);
CREATE INDEX IF NOT EXISTS idx_stk_mins_code ON stk_mins(code);
CREATE INDEX IF NOT EXISTS idx_stk_mins_time ON stk_mins(trade_time);

-- 涨跌停列表 (limit_list_d, 来自 Tushare limit_list_d API)
CREATE TABLE IF NOT EXISTS limit_list_d (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    ts_code TEXT,
    name TEXT,
    close DOUBLE PRECISION,
    pct_chg DOUBLE PRECISION,
    amount DOUBLE PRECISION,
    float_mv DOUBLE PRECISION,
    turnover_ratio DOUBLE PRECISION,
    fd_amount DOUBLE PRECISION,
    first_time TEXT,
    last_time TEXT,
    open_times INTEGER,
    up_stat TEXT,
    limit_times INTEGER,
    PRIMARY KEY(code, trade_date)
);

-- 同花顺每日指标 (ths_daily, 来自 Tushare ths_daily API)
CREATE TABLE IF NOT EXISTS ths_daily (
    ts_code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    name TEXT,
    close DOUBLE PRECISION,
    pct_change DOUBLE PRECISION,
    avg_price DOUBLE PRECISION,
    total_mv DOUBLE PRECISION,
    float_mv DOUBLE PRECISION,
    PRIMARY KEY(ts_code, trade_date)
);

-- ── 物化视图: 每日综合排名 (涨幅 + 资金 + 估值 + 流动性) ──
-- 盘后刷新，为选股 Dashboard 提供预计算数据
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
    (d.volume / NULLIF(dbl.volume_ratio, 0))::numeric(10,1) AS avg_vol_ratio,
    COALESCE(mf.net_mf_amount, 0)::numeric(12,2) AS net_mf_amount,
    COALESCE(dbl.pe, 0)::numeric(8,2) AS pe,
    COALESCE(dbl.pb, 0)::numeric(8,2) AS pb,
    (dbl.total_mv / 1e8)::numeric(12,1) AS total_mv_yi,
    -- 综合评分: 涨幅归一化 + 资金归一化 + 流动性归一化 (0-100)
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

-- ── 可转债 (3 张表) ──

CREATE TABLE IF NOT EXISTS cb_basic (
    ts_code TEXT PRIMARY KEY,
    bond_full_name TEXT,
    bond_short_name TEXT,
    cb_code TEXT,
    cb_type TEXT,
    stk_code TEXT,
    stk_short_name TEXT,
    maturity DOUBLE PRECISION,
    par DOUBLE PRECISION,
    issue_price DOUBLE PRECISION,
    issue_size DOUBLE PRECISION,
    remain_size DOUBLE PRECISION,
    value_date DATE,
    maturity_date DATE,
    rate_type TEXT,
    coupon_rate DOUBLE PRECISION,
    add_rate DOUBLE PRECISION,
    pay_per_year INTEGER,
    list_date DATE,
    delist_date DATE,
    exchange TEXT,
    conv_start_date DATE,
    conv_end_date DATE,
    conv_stop_date DATE,
    first_conv_price DOUBLE PRECISION,
    conv_price DOUBLE PRECISION,
    rate_clause TEXT,
    put_clause TEXT,
    maturity_call_price TEXT,
    call_clause TEXT,
    reset_clause TEXT,
    conv_clause TEXT,
    guarantor TEXT,
    guarantee_type TEXT,
    issue_rating TEXT,
    newest_rating TEXT,
    rating_comp TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cb_daily (
    id SERIAL PRIMARY KEY,
    ts_code TEXT NOT NULL REFERENCES cb_basic(ts_code),
    trade_date DATE NOT NULL,
    pre_close DOUBLE PRECISION,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    change DOUBLE PRECISION,
    pct_chg DOUBLE PRECISION,
    vol DOUBLE PRECISION,
    amount DOUBLE PRECISION,
    bond_value DOUBLE PRECISION,
    bond_over_rate DOUBLE PRECISION,
    cb_value DOUBLE PRECISION,
    cb_over_rate DOUBLE PRECISION,
    UNIQUE(ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_cb_daily_code ON cb_daily(ts_code);
CREATE INDEX IF NOT EXISTS idx_cb_daily_date ON cb_daily(trade_date);

CREATE TABLE IF NOT EXISTS cb_price_chg (
    id SERIAL PRIMARY KEY,
    ts_code TEXT NOT NULL REFERENCES cb_basic(ts_code),
    change_date DATE NOT NULL,
    pre_price DOUBLE PRECISION,
    new_price DOUBLE PRECISION,
    change_reason TEXT,
    UNIQUE(ts_code, change_date)
);

CREATE INDEX IF NOT EXISTS idx_cb_price_chg_code ON cb_price_chg(ts_code);

CREATE TABLE IF NOT EXISTS cb_call (
    id SERIAL PRIMARY KEY,
    ts_code TEXT NOT NULL REFERENCES cb_basic(ts_code),
    call_type TEXT,
    is_call TEXT,
    ann_date DATE,
    call_date DATE,
    call_price DOUBLE PRECISION,
    call_price_tax DOUBLE PRECISION,
    call_vol DOUBLE PRECISION,
    call_amount DOUBLE PRECISION,
    payment_date DATE,
    call_reg_date DATE,
    UNIQUE(ts_code, ann_date, call_type)
);

CREATE INDEX IF NOT EXISTS idx_cb_call_code ON cb_call(ts_code);
CREATE INDEX IF NOT EXISTS idx_cb_call_date ON cb_call(call_date);
