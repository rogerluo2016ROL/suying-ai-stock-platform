-- 022: forecast_data schema fix — 补全 Tushare 返回字段

ALTER TABLE forecast_data ADD COLUMN IF NOT EXISTS ann_date date;
ALTER TABLE forecast_data ADD COLUMN IF NOT EXISTS net_profit_min double precision;
ALTER TABLE forecast_data ADD COLUMN IF NOT EXISTS net_profit_max double precision;
ALTER TABLE forecast_data ADD COLUMN IF NOT EXISTS change_reason text;
