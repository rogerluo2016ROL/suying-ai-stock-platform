-- 参数型接口目录：记录调用所需参数，避免用空参数伪造数据。
CREATE TABLE IF NOT EXISTS tushare_api_parameter_catalog (
    api TEXT PRIMARY KEY,
    required_params TEXT[] NOT NULL,
    parameter_source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'configured',
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO tushare_api_parameter_catalog (api, required_params, parameter_source, note)
VALUES
('cb_price_chg', ARRAY['ts_code'], 'cb_basic.code', '可转债代码'),
('fina_audit', ARRAY['ts_code'], 'stocks.code', '股票代码'),
('fina_mainbz', ARRAY['ts_code'], 'stocks.code', '股票代码'),
('ft_mins', ARRAY['ts_code','freq'], 'configured_universe', '分钟频率与标的'),
('fund_nav', ARRAY['ts_code','nav_date'], 'fund_basic.code/date', '基金代码或净值日期至少一个'),
('fut_weekly_monthly', ARRAY['freq'], 'fixed', '周线或月线频率'),
('hk_balancesheet', ARRAY['ts_code'], 'hk_basic.code', '港股代码'),
('hk_cashflow', ARRAY['ts_code'], 'hk_basic.code', '港股代码'),
('hk_fina_indicator', ARRAY['ts_code'], 'hk_basic.code', '港股代码'),
('hk_income', ARRAY['ts_code'], 'hk_basic.code', '港股代码'),
('hk_mins', ARRAY['ts_code','freq'], 'configured_universe', '分钟频率与标的'),
('idx_mins', ARRAY['ts_code'], 'index_basic.code', '指数代码'),
('opt_mins', ARRAY['ts_code'], 'opt_basic.ts_code', '期权代码'),
('rt_etf_k', ARRAY['ts_code'], 'etf_basic.ts_code', 'ETF代码'),
('rt_fut_min', ARRAY['freq'], 'fixed', '分钟频率'),
('rt_hk_k', ARRAY['ts_code'], 'hk_basic.code', '港股代码'),
('rt_idx_k', ARRAY['ts_code'], 'index_basic.code', '指数代码'),
('rt_idx_min', ARRAY['freq'], 'fixed', '分钟频率'),
('rt_k', ARRAY['ts_code'], 'stocks.code', '股票代码'),
('rt_min', ARRAY['freq'], 'fixed', '分钟频率'),
('stk_rewards', ARRAY['ts_code'], 'stocks.code', '股票代码'),
('stk_week_month_adj', ARRAY['freq'], 'fixed', '周线或月线频率'),
('stk_weekly_monthly', ARRAY['freq'], 'fixed', '周线或月线频率'),
('us_balancesheet', ARRAY['ts_code'], 'us_basic.ts_code', '美股代码'),
('us_cashflow', ARRAY['ts_code'], 'us_basic.ts_code', '美股代码'),
('us_income', ARRAY['ts_code'], 'us_basic.ts_code', '美股代码')
ON CONFLICT (api) DO UPDATE SET
    required_params=EXCLUDED.required_params,
    parameter_source=EXCLUDED.parameter_source,
    note=EXCLUDED.note,
    updated_at=NOW();
