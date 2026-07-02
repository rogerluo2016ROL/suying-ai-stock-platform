# Tushare 数据资产目录

> 生成时间: 2026-07-02T10:58:45

## 汇总

- Tushare 本地接口文档 API 数: 224
- 前端/后端已登记数据源: 34
- PG+ETL 双覆盖: 33
- 10 年跨度达标: 19
- 存在字段/覆盖问题的数据源: 15
- 全量 API 目录行数: 224
- 原始层已采集 API: 152
- 原始层已建表但需补参数/权限/API 支持的 API: 39
- 尚未分类治理结论的 API: 0
- 尚未实现 PG/ETL 的 API: 191

## 已登记数据源

| 表 | Tushare API | 分类 | 同步 mode | 监控 | 日期列 | 行数 | 起始 | 最新 | 覆盖 | 历史 | 问题 |
|---|---|---|---|---|---|---:|---|---|---|---|---|
| daily_kline | daily | 行情 | daily_kline | 是 | trade_date | 8604379 | 1990-12-19 | 2026-07-01 | covered | 10y_ok |  |
| weekly_kline | weekly | 行情 | weekly | 是 | trade_date | 2302914 | 2016-01-08 | 2026-06-26 | covered | 10y_ok |  |
| monthly_kline | monthly | 行情 | monthly | 是 | trade_date | 545575 | 2016-01-29 | 2026-06-30 | covered | 10y_ok |  |
| stk_mins | stk_mins | 行情 | stk_mins | 是 | trade_time | 19940041 | 2026-03-02 09:30:00 | 2026-07-02 10:55:00 | covered | short_history |  |
| adj_factor | adj_factor | 行情 | adj_factor | 是 | trade_date | 11241671 | 2016-01-04 | 2026-06-30 | covered | 10y_ok |  |
| daily_basic | daily_basic | 行情 | daily_basic | 是 | trade_date | 10738866 | 2016-01-04 | 2026-06-30 | covered | 10y_ok | etl_cols_not_in_pg: turnover_rate_f,pe_ttm,ps,ps_ttm,dv_ratio |
| stk_limit | stk_limit | 行情 | stk_limit | 是 | trade_date | 13159670 | 2016-01-04 | 2026-07-02 | covered | 10y_ok |  |
| index_daily | index_daily | 行情 | index_daily | 是 | trade_date | 10389 | 2021-01-04 | 2026-06-30 | covered | short_history |  |
| sw_daily | sw_daily | 行情 | sw_daily | 是 | trade_date | 491073 | 2016-07-06 | 2026-06-30 | covered | short_history |  |
| rt_sw_k | rt_sw_k | 行情 | rt_sw_k | 是 | trade_date | 1800 | 2026-06-18 | 2026-07-02 | covered | short_history |  |
| moneyflow | moneyflow | 资金 | moneyflow | 是 | trade_date | 14284230 | 2007-01-04 | 2026-06-30 | covered | 10y_ok | etl_cols_not_in_pg: net_mf_vol |
| moneyflow_hsgt | moneyflow_hsgt | 资金 | moneyflow_hsgt | 是 | trade_date | 2646 | 2014-11-17 | 2026-06-26 | covered | 10y_ok |  |
| hk_holdings | hk_hold | 资金 | hk_hold | 是 | trade_date | 5693213 | 2016-06-29 | 2026-06-30 | covered | 10y_ok | etl_cols_not_in_pg: hold_vol |
| margin_detail | margin_detail | 资金 | margin | 是 | trade_date | 6582916 | 2010-03-31 | 2026-06-30 | covered | 10y_ok | etl_cols_not_in_pg: rqyl |
| margin_summary | margin_summary | 资金 | margin_summary | 是 | trade_date | 3943 | 2010-03-31 | 2026-06-30 | covered | 10y_ok | api_not_in_reference<br>etl_cols_not_in_pg: rzmre,rzche,rqmcl,rzrqye |
| block_trade_data | block_trade | 资金 | block_trade | 是 | trade_date | 320429 | 2006-01-24 | 2026-06-29 | covered | 10y_ok | etl_cols_not_in_pg: vol,buyer,seller |
| stk_auction_o | stk_auction_o | 特色 | stk_auction_o | 否 |  | 2933638 | 2021-01-04 | 2026-07-02 | covered | short_history |  |
| stk_factor_pro | stk_factor_pro | 特色 | stk_factor_pro | 是 | trade_date | 213034 | 20260526 | 20260624 | covered | short_history |  |
| broker_recommend | broker_recommend | 特色 | broker_recommend | 是 | month | 17347 | 202003 | 202606 | covered | unknown | etl_cols_not_in_pg: name |
| cyq_chips | cyq_chips | 特色 | cyq_chips | 是 | trade_date | 108475 | 2026-06-18 | 2026-06-30 | covered | short_history |  |
| top_list | top_list | 特色 | top_list | 是 | trade_date | 137745 | 2016-06-23 | 2026-06-30 | covered | 10y_ok |  |
| top_inst | top_inst | 特色 | top_inst | 是 | trade_date | 2013964 | 2016-06-23 | 2026-06-30 | covered | 10y_ok |  |
| limit_list_d | limit_list_d | 特色 | limit_list | 是 | trade_date | 150081 | 20191128 | 20260630 | covered | short_history |  |
| financial_indicator | fina_indicator | 财务 | fina_indicator | 是 | end_date | 33207 | 2006-12-31 | 2026-03-31 | covered | 10y_ok |  |
| financial_income | income | 财务 | income | 是 | end_date | 17583 | 2006-12-31 | 2026-03-31 | covered | 10y_ok | etl_cols_not_in_pg: basic_eps,revenue,oper_cost,sell_expense,admin_expense,fin_expense,n_income,n_income_attr_p,operate_profit,total_profit |
| financial_balance | balancesheet | 财务 | balancesheet | 是 | end_date | 17694 | 2006-12-31 | 2026-03-31 | covered | 10y_ok | etl_cols_not_in_pg: total_cur_assets,total_liab,total_cur_liab,total_hldr_eqy_exc_min_int,total_share,cap_rese,undistr_porfit |
| financial_cashflow | cashflow | 财务 | cashflow | 是 | end_date | 17611 | 2006-12-31 | 2026-03-31 | covered | 10y_ok | etl_cols_not_in_pg: n_cashflow_act,n_cashflow_inv_act,n_cashflow_fin_act,c_fr_sale_sg,net_profit |
| forecast_data | forecast | 财务 | forecast | 是 | end_date | 27251 | 2021-03-31 | 2027-12-31 | covered | short_history | etl_cols_not_in_pg: ann_date,net_profit_min,net_profit_max,change_reason |
| dividend_data | dividend | 财务 | dividend | 是 | ex_date | 35148 | 2016-07-08 | 2026-07-09 | covered | 10y_ok | etl_cols_not_in_pg: end_date,ann_date,stk_div,stk_bo_rate,record_date |
| stocks | stock_basic | 基础 | stocks | 是 | updated_at | 5651 | 2026-06-04 01:43:40 | 2026-07-02 02:34:17 | covered | short_history |  |
| index_basic | index_basic | 基础 | index_basic | 否 |  | 1103 |  |  | covered | no_data | etl_cols_not_in_pg: ts_code,category,base_date,base_point,list_date |
| ths_member | ths_member | 基础 |  | 否 |  | 241136 |  |  | pg_only | no_data | missing_etl_target |
| stock_news_tushare | news | 舆情 | stock_news | 是 | pub_time | 110624 | 2016-06-29 00:00:00 | 2026-06-08 00:00:00 | covered | short_history |  |
| research_reports_tushare | research_report | 舆情 | research_report | 是 | pub_date | 116266 | 2017-01-09 | 2026-06-24 | covered | short_history | etl_cols_not_in_pg: trade_date,report_type,author,name |

