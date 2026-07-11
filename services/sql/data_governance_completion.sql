-- 可重复执行的数据治理迁移。只增加兼容字段，不删除历史数据。
ALTER TABLE daily_basic
    ADD COLUMN IF NOT EXISTS turnover_rate_f DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pe_ttm DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ps DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ps_ttm DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS dv_ratio DOUBLE PRECISION;

ALTER TABLE dividend_data
    ADD COLUMN IF NOT EXISTS end_date DATE,
    ADD COLUMN IF NOT EXISTS ann_date DATE,
    ADD COLUMN IF NOT EXISTS stk_div DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS stk_bo_rate DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS record_date DATE;

ALTER TABLE share_float
    ADD COLUMN IF NOT EXISTS ann_date DATE,
    ADD COLUMN IF NOT EXISTS holder_name TEXT;

ALTER TABLE stk_holdernumber
    ALTER COLUMN holder_num TYPE BIGINT;

ALTER TABLE margin_summary
    ADD COLUMN IF NOT EXISTS rzmre DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS rzche DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS rqmcl DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS rzrqye DOUBLE PRECISION;

ALTER TABLE block_trade_data
    ADD COLUMN IF NOT EXISTS vol DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS buyer TEXT,
    ADD COLUMN IF NOT EXISTS seller TEXT;

ALTER TABLE repurchase
    ADD COLUMN IF NOT EXISTS end_date DATE,
    ADD COLUMN IF NOT EXISTS proc TEXT,
    ADD COLUMN IF NOT EXISTS vol DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS amount DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_daily_basic_trade_date_code
    ON daily_basic (trade_date, code);
CREATE INDEX IF NOT EXISTS idx_dividend_data_ex_date_code
    ON dividend_data (ex_date, code);
CREATE INDEX IF NOT EXISTS idx_share_float_float_date_code
    ON share_float (float_date, code);
CREATE INDEX IF NOT EXISTS idx_stock_news_tushare_pub_time
    ON stock_news_tushare (pub_time);
