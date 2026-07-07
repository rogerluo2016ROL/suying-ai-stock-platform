-- 021: research_reports_tushare + broker_recommend schema fix
-- 新增 Tushare 接口返回的额外字段, pub_date 改为可空(部分研报缺日期)

ALTER TABLE research_reports_tushare ADD COLUMN IF NOT EXISTS trade_date date;
ALTER TABLE research_reports_tushare ADD COLUMN IF NOT EXISTS report_type text;
ALTER TABLE research_reports_tushare ADD COLUMN IF NOT EXISTS author text;
ALTER TABLE research_reports_tushare ADD COLUMN IF NOT EXISTS name text;
ALTER TABLE research_reports_tushare ALTER COLUMN pub_date DROP NOT NULL;

ALTER TABLE broker_recommend ADD COLUMN IF NOT EXISTS name text;