## 全量 Tushare API 覆盖矩阵

> 每个 Tushare API 都在本表中。未实现不等于遗漏，而是必须继续补治理结论。

| API | 标题 | 分类 | 项目状态 | 治理状态 | PG表 | 同步mode | 监控 | 日期列 | 行数 | 起始 | 最新 | 历史 | 问题 | 文档 |
|---|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|
| adj_factor | 复权因子 | 股票数据,行情数据 | covered | active | adj_factor | adj_factor | 是 | trade_date | 11241671 | 2016-01-04 | 2026-06-30 | 10y_ok |  | https://tushare.pro/wctapi/documents/28.md |
| anns_d | 上市公司公告 | 大模型语料专题数据 | raw_landed | collected | ts_raw_anns_d | raw_bulk_ingest | 否 |  | 56410 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/176.md |
| bak_basic | 股票历史列表 | 股票数据,基础数据 | raw_landed | collected | ts_raw_bak_basic | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/262.md |
| bak_daily | 备用行情 | 股票数据,行情数据 | raw_landed | collected | ts_raw_bak_daily | raw_bulk_ingest | 否 |  | 70000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/255.md |
| balancesheet | 资产负债表 | 股票数据,财务数据 | covered | needs_field_decision | financial_balance | balancesheet | 是 | end_date | 17694 | 2006-12-31 | 2026-03-31 | 10y_ok | etl_cols_not_in_pg: total_cur_assets,total_liab,total_cur_liab,total_hldr_eqy_exc_min_int,total_share,cap_rese,undistr_porfit | https://tushare.pro/wctapi/documents/36.md |
| bc_bestotcqt | 柜台流通式债券最优报价 | 债券专题 | raw_landed | collected | ts_raw_bc_bestotcqt | raw_bulk_ingest | 否 |  | 4940 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/323.md |
| bc_otcqt | 柜台流通式债券报价 | 债券专题 | raw_landed | collected | ts_raw_bc_otcqt | raw_bulk_ingest | 否 |  | 6000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/322.md |
| block_trade | 大宗交易 | 股票数据,参考数据 | covered | needs_field_decision | block_trade_data | block_trade | 是 | trade_date | 320429 | 2006-01-24 | 2026-06-29 | 10y_ok | etl_cols_not_in_pg: vol,buyer,seller | https://tushare.pro/wctapi/documents/161.md |
| bo_cinema | 影院日度票房 | 行业经济,TMT行业 | raw_table_created | unsupported_api | ts_raw_bo_cinema | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/116.md |
| bo_daily | 电影日度票房 | 行业经济,TMT行业 | raw_table_created | unsupported_api | ts_raw_bo_daily | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/115.md |
| bo_monthly | 电影月度票房 | 行业经济,TMT行业 | raw_table_created | unsupported_api | ts_raw_bo_monthly | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/113.md |
| bo_weekly | 电影周度票房 | 行业经济,TMT行业 | raw_table_created | unsupported_api | ts_raw_bo_weekly | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/114.md |
| bond_blk | 大宗交易 | 债券专题 | raw_landed | collected | ts_raw_bond_blk | raw_bulk_ingest | 否 |  | 10735 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/271.md |
| bond_blk_detail | 大宗交易明细 | 债券专题 | raw_landed | collected | ts_raw_bond_blk_detail | raw_bulk_ingest | 否 |  | 10972 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/272.md |
| broker_recommend | 券商月度金股 | 股票数据,特色数据 | covered | needs_field_decision | broker_recommend | broker_recommend | 是 | month | 17347 | 202003 | 202606 | unknown | etl_cols_not_in_pg: name | https://tushare.pro/wctapi/documents/267.md |
| bse_mapping | 北交所新旧代码对照 | 股票数据,基础数据 | raw_landed | collected | ts_raw_bse_mapping | raw_bulk_ingest | 否 |  | 248 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/375.md |
| cashflow | 现金流量表 | 股票数据,财务数据 | covered | needs_field_decision | financial_cashflow | cashflow | 是 | end_date | 17611 | 2006-12-31 | 2026-03-31 | 10y_ok | etl_cols_not_in_pg: n_cashflow_act,n_cashflow_inv_act,n_cashflow_fin_act,c_fr_sale_sg,net_profit | https://tushare.pro/wctapi/documents/44.md |
| cb_basic | 可转债基础信息 | 债券专题 | raw_landed | collected | ts_raw_cb_basic | raw_bulk_ingest | 否 |  | 1141 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/185.md |
| cb_call | 可转债赎回信息 | 债券专题 | raw_landed | collected | ts_raw_cb_call | raw_bulk_ingest | 否 |  | 2883 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/269.md |
| cb_daily | 可转债行情 | 债券专题 | raw_landed | collected | ts_raw_cb_daily | raw_bulk_ingest | 否 |  | 22000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/187.md |
| cb_factor_pro | 可转债技术面因子(专业版) | 债券专题 | raw_landed | collected | ts_raw_cb_factor_pro | raw_bulk_ingest | 否 |  | 1112 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/392.md |
| cb_issue | 可转债发行 | 债券专题 | raw_landed | collected | ts_raw_cb_issue | raw_bulk_ingest | 否 |  | 991 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/186.md |
| cb_price_chg | 可转债转股价变动 | 债券专题 | raw_table_created | requires_params | ts_raw_cb_price_chg | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/246.md |
| cb_rate | 可转债票面利率 | 债券专题 | raw_landed | collected | ts_raw_cb_rate | raw_bulk_ingest | 否 |  | 482 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/305.md |
| cb_share | 可转债转股结果 | 债券专题 | raw_landed | collected | ts_raw_cb_share | raw_bulk_ingest | 否 |  | 18743 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/247.md |
| ccass_hold | 中央结算系统持股统计 | 股票数据,特色数据 | raw_landed | collected | ts_raw_ccass_hold | raw_bulk_ingest | 否 |  | 34994 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/295.md |
| ccass_hold_detail | 中央结算系统持股明细 | 股票数据,特色数据 | raw_landed | collected | ts_raw_ccass_hold_detail | raw_bulk_ingest | 否 |  | 35000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/274.md |
| cctv_news | 新闻联播文字稿 | 大模型语料专题数据 | raw_landed | collected | ts_raw_cctv_news | raw_bulk_ingest | 否 |  | 100 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/154.md |
| ci_daily | 中信行业指数日行情 | 指数专题 | raw_landed | collected | ts_raw_ci_daily | raw_bulk_ingest | 否 |  | 44000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/308.md |
| ci_index_member | 中信行业成分 | 指数专题 | raw_landed | collected | ts_raw_ci_index_member | raw_bulk_ingest | 否 |  | 5000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/373.md |
| cn_cpi | 居民消费价格指数(CPI) | 宏观经济,国内宏观,价格指数 | raw_landed | collected | ts_raw_cn_cpi | raw_bulk_ingest | 否 |  | 509 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/228.md |
| cn_gdp | 国内生产总值(GDP) | 宏观经济,国内宏观,国民经济 | raw_landed | collected | ts_raw_cn_gdp | raw_bulk_ingest | 否 |  | 176 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/227.md |
| cn_m | 货币供应量(月) | 宏观经济,国内宏观,金融,货币供应量 | raw_landed | collected | ts_raw_cn_m | raw_bulk_ingest | 否 |  | 580 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/242.md |
| cn_pmi | 采购经理指数(PMI) | 宏观经济,国内宏观,景气度 | raw_landed | collected | ts_raw_cn_pmi | raw_bulk_ingest | 否 |  | 257 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/325.md |
| cn_ppi | 工业生产者出厂价格指数(PPI) | 宏观经济,国内宏观,价格指数 | raw_landed | collected | ts_raw_cn_ppi | raw_bulk_ingest | 否 |  | 416 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/245.md |
| cyq_chips | 每日筹码分布 | 股票数据,特色数据 | covered | needs_history_decision | cyq_chips | cyq_chips | 是 | trade_date | 108475 | 2026-06-18 | 2026-06-30 | short_history |  | https://tushare.pro/wctapi/documents/294.md |
| cyq_perf | 每日筹码及胜率 | 股票数据,特色数据 | raw_landed | collected | ts_raw_cyq_perf | raw_bulk_ingest | 否 |  | 22956 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/293.md |
| daily | 历史日线 | 股票数据,行情数据 | covered | active | daily_kline | daily_kline | 是 | trade_date | 8604379 | 1990-12-19 | 2026-07-01 | 10y_ok |  | https://tushare.pro/wctapi/documents/27.md |
| daily_basic | 每日指标 | 股票数据,行情数据 | covered | needs_field_decision | daily_basic | daily_basic | 是 | trade_date | 10738866 | 2016-01-04 | 2026-06-30 | 10y_ok | etl_cols_not_in_pg: turnover_rate_f,pe_ttm,ps,ps_ttm,dv_ratio | https://tushare.pro/wctapi/documents/32.md |
| daily_info | 沪深市场每日交易统计 | 指数专题 | raw_landed | collected | ts_raw_daily_info | raw_bulk_ingest | 否 |  | 36224 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/215.md |
| dc_daily | 东财概念和行业指数行情 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_dc_daily | raw_bulk_ingest | 否 |  | 14000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/382.md |
| dc_hot | 东方财富App热榜 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_dc_hot | raw_bulk_ingest | 否 |  | 2000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/321.md |
| dc_index | 东方财富概念板块 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_dc_index | raw_bulk_ingest | 否 |  | 15000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/362.md |
| dc_member | 东方财富概念成分 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_dc_member | raw_bulk_ingest | 否 |  | 24000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/363.md |
| disclosure_date | 财报披露日期表 | 股票数据,财务数据 | raw_landed | collected | ts_raw_disclosure_date | raw_bulk_ingest | 否 |  | 49892 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/162.md |
| dividend | 分红送股数据 | 股票数据,财务数据 | covered | needs_field_decision | dividend_data | dividend | 是 | ex_date | 35148 | 2016-07-08 | 2026-07-09 | 10y_ok | etl_cols_not_in_pg: end_date,ann_date,stk_div,stk_bo_rate,record_date | https://tushare.pro/wctapi/documents/103.md |
| eco_cal | 全球财经事件 | 债券专题 | raw_landed | collected | ts_raw_eco_cal | raw_bulk_ingest | 否 |  | 1053 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/233.md |
| etf_basic | ETF基本信息 | ETF专题 | raw_landed | collected | ts_raw_etf_basic | raw_bulk_ingest | 否 |  | 3342 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/385.md |
| etf_index | ETF基准指数 | ETF专题 | raw_landed | collected | ts_raw_etf_index | raw_bulk_ingest | 否 |  | 1495 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/386.md |
| etf_share_size | ETF份额规模 | ETF专题 | raw_landed | collected | ts_raw_etf_share_size | raw_bulk_ingest | 否 |  | 55000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/408.md |
| express | 业绩快报 | 股票数据,财务数据 | raw_landed | collected | ts_raw_express | raw_bulk_ingest | 否 |  | 17478 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/46.md |
| film_record | 全国电影剧本备案数据 | 行业经济,TMT行业 | raw_table_created | unsupported_api | ts_raw_film_record | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/156.md |
| fina_audit | 财务审计意见 | 股票数据,财务数据 | raw_table_created | requires_params | ts_raw_fina_audit | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/80.md |
| fina_indicator | 财务指标数据 | 股票数据,财务数据 | covered | active | financial_indicator | fina_indicator | 是 | end_date | 33207 | 2006-12-31 | 2026-03-31 | 10y_ok |  | https://tushare.pro/wctapi/documents/79.md |
| fina_mainbz | 主营业务构成 | 股票数据,财务数据 | raw_table_created | requires_params | ts_raw_fina_mainbz | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/81.md |
| forecast | 业绩预告 | 股票数据,财务数据 | covered | needs_field_decision | forecast_data | forecast | 是 | end_date | 27251 | 2021-03-31 | 2027-12-31 | short_history | etl_cols_not_in_pg: ann_date,net_profit_min,net_profit_max,change_reason | https://tushare.pro/wctapi/documents/45.md |
| ft_limit | 期货合约涨跌停价格 | 期货数据 | raw_landed | collected | ts_raw_ft_limit | raw_bulk_ingest | 否 |  | 44000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/368.md |
| ft_mins | 历史分钟行情 | 期货数据 | raw_table_created | requires_params | ts_raw_ft_mins | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/313.md |
| fund_adj | ETF复权因子 | ETF专题 | raw_landed | collected | ts_raw_fund_adj | raw_bulk_ingest | 否 |  | 22000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/199.md |
| fund_basic | 基金列表 | 公募基金 | raw_landed | collected | ts_raw_fund_basic | raw_bulk_ingest | 否 |  | 15000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/19.md |
| fund_company | 基金管理人 | 公募基金 | raw_landed | collected | ts_raw_fund_company | raw_bulk_ingest | 否 |  | 203 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/118.md |
| fund_daily | ETF日线行情 | ETF专题 | raw_landed | collected | ts_raw_fund_daily | raw_bulk_ingest | 否 |  | 5905 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/127.md |
| fund_div | 基金分红 | 公募基金 | raw_landed | collected | ts_raw_fund_div | raw_bulk_ingest | 否 |  | 117 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/120.md |
| fund_factor_pro | 基金技术面因子(专业版) | 公募基金 | raw_landed | collected | ts_raw_fund_factor_pro | raw_bulk_ingest | 否 |  | 5361 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/359.md |
| fund_manager | 基金经理 | 公募基金 | raw_landed | collected | ts_raw_fund_manager | raw_bulk_ingest | 否 |  | 5000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/208.md |
| fund_nav | 基金净值 | 公募基金 | raw_table_created | requires_params | ts_raw_fund_nav | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/119.md |
| fund_portfolio | 基金持仓 | 公募基金 | raw_landed | collected | ts_raw_fund_portfolio | raw_bulk_ingest | 否 |  | 60 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/121.md |
| fund_sales_ratio | 各渠道公募基金销售保有规模占比 | 财富管理,基金销售行业数据 | raw_table_created | unsupported_api | ts_raw_fund_sales_ratio | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/265.md |
| fund_sales_vol | 销售机构公募基金销售保有规模 | 财富管理,基金销售行业数据 | raw_table_created | unsupported_api | ts_raw_fund_sales_vol | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/266.md |
| fund_share | 基金规模 | 公募基金 | raw_landed | collected | ts_raw_fund_share | raw_bulk_ingest | 否 |  | 22000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/207.md |
| fut_basic | 合约信息 | 期货数据 | raw_landed | collected | ts_raw_fut_basic | raw_bulk_ingest | 否 |  | 10000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/135.md |
| fut_daily | 日线行情 | 期货数据 | raw_landed | collected | ts_raw_fut_daily | raw_bulk_ingest | 否 |  | 22000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/138.md |
| fut_holding | 每日持仓排名 | 期货数据 | raw_landed | collected | ts_raw_fut_holding | raw_bulk_ingest | 否 |  | 20000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/139.md |
| fut_mapping | 期货主力与连续合约 | 期货数据 | raw_landed | collected | ts_raw_fut_mapping | raw_bulk_ingest | 否 |  | 55000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/189.md |
| fut_settle | 每日结算参数 | 期货数据 | raw_landed | collected | ts_raw_fut_settle | raw_bulk_ingest | 否 |  | 1490 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/141.md |
| fut_weekly_detail | 期货主要品种交易周报 | 期货数据 | raw_landed | collected | ts_raw_fut_weekly_detail | raw_bulk_ingest | 否 |  | 4000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/216.md |
| fut_weekly_monthly | 期货周月线行情(每日更新) | 期货数据 | raw_table_created | requires_params | ts_raw_fut_weekly_monthly | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/337.md |
| fut_wsr | 仓单日报 | 期货数据 | raw_landed | collected | ts_raw_fut_wsr | raw_bulk_ingest | 否 |  | 4394 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/140.md |
| fx_daily | 外汇日线行情 | 外汇数据 | raw_landed | collected | ts_raw_fx_daily | raw_bulk_ingest | 否 |  | 44000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/179.md |
| fx_obasic | 外汇基础信息(海外) | 外汇数据 | raw_landed | collected | ts_raw_fx_obasic | raw_bulk_ingest | 否 |  | 69 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/178.md |
| ggt_daily | 港股通每日成交统计 | 股票数据,行情数据 | raw_landed | collected | ts_raw_ggt_daily | raw_bulk_ingest | 否 |  | 2277 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/196.md |
| ggt_monthly | 港股通每月成交统计 | 股票数据,行情数据 | raw_table_created | unsupported_api | ts_raw_ggt_monthly | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/197.md |
| ggt_top10 | 港股通十大成交股 | 股票数据,行情数据 | raw_landed | collected | ts_raw_ggt_top10 | raw_bulk_ingest | 否 |  | 80 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/49.md |
| gz_index | 广州民间借贷利率 | 宏观经济,国内宏观,利率数据 | raw_landed | collected | ts_raw_gz_index | raw_bulk_ingest | 否 |  | 218 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/174.md |
| hibor | Hibor利率 | 宏观经济,国内宏观,利率数据 | raw_landed | collected | ts_raw_hibor | raw_bulk_ingest | 否 |  | 980 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/153.md |
| hk_adjfactor | 港股复权因子 | 港股数据 | raw_landed | collected | ts_raw_hk_adjfactor | raw_bulk_ingest | 否 |  | 66000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/401.md |
| hk_balancesheet | 港股资产负债表 | 港股数据 | raw_table_created | requires_params | ts_raw_hk_balancesheet | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/390.md |
| hk_basic | 港股基础信息 | 港股数据 | raw_landed | collected | ts_raw_hk_basic | raw_bulk_ingest | 否 |  | 2751 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/191.md |
| hk_cashflow | 港股现金流量表 | 港股数据 | raw_table_created | requires_params | ts_raw_hk_cashflow | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/391.md |
| hk_daily | 港股日线行情 | 港股数据 | raw_landed | collected | ts_raw_hk_daily | raw_bulk_ingest | 否 |  | 88000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/192.md |
| hk_daily_adj | 港股复权行情 | 港股数据 | raw_landed | collected | ts_raw_hk_daily_adj | raw_bulk_ingest | 否 |  | 70484 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/339.md |
| hk_fina_indicator | 港股财务指标数据 | 港股数据 | raw_table_created | requires_params | ts_raw_hk_fina_indicator | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/388.md |
| hk_hold | 沪深股通持股明细 | 股票数据,特色数据 | covered | needs_field_decision | hk_holdings | hk_hold | 是 | trade_date | 5693213 | 2016-06-29 | 2026-06-30 | 10y_ok | etl_cols_not_in_pg: hold_vol | https://tushare.pro/wctapi/documents/188.md |
| hk_income | 港股利润表 | 港股数据 | raw_table_created | requires_params | ts_raw_hk_income | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/389.md |
| hk_mins | 港股分钟行情 | 港股数据 | raw_table_created | requires_params | ts_raw_hk_mins | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/304.md |
| hk_tradecal | 港股交易日历 | 港股数据 | raw_landed | collected | ts_raw_hk_tradecal | raw_bulk_ingest | 否 |  | 3651 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/250.md |
| hm_detail | 游资交易每日明细 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_hm_detail | raw_bulk_ingest | 否 |  | 10000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/312.md |
| hm_list | 市场游资最全名录 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_hm_list | raw_bulk_ingest | 否 |  | 110 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/311.md |
| hsgt_top10 | 沪深股通十大成交股 | 股票数据,行情数据 | raw_landed | collected | ts_raw_hsgt_top10 | raw_bulk_ingest | 否 |  | 3300 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/48.md |
| idx_factor_pro | 指数技术面因子(专业版) | 指数专题 | raw_landed | collected | ts_raw_idx_factor_pro | raw_bulk_ingest | 否 |  | 15596 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/358.md |
| idx_mins | 指数历史分钟 | 指数专题 | raw_table_created | requires_params | ts_raw_idx_mins | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/419.md |
| income | 利润表 | 股票数据,财务数据 | covered | needs_field_decision | financial_income | income | 是 | end_date | 17583 | 2006-12-31 | 2026-03-31 | 10y_ok | etl_cols_not_in_pg: basic_eps,revenue,oper_cost,sell_expense,admin_expense,fin_expense,n_income,n_income_attr_p,operate_profit,total_profit | https://tushare.pro/wctapi/documents/33.md |
| index_basic | 指数基本信息 | 指数专题 | covered | needs_field_decision | index_basic | index_basic | 否 |  | 1103 |  |  | no_data | etl_cols_not_in_pg: ts_code,category,base_date,base_point,list_date | https://tushare.pro/wctapi/documents/94.md |
| index_classify | 申万行业分类 | 指数专题 | raw_landed | collected | ts_raw_index_classify | raw_bulk_ingest | 否 |  | 359 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/181.md |
| index_daily | 南华期货指数行情 | 期货数据 | covered | needs_history_decision | index_daily | index_daily | 是 | trade_date | 10389 | 2021-01-04 | 2026-06-30 | short_history |  | https://tushare.pro/wctapi/documents/155.md |
| index_dailybasic | 大盘指数每日指标 | 指数专题 | raw_landed | collected | ts_raw_index_dailybasic | raw_bulk_ingest | 否 |  | 60 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/128.md |
| index_global | 国际主要指数 | 指数专题 | raw_landed | collected | ts_raw_index_global | raw_bulk_ingest | 否 |  | 41040 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/211.md |
| index_member_all | 申万行业成分(分级) | 指数专题 | raw_landed | collected | ts_raw_index_member_all | raw_bulk_ingest | 否 |  | 3000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/335.md |
| index_monthly | 指数月线行情 | 指数专题 | raw_landed | collected | ts_raw_index_monthly | raw_bulk_ingest | 否 |  | 5000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/172.md |
| index_weekly | 指数周线行情 | 指数专题 | raw_landed | collected | ts_raw_index_weekly | raw_bulk_ingest | 否 |  | 3003 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/171.md |
| index_weight | 指数成分和权重 | 指数专题 | raw_landed | collected | ts_raw_index_weight | raw_bulk_ingest | 否 |  | 35000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/96.md |
| irm_qa_sh | 上证e互动问答 | 大模型语料专题数据 | raw_landed | collected | ts_raw_irm_qa_sh | raw_bulk_ingest | 否 |  | 11986 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/366.md |
| irm_qa_sz | 深证易互动问答 | 大模型语料专题数据 | raw_landed | collected | ts_raw_irm_qa_sz | raw_bulk_ingest | 否 |  | 13196 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/367.md |
| kpl_concept_cons | 题材成分(开盘啦) | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_kpl_concept_cons | raw_bulk_ingest | 否 |  | 3000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/351.md |
| kpl_list | 榜单数据(开盘啦) | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_kpl_list | raw_bulk_ingest | 否 |  | 72000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/347.md |
| libor | Libor利率 | 宏观经济,国内宏观,利率数据 | raw_landed | collected | ts_raw_libor | raw_bulk_ingest | 否 |  | 1002 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/152.md |
| limit_cpt_list | 涨停最强板块统计 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_limit_cpt_list | raw_bulk_ingest | 否 |  | 6700 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/357.md |
| limit_list_d | 涨跌停和炸板数据 | 股票数据,打板专题数据 | covered | needs_history_decision | limit_list_d | limit_list | 是 | trade_date | 150081 | 20191128 | 20260630 | short_history |  | https://tushare.pro/wctapi/documents/298.md |
| limit_list_ths | 同花顺涨跌停榜单 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_limit_list_ths | raw_bulk_ingest | 否 |  | 16904 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/355.md |
| limit_step | 涨停股票连板天梯 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_limit_step | raw_bulk_ingest | 否 |  | 6470 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/356.md |
| major_news | 新闻通讯(长篇) | 大模型语料专题数据 | raw_landed | collected | ts_raw_major_news | raw_bulk_ingest | 否 |  | 8733 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/195.md |
| margin | 融资融券交易汇总 | 股票数据,两融及转融通 | raw_landed | collected | ts_raw_margin | raw_bulk_ingest | 否 |  | 5666 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/58.md |
| margin_detail | 融资融券交易明细 | 股票数据,两融及转融通 | covered | needs_field_decision | margin_detail | margin | 是 | trade_date | 6582916 | 2010-03-31 | 2026-06-30 | 10y_ok | etl_cols_not_in_pg: rqyl | https://tushare.pro/wctapi/documents/59.md |
| margin_secs | 融资融券标的(盘前) | 股票数据,两融及转融通 | raw_landed | collected | ts_raw_margin_secs | raw_bulk_ingest | 否 |  | 66000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/326.md |
| moneyflow | 个股资金流向 | 股票数据,资金流向数据 | covered | needs_field_decision | moneyflow | moneyflow | 是 | trade_date | 14284230 | 2007-01-04 | 2026-06-30 | 10y_ok | etl_cols_not_in_pg: net_mf_vol | https://tushare.pro/wctapi/documents/170.md |
| moneyflow_cnt_ths | 板块资金流向(THS) | 股票数据,资金流向数据 | raw_landed | collected | ts_raw_moneyflow_cnt_ths | raw_bulk_ingest | 否 |  | 12000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/371.md |
| moneyflow_dc | 个股资金流向(DC) | 股票数据,资金流向数据 | raw_landed | collected | ts_raw_moneyflow_dc | raw_bulk_ingest | 否 |  | 24000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/349.md |
| moneyflow_hsgt | 沪深港通资金流向 | 股票数据,资金流向数据 | covered | active | moneyflow_hsgt | moneyflow_hsgt | 是 | trade_date | 2646 | 2014-11-17 | 2026-06-26 | 10y_ok |  | https://tushare.pro/wctapi/documents/47.md |
| moneyflow_ind_dc | 板块资金流向(DC) | 股票数据,资金流向数据 | raw_landed | collected | ts_raw_moneyflow_ind_dc | raw_bulk_ingest | 否 |  | 20000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/344.md |
| moneyflow_ind_ths | 行业资金流向(THS) | 股票数据,资金流向数据 | raw_landed | collected | ts_raw_moneyflow_ind_ths | raw_bulk_ingest | 否 |  | 15000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/343.md |
| moneyflow_mkt_dc | 大盘资金流向(DC) | 股票数据,资金流向数据 | raw_landed | collected | ts_raw_moneyflow_mkt_dc | raw_bulk_ingest | 否 |  | 775 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/345.md |
| moneyflow_ths | 个股资金流向(THS) | 股票数据,资金流向数据 | raw_landed | collected | ts_raw_moneyflow_ths | raw_bulk_ingest | 否 |  | 18870 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/348.md |
| monthly | 月线行情 | 股票数据,行情数据 | covered | active | monthly_kline | monthly | 是 | trade_date | 545575 | 2016-01-29 | 2026-06-30 | 10y_ok |  | https://tushare.pro/wctapi/documents/145.md |
| namechange | 股票曾用名 | 股票数据,基础数据 | raw_landed | collected | ts_raw_namechange | raw_bulk_ingest | 否 |  | 3854 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/100.md |
| new_share | IPO新股上市 | 股票数据,基础数据 | raw_landed | collected | ts_raw_new_share | raw_bulk_ingest | 否 |  | 2917 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/123.md |
| news | 新闻快讯(短讯) | 大模型语料专题数据 | covered | needs_history_decision | stock_news_tushare | stock_news | 是 | pub_time | 110624 | 2016-06-29 00:00:00 | 2026-06-08 00:00:00 | short_history |  | https://tushare.pro/wctapi/documents/143.md |
| npr | 国家政策库 | 大模型语料专题数据 | raw_landed | collected | ts_raw_npr | raw_bulk_ingest | 否 |  | 4607 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/406.md |
| opt_basic | 期权合约信息 | 期权数据 | raw_landed | collected | ts_raw_opt_basic | raw_bulk_ingest | 否 |  | 12000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/158.md |
| opt_daily | 期权日线行情 | 期权数据 | raw_landed | collected | ts_raw_opt_daily | raw_bulk_ingest | 否 |  | 160182 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/159.md |
| opt_mins | 期权分钟行情 | 期权数据 | raw_table_created | requires_params | ts_raw_opt_mins | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/341.md |
| pledge_detail | 股权质押明细数据 | 股票数据,参考数据 | raw_landed | collected | ts_raw_pledge_detail | raw_bulk_ingest | 否 |  | 12793 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/111.md |
| pledge_stat | 股权质押统计数据 | 股票数据,参考数据 | raw_landed | collected | ts_raw_pledge_stat | raw_bulk_ingest | 否 |  | 9000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/110.md |
| pro_bar | 通用行情接口 | 股票数据,行情数据 | raw_table_created | unsupported_api | ts_raw_pro_bar | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/109.md |
| repo_daily | 债券回购日行情 | 债券专题 | raw_landed | collected | ts_raw_repo_daily | raw_bulk_ingest | 否 |  | 22000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/256.md |
| report_rc | 券商盈利预测数据 | 股票数据,特色数据 | raw_landed | collected | ts_raw_report_rc | raw_bulk_ingest | 否 |  | 55000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/292.md |
| repurchase | 股票回购 | 股票数据,参考数据 | raw_landed | collected | ts_raw_repurchase | raw_bulk_ingest | 否 |  | 15034 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/124.md |
| research_report | 券商研究报告 | 大模型语料专题数据 | covered | needs_field_decision | research_reports_tushare | research_report | 是 | pub_date | 116266 | 2017-01-09 | 2026-06-24 | short_history | etl_cols_not_in_pg: trade_date,report_type,author,name | https://tushare.pro/wctapi/documents/415.md |
| rt_etf_k | ETF实时日线 | ETF专题 | raw_table_created | requires_params | ts_raw_rt_etf_k | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/400.md |
| rt_fut_min | 实时分钟行情 | 期货数据 | raw_table_created | requires_params | ts_raw_rt_fut_min | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/340.md |
| rt_hk_k | 港股实时日线 | 港股数据 | raw_table_created | requires_params | ts_raw_rt_hk_k | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/383.md |
| rt_idx_k | 指数实时日线 | 指数专题 | raw_table_created | requires_params | ts_raw_rt_idx_k | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/403.md |
| rt_idx_min | 指数实时分钟 | 指数专题 | raw_table_created | requires_params | ts_raw_rt_idx_min | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/420.md |
| rt_k | 实时日线 | 股票数据,行情数据 | raw_table_created | requires_params | ts_raw_rt_k | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/372.md |
| rt_min | 实时分钟 | 股票数据,行情数据 | raw_table_created | requires_params | ts_raw_rt_min | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/374.md |
| rt_sw_k | 申万实时行情 | 指数专题 | covered | needs_history_decision | rt_sw_k | rt_sw_k | 是 | trade_date | 1800 | 2026-06-18 | 2026-07-02 | short_history |  | https://tushare.pro/wctapi/documents/417.md |
| sf_month | 社融增量(月度) | 宏观经济,国内宏观,金融,社会融资 | raw_landed | collected | ts_raw_sf_month | raw_bulk_ingest | 否 |  | 293 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/310.md |
| sge_basic | 上海黄金基础信息 | 现货数据 | raw_landed | collected | ts_raw_sge_basic | raw_bulk_ingest | 否 |  | 13 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/284.md |
| sge_daily | 上海黄金现货日行情 | 现货数据 | raw_landed | collected | ts_raw_sge_daily | raw_bulk_ingest | 否 |  | 21308 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/285.md |
| share_float | 限售股解禁 | 股票数据,参考数据 | raw_landed | collected | ts_raw_share_float | raw_bulk_ingest | 否 |  | 64948 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/160.md |
| shibor | Shibor利率 | 宏观经济,国内宏观,利率数据 | raw_landed | collected | ts_raw_shibor | raw_bulk_ingest | 否 |  | 2470 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/149.md |
| shibor_lpr | LPR贷款基础利率 | 宏观经济,国内宏观,利率数据 | raw_landed | collected | ts_raw_shibor_lpr | raw_bulk_ingest | 否 |  | 856 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/151.md |
| shibor_quote | Shibor报价数据 | 宏观经济,国内宏观,利率数据 | raw_landed | collected | ts_raw_shibor_quote | raw_bulk_ingest | 否 |  | 32669 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/150.md |
| slb_len | 转融资交易汇总 | 股票数据,两融及转融通 | raw_landed | collected | ts_raw_slb_len | raw_bulk_ingest | 否 |  | 2201 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/331.md |
| slb_len_mm | 做市借券交易汇总(停) | 股票数据,两融及转融通 | raw_landed | collected | ts_raw_slb_len_mm | raw_bulk_ingest | 否 |  | 12664 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/334.md |
| slb_sec | 转融券交易汇总(停) | 股票数据,两融及转融通 | raw_landed | collected | ts_raw_slb_sec | raw_bulk_ingest | 否 |  | 45000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/332.md |
| slb_sec_detail | 转融券交易明细(停) | 股票数据,两融及转融通 | raw_landed | collected | ts_raw_slb_sec_detail | raw_bulk_ingest | 否 |  | 36000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/333.md |
| st | ST风险警示板股票 | 股票数据,基础数据 | raw_landed | collected | ts_raw_st | raw_bulk_ingest | 否 |  | 1000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/423.md |
| stk_account | 股票开户数据(停) | 股票数据,参考数据 | raw_landed | collected | ts_raw_stk_account | raw_bulk_ingest | 否 |  | 132 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/164.md |
| stk_account_old | 股票开户数据(旧) | 股票数据,参考数据 | raw_table_created | unsupported_api | ts_raw_stk_account_old | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/165.md |
| stk_ah_comparison | AH股比价 | 股票数据,特色数据 | raw_landed | collected | ts_raw_stk_ah_comparison | raw_bulk_ingest | 否 |  | 2000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/399.md |
| stk_auction | 开盘竞价成交(当日) | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_stk_auction | raw_bulk_ingest | 否 |  | 16000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/369.md |
| stk_auction_c | 股票收盘集合竞价数据 | 股票数据,特色数据 | raw_landed | collected | ts_raw_stk_auction_c | raw_bulk_ingest | 否 |  | 110000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/354.md |
| stk_auction_o | 股票开盘集合竞价数据 | 股票数据,特色数据 | covered | needs_history_decision | stk_auction_o | stk_auction_o | 否 |  | 2933638 | 2021-01-04 | 2026-07-02 | short_history |  | https://tushare.pro/wctapi/documents/353.md |
| stk_factor_pro | 股票技术面因子(专业版) | 股票数据,特色数据 | covered | needs_history_decision | stk_factor_pro | stk_factor_pro | 是 | trade_date | 213034 | 20260526 | 20260624 | short_history |  | https://tushare.pro/wctapi/documents/328.md |
| stk_holdernumber | 股东人数 | 股票数据,参考数据 | raw_landed | collected | ts_raw_stk_holdernumber | raw_bulk_ingest | 否 |  | 60500 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/166.md |
| stk_holdertrade | 股东增减持 | 股票数据,参考数据 | raw_landed | collected | ts_raw_stk_holdertrade | raw_bulk_ingest | 否 |  | 31742 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/175.md |
| stk_limit | 每日涨跌停价格 | 股票数据,行情数据 | covered | active | stk_limit | stk_limit | 是 | trade_date | 13159670 | 2016-01-04 | 2026-07-02 | 10y_ok |  | https://tushare.pro/wctapi/documents/183.md |
| stk_managers | 上市公司管理层 | 股票数据,基础数据 | raw_landed | collected | ts_raw_stk_managers | raw_bulk_ingest | 否 |  | 32000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/193.md |
| stk_mins | 历史分钟 | 股票数据,行情数据 | covered | needs_history_decision | stk_mins | stk_mins | 是 | trade_time | 19940041 | 2026-03-02 09:30:00 | 2026-07-02 10:55:00 | short_history |  | https://tushare.pro/wctapi/documents/370.md |
| stk_nineturn | 神奇九转指标 | 股票数据,特色数据 | raw_landed | collected | ts_raw_stk_nineturn | raw_bulk_ingest | 否 |  | 110000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/364.md |
| stk_premarket | 每日股本(盘前) | 股票数据,基础数据 | raw_landed | collected | ts_raw_stk_premarket | raw_bulk_ingest | 否 |  | 24000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/329.md |
| stk_rewards | 管理层薪酬和持股 | 股票数据,基础数据 | raw_table_created | requires_params | ts_raw_stk_rewards | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/194.md |
| stk_surv | 机构调研数据 | 股票数据,特色数据 | raw_landed | collected | ts_raw_stk_surv | raw_bulk_ingest | 否 |  | 2400 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/275.md |
| stk_week_month_adj | 周月线复权行情(每日更新) | 股票数据,行情数据 | raw_table_created | requires_params | ts_raw_stk_week_month_adj | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/365.md |
| stk_weekly_monthly | 周月线行情(每日更新) | 股票数据,行情数据 | raw_table_created | requires_params | ts_raw_stk_weekly_monthly | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/336.md |
| stock_basic | 股票列表 | 股票数据,基础数据 | covered | needs_history_decision | stocks | stocks | 是 | updated_at | 5651 | 2026-06-04 01:43:40 | 2026-07-02 02:34:17 | short_history |  | https://tushare.pro/wctapi/documents/25.md |
| stock_company | 上市公司基本信息 | 股票数据,基础数据 | raw_landed | collected | ts_raw_stock_company | raw_bulk_ingest | 否 |  | 6294 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/112.md |
| stock_hsgt | 沪深港通股票列表 | 股票数据,基础数据 | raw_landed | collected | ts_raw_stock_hsgt | raw_bulk_ingest | 否 |  | 22000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/398.md |
| stock_st | ST股票列表 | 股票数据,基础数据 | raw_landed | collected | ts_raw_stock_st | raw_bulk_ingest | 否 |  | 11000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/397.md |
| suspend_d | 每日停复牌信息 | 股票数据,行情数据 | raw_landed | collected | ts_raw_suspend_d | raw_bulk_ingest | 否 |  | 49837 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/214.md |
| sw_daily | 申万行业指数日行情 | 指数专题 | covered | needs_history_decision | sw_daily | sw_daily | 是 | trade_date | 491073 | 2016-07-06 | 2026-06-30 | short_history |  | https://tushare.pro/wctapi/documents/327.md |
| sz_daily_info | 深圳市场每日交易情况 | 指数专题 | raw_landed | collected | ts_raw_sz_daily_info | raw_bulk_ingest | 否 |  | 21592 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/268.md |
| tdx_daily | 通达信板块行情 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_tdx_daily | raw_bulk_ingest | 否 |  | 6000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/378.md |
| tdx_index | 通达信板块信息 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_tdx_index | raw_bulk_ingest | 否 |  | 1000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/376.md |
| tdx_member | 通达信板块成分 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_tdx_member | raw_bulk_ingest | 否 |  | 6000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/377.md |
| teleplay_record | 全国电视剧备案公示数据 | 行业经济,TMT行业 | raw_table_created | unsupported_api | ts_raw_teleplay_record | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/180.md |
| ths_daily | 同花顺概念和行业指数行情 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_ths_daily | raw_bulk_ingest | 否 |  | 33000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/260.md |
| ths_hot | 同花顺App热榜数 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_ths_hot | raw_bulk_ingest | 否 |  | 2000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/320.md |
| ths_index | 同花顺行业概念板块 | 股票数据,打板专题数据 | raw_landed | collected | ts_raw_ths_index | raw_bulk_ingest | 否 |  | 1725 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/259.md |
| ths_member | 同花顺行业概念成分 | 股票数据,打板专题数据 | pg_only | needs_mapping | ths_member |  | 否 |  | 241136 |  |  | no_data | missing_etl_target | https://tushare.pro/wctapi/documents/261.md |
| tmt_twincome | 台湾电子产业月营收 | 行业经济,TMT行业 | raw_table_created | unsupported_api | ts_raw_tmt_twincome | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/88.md |
| tmt_twincomedetail | 台湾电子产业月营收明细 | 行业经济,TMT行业 | raw_table_created | unsupported_api | ts_raw_tmt_twincomedetail | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | unsupported_api | https://tushare.pro/wctapi/documents/87.md |
| top10_floatholders | 前十大流通股东 | 股票数据,参考数据 | raw_landed | collected | ts_raw_top10_floatholders | raw_bulk_ingest | 否 |  | 66000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/62.md |
| top10_holders | 前十大股东 | 股票数据,参考数据 | raw_landed | collected | ts_raw_top10_holders | raw_bulk_ingest | 否 |  | 66000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/61.md |
| top_inst | 龙虎榜机构交易单 | 股票数据,打板专题数据 | covered | active | top_inst | top_inst | 是 | trade_date | 2013964 | 2016-06-23 | 2026-06-30 | 10y_ok |  | https://tushare.pro/wctapi/documents/107.md |
| top_list | 龙虎榜每日统计单 | 股票数据,打板专题数据 | covered | active | top_list | top_list | 是 | trade_date | 137745 | 2016-06-23 | 2026-06-30 | 10y_ok |  | https://tushare.pro/wctapi/documents/106.md |
| trade_cal | 交易日历 | 股票数据,基础数据 | raw_landed | collected | ts_raw_trade_cal | raw_bulk_ingest | 否 |  | 3651 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/26.md |
| us_adjfactor | 美股复权因子 | 美股数据 | raw_landed | collected | ts_raw_us_adjfactor | raw_bulk_ingest | 否 |  | 165000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/402.md |
| us_balancesheet | 美股资产负债表 | 美股数据 | raw_table_created | requires_params | ts_raw_us_balancesheet | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/395.md |
| us_basic | 美股基础信息 | 美股数据 | raw_landed | collected | ts_raw_us_basic | raw_bulk_ingest | 否 |  | 5999 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/252.md |
| us_cashflow | 美股现金流量表 | 美股数据 | raw_table_created | requires_params | ts_raw_us_cashflow | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/396.md |
| us_daily | 美股日线行情 | 美股数据 | raw_landed | collected | ts_raw_us_daily | raw_bulk_ingest | 否 |  | 87762 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/254.md |
| us_daily_adj | 美股复权行情 | 美股数据 | raw_landed | collected | ts_raw_us_daily_adj | raw_bulk_ingest | 否 |  | 87998 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/338.md |
| us_fina_indicator | 美股财务指标数据 | 美股数据 | raw_landed | collected | ts_raw_us_fina_indicator | raw_bulk_ingest | 否 |  | 22000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/393.md |
| us_income | 美股利润表 | 美股数据 | raw_table_created | requires_params | ts_raw_us_income | raw_bulk_ingest | 否 |  | 0 |  |  | raw_unverified | requires_params | https://tushare.pro/wctapi/documents/394.md |
| us_tbr | 短期国债利率 | 宏观经济,国际宏观,美国利率 | raw_landed | collected | ts_raw_us_tbr | raw_bulk_ingest | 否 |  | 2495 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/221.md |
| us_tltr | 国债长期利率 | 宏观经济,国际宏观,美国利率 | raw_landed | collected | ts_raw_us_tltr | raw_bulk_ingest | 否 |  | 2494 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/222.md |
| us_tradecal | 美股交易日历 | 美股数据 | raw_landed | collected | ts_raw_us_tradecal | raw_bulk_ingest | 否 |  | 3651 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/253.md |
| us_trltr | 国债长期利率平均值 | 宏观经济,国际宏观,美国利率 | raw_landed | collected | ts_raw_us_trltr | raw_bulk_ingest | 否 |  | 2494 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/223.md |
| us_trycr | 国债实际收益率曲线利率 | 宏观经济,国际宏观,美国利率 | raw_landed | collected | ts_raw_us_trycr | raw_bulk_ingest | 否 |  | 2493 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/220.md |
| us_tycr | 国债收益率曲线利率 | 宏观经济,国际宏观,美国利率 | raw_landed | collected | ts_raw_us_tycr | raw_bulk_ingest | 否 |  | 2494 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/219.md |
| weekly | 周线行情 | 股票数据,行情数据 | covered | active | weekly_kline | weekly | 是 | trade_date | 2302914 | 2016-01-08 | 2026-06-26 | 10y_ok |  | https://tushare.pro/wctapi/documents/144.md |
| wz_index | 温州民间借贷利率 | 宏观经济,国内宏观,利率数据 | raw_landed | collected | ts_raw_wz_index | raw_bulk_ingest | 否 |  | 1499 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/173.md |
| yc_cb | 国债收益率曲线 | 债券专题 | raw_landed | collected | ts_raw_yc_cb | raw_bulk_ingest | 否 |  | 22000 |  |  | raw_unverified |  | https://tushare.pro/wctapi/documents/201.md |
