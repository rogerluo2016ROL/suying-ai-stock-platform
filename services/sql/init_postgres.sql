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

-- ADR-008: 15 列对齐 etl sync_sw_daily (Tushare sw_daily 5000 积分接口全字段)
-- 单位: vol=万股, amount=万元, float_mv=万元, total_mv=万元 (Tushare 原值直写, sync 不做单位转换)
CREATE TABLE IF NOT EXISTS sw_daily (
    code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    name TEXT,
    open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION,
    change DOUBLE PRECISION,
    change_pct DOUBLE PRECISION,
    pe DOUBLE PRECISION, pb DOUBLE PRECISION,
    float_mv DOUBLE PRECISION, total_mv DOUBLE PRECISION,
    vol DOUBLE PRECISION, amount DOUBLE PRECISION,
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

CREATE TABLE IF NOT EXISTS fina_audit (
    code TEXT NOT NULL,
    ann_date DATE NOT NULL,
    end_date DATE NOT NULL,
    audit_result TEXT,
    audit_fees DOUBLE PRECISION,
    audit_agency TEXT,
    audit_sign TEXT,
    CONSTRAINT fina_audit_pkey PRIMARY KEY(code, end_date)
);
CREATE INDEX IF NOT EXISTS idx_fina_audit_result ON fina_audit(audit_result);

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
    main_business TEXT, website TEXT,
    city TEXT, setup_date TEXT, business_scope TEXT, email TEXT,
    chairman TEXT, manager TEXT, secretary TEXT,
    employees INTEGER, introduction TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stock_profiles_province ON stock_profiles(province);

-- ── P2: 资讯舆情数据 (5 张表) ──

-- 互动问答 (深交所互动易 + 上证e互动)
CREATE TABLE IF NOT EXISTS interact_qa (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    pub_date DATE NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    pub_time TIMESTAMP,
    source TEXT DEFAULT 'szse',
    CONSTRAINT interact_qa_uniq UNIQUE(code, pub_date, question)
);
CREATE INDEX IF NOT EXISTS idx_interact_qa_code ON interact_qa(code);
CREATE INDEX IF NOT EXISTS idx_interact_qa_date ON interact_qa(pub_date);

-- 国家政策法规库 (国务院及各部委)
CREATE TABLE IF NOT EXISTS policy_law (
    id SERIAL PRIMARY KEY,
    pub_date TIMESTAMP,
    title TEXT NOT NULL,
    url TEXT,
    content_html TEXT,
    pcode TEXT,
    puborg TEXT,
    ptype TEXT,
    CONSTRAINT policy_law_uniq UNIQUE(pub_date, title)
);
CREATE INDEX IF NOT EXISTS idx_policy_law_ptype ON policy_law(ptype);
CREATE INDEX IF NOT EXISTS idx_policy_law_puborg ON policy_law(puborg);

-- 央行货币政策执行报告
CREATE TABLE IF NOT EXISTS mp_report (
    id SERIAL PRIMARY KEY,
    pub_date DATE NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    pdf_url TEXT,
    content_html TEXT,
    CONSTRAINT mp_report_uniq UNIQUE(pub_date, title)
);

-- 新闻联播文字稿
CREATE TABLE IF NOT EXISTS cctv_news (
    id SERIAL PRIMARY KEY,
    pub_date DATE NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    channels TEXT,
    CONSTRAINT cctv_news_uniq UNIQUE(pub_date, title)
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
    biz_item TEXT NOT NULL,
    biz_income DOUBLE PRECISION,
    biz_ratio DOUBLE PRECISION,
    biz_type TEXT DEFAULT 'P',
    CONSTRAINT fina_mainbz_pk UNIQUE(code, end_date, biz_item)
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
    pct_change DOUBLE PRECISION NOT NULL,
    avg_price DOUBLE PRECISION,
    total_mv DOUBLE PRECISION,
    float_mv DOUBLE PRECISION,
    PRIMARY KEY(ts_code, trade_date)
);

-- 同花顺概念板块成分股映射 (ths_concept_map, 每月同步)
CREATE TABLE IF NOT EXISTS ths_concept_map (
    id SERIAL PRIMARY KEY,
    ts_code TEXT NOT NULL,
    concept_name TEXT NOT NULL,
    concept_code TEXT NOT NULL,
    trade_date DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE(ts_code, concept_name)
);
CREATE INDEX IF NOT EXISTS idx_ths_concept_map_code ON ths_concept_map(ts_code);
CREATE INDEX IF NOT EXISTS idx_ths_concept_map_concept ON ths_concept_map(concept_name);

-- ── 物化视图: 每日综合排名 (涨幅 + 资金 + 估值 + 流动性) ──
-- 盘后刷新，为选股 Dashboard 提供预计算数据
-- 物化视图 DDL 在 services/sql/materialized_views.sql（4 视图 + 各自索引）
-- docker-compose 挂 materialized_views.sql 作 02_，首启 01 建表 → 02 建 MV
-- （原 CREATE UNIQUE INDEX ON mv_daily_composite_ranking 是孤儿——MV 不在此文件，
--   索引在 materialized_views.sql:132；删此避免新卷首启 init exit 3）

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
    UNIQUE(ts_code, trade_date),
    CONSTRAINT chk_cb_daily_valid CHECK (close > 0 AND amount >= 0)
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
    publish_date DATE,
    convert_price_initial DOUBLE PRECISION,
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

CREATE TABLE IF NOT EXISTS cb_concept (
    id SERIAL PRIMARY KEY,
    ts_code TEXT NOT NULL REFERENCES cb_basic(ts_code),
    concept TEXT NOT NULL,
    bond_name TEXT,
    UNIQUE(ts_code, concept)
);
CREATE INDEX IF NOT EXISTS idx_cb_concept_code ON cb_concept(ts_code);
CREATE INDEX IF NOT EXISTS idx_cb_concept_name ON cb_concept(concept);

-- cb_factor_pro: 精选技术指标 (从89个字段中提取关键的18个, 含KDJ)
CREATE TABLE IF NOT EXISTS cb_factor (
    ts_code TEXT NOT NULL REFERENCES cb_basic(ts_code),
    trade_date DATE NOT NULL,
    close DOUBLE PRECISION,
    pre_close DOUBLE PRECISION,
    pct_change DOUBLE PRECISION,
    vol DOUBLE PRECISION,
    amount DOUBLE PRECISION,
    rsi_6 DOUBLE PRECISION,
    rsi_12 DOUBLE PRECISION,
    rsi_24 DOUBLE PRECISION,
    macd DOUBLE PRECISION,
    macd_dif DOUBLE PRECISION,
    macd_dea DOUBLE PRECISION,
    boll_upper DOUBLE PRECISION,
    boll_mid DOUBLE PRECISION,
    boll_lower DOUBLE PRECISION,
    atr DOUBLE PRECISION,
    ma_5 DOUBLE PRECISION,
    ma_20 DOUBLE PRECISION,
    ma_60 DOUBLE PRECISION,
    kdj_k DOUBLE PRECISION,
    kdj_d DOUBLE PRECISION,
    kdj_j DOUBLE PRECISION,
    PRIMARY KEY (ts_code, trade_date),
    CONSTRAINT chk_rsi_range CHECK (rsi_6 BETWEEN 0 AND 100 AND rsi_12 BETWEEN 0 AND 100 AND rsi_24 BETWEEN 0 AND 100)
);
CREATE INDEX IF NOT EXISTS idx_cb_factor_code ON cb_factor(ts_code);
CREATE INDEX IF NOT EXISTS idx_cb_factor_date ON cb_factor(trade_date);
