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

-- 开盘集合竞价 (stk_auction_o, 特色数据权限)
CREATE TABLE IF NOT EXISTS stk_auction_o (id SERIAL PRIMARY KEY, ts_code TEXT NOT NULL, trade_date DATE NOT NULL, pre_close DOUBLE PRECISION, price DOUBLE PRECISION, volume DOUBLE PRECISION, amount DOUBLE PRECISION, bid_volume DOUBLE PRECISION, ask_volume DOUBLE PRECISION, bid_amount DOUBLE PRECISION, ask_amount DOUBLE PRECISION, UNIQUE(ts_code, trade_date));
