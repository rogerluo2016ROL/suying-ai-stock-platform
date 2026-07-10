# Tushare 批量接入结果

> 生成时间: 2026-07-10T19:01:22

## 汇总

- collected: 92
- failed: 79
- requires_params: 12
- unsupported_api: 8

## 明细

| API | 标题 | 分类 | 表 | 状态 | 拉取行数 | 入库行数 | 字段数 | 错误 |
|---|---|---|---|---|---:|---:|---:|---|
| anns_d | 上市公司公告 | 大模型语料专题数据 | ts_raw_anns_d | collected | 126000 | 66378 | 5 |  |
| bak_basic | 股票历史列表 | 股票数据,基础数据 | ts_raw_bak_basic | collected | 147000 | 7000 | 24 |  |
| bak_daily | 备用行情 | 股票数据,行情数据 | ts_raw_bak_daily | collected | 70000 | 7000 | 31 |  |
| bc_bestotcqt | 柜台流通式债券最优报价 | 债券专题 | ts_raw_bc_bestotcqt | collected | 6000 | 0 | 2 |  |
| bc_otcqt | 柜台流通式债券报价 | 债券专题 | ts_raw_bc_otcqt | collected | 42000 | 2000 | 18 |  |
| bo_cinema | 影院日度票房 | 行业经济,TMT行业 | ts_raw_bo_cinema | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| bo_daily | 电影日度票房 | 行业经济,TMT行业 | ts_raw_bo_daily | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| bo_monthly | 电影月度票房 | 行业经济,TMT行业 | ts_raw_bo_monthly | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| bo_weekly | 电影周度票房 | 行业经济,TMT行业 | ts_raw_bo_weekly | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| bond_blk | 大宗交易 | 债券专题 | ts_raw_bond_blk | collected | 17419 | 6684 | 6 |  |
| bond_blk_detail | 大宗交易明细 | 债券专题 | ts_raw_bond_blk_detail | collected | 11000 | 28 | 8 |  |
| bse_mapping | 北交所新旧代码对照 | 股票数据,基础数据 | ts_raw_bse_mapping | collected | 5208 | 0 | 4 |  |
| cb_basic | 可转债基础信息 | 债券专题 | ts_raw_cb_basic | collected | 24024 | 221 | 27 |  |
| cb_call | 可转债赎回信息 | 债券专题 | ts_raw_cb_call | collected | 3014 | 140 | 11 |  |
| cb_daily | 可转债行情 | 债券专题 | ts_raw_cb_daily | collected | 42000 | 22000 | 11 |  |
| cb_factor_pro | 可转债技术面因子(专业版) | 债券专题 | ts_raw_cb_factor_pro | collected | 1251 | 139 | 89 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| cb_issue | 可转债发行 | 债券专题 | ts_raw_cb_issue | collected | 1078 | 91 | 23 |  |
| cb_price_chg | 可转债转股价变动 | 债券专题 | ts_raw_cb_price_chg | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| cb_rate | 可转债票面利率 | 债券专题 | ts_raw_cb_rate | collected | 42000 | 2 | 1 |  |
| cb_share | 可转债转股结果 | 债券专题 | ts_raw_cb_share | collected | 25801 | 7562 | 15 |  |
| ccass_hold | 中央结算系统持股统计 | 股票数据,特色数据 | ts_raw_ccass_hold | collected | 35000 | 6079 | 6 |  |
| ccass_hold_detail | 中央结算系统持股明细 | 股票数据,特色数据 | ts_raw_ccass_hold_detail | collected | 35000 | 0 | 7 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| cctv_news | 新闻联播文字稿 | 大模型语料专题数据 | ts_raw_cctv_news | collected | 2100 | 100 | 3 |  |
| ci_daily | 中信行业指数日行情 | 指数专题 | ts_raw_ci_daily | collected | 68000 | 27496 | 11 |  |
| ci_index_member | 中信行业成分 | 指数专题 | ts_raw_ci_index_member | collected | 105000 | 0 | 11 |  |
| cn_cpi | 居民消费价格指数(CPI) | 宏观经济,国内宏观,价格指数 | ts_raw_cn_cpi | collected | 10689 | 0 | 13 |  |
| cn_gdp | 国内生产总值(GDP) | 宏观经济,国内宏观,国民经济 | ts_raw_cn_gdp | collected | 3717 | 1 | 9 |  |
| cn_m | 货币供应量(月) | 宏观经济,国内宏观,金融,货币供应量 | ts_raw_cn_m | collected | 12201 | 1 | 10 |  |
| cn_pmi | 采购经理指数(PMI) | 宏观经济,国内宏观,景气度 | ts_raw_cn_pmi | collected | 5397 | 0 | 65 |  |
| cn_ppi | 工业生产者出厂价格指数(PPI) | 宏观经济,国内宏观,价格指数 | ts_raw_cn_ppi | collected | 8736 | 0 | 31 |  |
| cyq_perf | 每日筹码及胜率 | 股票数据,特色数据 | ts_raw_cyq_perf | collected | 22980 | 1085 | 11 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| daily_info | 沪深市场每日交易统计 | 指数专题 | ts_raw_daily_info | collected | 72814 | 36590 | 14 |  |
| dc_daily | 东财概念和行业指数行情 | 股票数据,打板专题数据 | ts_raw_dc_daily | collected | 22000 | 10000 | 13 |  |
| dc_hot | 东方财富App热榜 | 股票数据,打板专题数据 | ts_raw_dc_hot | collected | 42000 | 2000 | 10 |  |
| dc_index | 东方财富概念板块 | 股票数据,打板专题数据 | ts_raw_dc_index | collected | 15000 | 5000 | 13 |  |
| dc_member | 东方财富概念成分 | 股票数据,打板专题数据 | ts_raw_dc_member | collected | 24000 | 4449 | 4 |  |
| disclosure_date | 财报披露日期表 | 股票数据,财务数据 | ts_raw_disclosure_date | collected | 73253 | 23361 | 5 |  |
| eco_cal | 全球财经事件 | 债券专题 | ts_raw_eco_cal | collected | 2100 | 1200 | 8 |  |
| etf_basic | ETF基本信息 | ETF专题 | ts_raw_etf_basic | collected | 37149 | 1769 | 14 |  |
| etf_index | ETF基准指数 | ETF专题 | ts_raw_etf_index | collected | 11760 | 140 | 8 |  |
| etf_share_size | ETF份额规模 | ETF专题 | ts_raw_etf_share_size | collected | 84019 | 34149 | 6 |  |
| express | 业绩快报 | 股票数据,财务数据 | ts_raw_express | collected | 28444 | 10966 | 15 |  |
| film_record | 全国电影剧本备案数据 | 行业经济,TMT行业 | ts_raw_film_record | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| fina_audit | 财务审计意见 | 股票数据,财务数据 | ts_raw_fina_audit | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| fina_mainbz | 主营业务构成 | 股票数据,财务数据 | ts_raw_fina_mainbz | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| ft_limit | 期货合约涨跌停价格 | 期货数据 | ts_raw_ft_limit | collected | 84000 | 44000 | 8 |  |
| ft_mins | 历史分钟行情 | 期货数据 | ts_raw_ft_mins | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| fund_adj | ETF复权因子 | ETF专题 | ts_raw_fund_adj | collected | 54600 | 34600 | 3 |  |
| fund_basic | 基金列表 | 公募基金 | ts_raw_fund_basic | collected | 315000 | 812 | 25 |  |
| fund_company | 基金管理人 | 公募基金 | ts_raw_fund_company | collected | 4263 | 5 | 17 |  |
| fund_daily | ETF日线行情 | ETF专题 | ts_raw_fund_daily | collected | 9815 | 3910 | 11 | 参数校验失败, ts_code和trade_date至少填写一个 |
| fund_div | 基金分红 | 公募基金 | ts_raw_fund_div | collected | 238 | 99 | 16 | 参数校验失败, ts_code,ex_date,pay_data,ann_date必选其一 |
| fund_factor_pro | 基金技术面因子(专业版) | 公募基金 | ts_raw_fund_factor_pro | collected | 8243 | 2882 | 90 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| fund_manager | 基金经理 | 公募基金 | ts_raw_fund_manager | collected | 105000 | 16 | 10 |  |
| fund_nav | 基金净值 | 公募基金 | ts_raw_fund_nav | requires_params | 0 | 0 | 0 | 参数校验失败, ts_code和nav_date至少填写一个 |
| fund_portfolio | 基金持仓 | 公募基金 | ts_raw_fund_portfolio | collected | 110 | 54 | 8 | 参数校验失败, ts_code,ann_date,period至少输入一个参数 |
| fund_sales_ratio | 各渠道公募基金销售保有规模占比 | 财富管理,基金销售行业数据 | ts_raw_fund_sales_ratio | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| fund_sales_vol | 销售机构公募基金销售保有规模 | 财富管理,基金销售行业数据 | ts_raw_fund_sales_vol | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| fund_share | 基金规模 | 公募基金 | ts_raw_fund_share | collected | 40826 | 20832 | 5 |  |
| fut_basic | 合约信息 | 期货数据 | ts_raw_fut_basic | collected | 210000 | 0 | 15 |  |
| fut_daily | 日线行情 | 期货数据 | ts_raw_fut_daily | collected | 42000 | 22000 | 15 |  |
| fut_holding | 每日持仓排名 | 期货数据 | ts_raw_fut_holding | collected | 45294 | 25294 | 9 | 参数校验失败, trade_date,symbol参数不能都为空 |
| fut_mapping | 期货主力与连续合约 | 期货数据 | ts_raw_fut_mapping | collected | 103010 | 49425 | 3 |  |
| fut_settle | 每日结算参数 | 期货数据 | ts_raw_fut_settle | collected | 5150 | 4234 | 10 | 参数校验失败, trade_date,ts_code不能都为空 |
| fut_weekly_detail | 期货主要品种交易周报 | 期货数据 | ts_raw_fut_weekly_detail | collected | 84000 | 0 | 17 |  |
| fut_weekly_monthly | 期货周月线行情(每日更新) | 期货数据 | ts_raw_fut_weekly_monthly | requires_params | 0 | 0 | 0 | 必填参数, freq |
| fut_wsr | 仓单日报 | 期货数据 | ts_raw_fut_wsr | collected | 5897 | 1269 | 8 | 参数校验失败, trade_date,symbol参数不能都为空 |
| fx_daily | 外汇日线行情 | 外汇数据 | ts_raw_fx_daily | collected | 84000 | 42075 | 11 |  |
| fx_obasic | 外汇基础信息(海外) | 外汇数据 | ts_raw_fx_obasic | collected | 1449 | 0 | 12 |  |
| ggt_daily | 港股通每日成交统计 | 股票数据,行情数据 | ts_raw_ggt_daily | collected | 2655 | 378 | 5 |  |
| ggt_monthly | 港股通每月成交统计 | 股票数据,行情数据 | ts_raw_ggt_monthly | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| ggt_top10 | 港股通十大成交股 | 股票数据,行情数据 | ts_raw_ggt_top10 | collected | 110 | 30 | 17 | 参数校验失败,  |
| gz_index | 广州民间借贷利率 | 宏观经济,国内宏观,利率数据 | ts_raw_gz_index | collected | 1181 | 963 | 7 |  |
| hibor | Hibor利率 | 宏观经济,国内宏观,利率数据 | ts_raw_hibor | collected | 3186 | 2206 | 9 |  |
| hk_adjfactor | 港股复权因子 | 港股数据 | ts_raw_hk_adjfactor | collected | 126000 | 66183 | 4 |  |
| hk_balancesheet | 港股资产负债表 | 港股数据 | ts_raw_hk_balancesheet | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| hk_basic | 港股基础信息 | 港股数据 | ts_raw_hk_basic | collected | 57771 | 0 | 12 |  |
| hk_cashflow | 港股现金流量表 | 港股数据 | ts_raw_hk_cashflow | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| hk_daily | 港股日线行情 | 港股数据 | ts_raw_hk_daily | collected | 168000 | 88000 | 11 |  |
| hk_daily_adj | 港股复权行情 | 港股数据 | ts_raw_hk_daily_adj | collected | 168000 | 79333 | 18 |  |
| hk_fina_indicator | 港股财务指标数据 | 港股数据 | ts_raw_hk_fina_indicator | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| hk_income | 港股利润表 | 港股数据 | ts_raw_hk_income | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| hk_mins | 港股分钟行情 | 港股数据 | ts_raw_hk_mins | requires_params | 0 | 0 | 0 | 必填参数, freq |
| hk_tradecal | 港股交易日历 | 港股数据 | ts_raw_hk_tradecal | collected | 7301 | 3650 | 3 |  |
| hm_detail | 游资交易每日明细 | 股票数据,打板专题数据 | ts_raw_hm_detail | collected | 10000 | 2000 | 8 |  |
| hm_list | 市场游资最全名录 | 股票数据,打板专题数据 | ts_raw_hm_list | collected | 2310 | 0 | 3 |  |
| hsgt_top10 | 沪深股通十大成交股 | 股票数据,行情数据 | ts_raw_hsgt_top10 | collected | 3900 | 740 | 11 |  |
| idx_factor_pro | 指数技术面因子(专业版) | 指数专题 | ts_raw_idx_factor_pro | collected | 26945 | 11349 | 89 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| idx_mins | 指数历史分钟 | 指数专题 | ts_raw_idx_mins | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| index_classify | 申万行业分类 | 指数专题 | ts_raw_index_classify | collected | 7539 | 0 | 7 |  |
| index_dailybasic | 大盘指数每日指标 | 指数专题 | ts_raw_index_dailybasic | collected | 147 | 87 | 12 | 参数校验失败, trade_date,ts_code参数至少输入一个 |
| index_global | 国际主要指数 | 指数专题 | ts_raw_index_global | collected | 80913 | 80867 | 11 |  |
| index_member_all | 申万行业成分(分级) | 指数专题 | ts_raw_index_member_all | collected | 63000 | 0 | 11 |  |
| index_monthly | 指数月线行情 | 指数专题 | ts_raw_index_monthly | collected | 9808 | 4808 | 11 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| index_weekly | 指数周线行情 | 指数专题 | ts_raw_index_weekly | collected | 7167 | 4164 | 11 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| index_weight | 指数成分和权重 | 指数专题 | ts_raw_index_weight | collected | 88521 | 82147 | 4 | 参数校验失败,  |
| irm_qa_sh | 上证e互动问答 | 大模型语料专题数据 | ts_raw_irm_qa_sh | collected | 12000 | 2998 | 6 |  |
| irm_qa_sz | 深证易互动问答 | 大模型语料专题数据 | ts_raw_irm_qa_sz | collected | 13244 | 3029 | 7 |  |
| kpl_concept_cons | 题材成分(开盘啦) | 股票数据,打板专题数据 | ts_raw_kpl_concept_cons | collected | 63000 | 3000 | 7 |  |
| kpl_list | 榜单数据(开盘啦) | 股票数据,打板专题数据 | ts_raw_kpl_list | collected | 72000 | 929 | 24 |  |
| libor | Libor利率 | 宏观经济,国内宏观,利率数据 | ts_raw_libor | collected | 3554 | 2552 | 9 |  |
| limit_cpt_list | 涨停最强板块统计 | 股票数据,打板专题数据 | ts_raw_limit_cpt_list | collected | 6700 | 6398 | 9 |  |
| limit_list_ths | 同花顺涨跌停榜单 | 股票数据,打板专题数据 | ts_raw_limit_list_ths | collected | 16904 | 16329 | 18 |  |
| limit_step | 涨停股票连板天梯 | 股票数据,打板专题数据 | ts_raw_limit_step | collected | 6470 | 6066 | 4 |  |
| major_news | 新闻通讯(长篇) | 大模型语料专题数据 | ts_raw_major_news | collected | 16800 | 9096 | 4 |  |
| margin | 融资融券交易汇总 | 股票数据,两融及转融通 | ts_raw_margin | collected | 8730 | 3064 | 9 |  |
| margin_secs | 融资融券标的(盘前) | 股票数据,两融及转融通 | ts_raw_margin_secs | collected | 102000 | 42000 | 4 |  |
| moneyflow_cnt_ths | 板块资金流向(THS) | 股票数据,资金流向数据 | ts_raw_moneyflow_cnt_ths | collected | 12000 | 3056 | 12 |  |
| moneyflow_dc | 个股资金流向(DC) | 股票数据,资金流向数据 | ts_raw_moneyflow_dc | collected | 24000 | 6007 | 15 |  |
| moneyflow_ind_dc | 板块资金流向(DC) | 股票数据,资金流向数据 | ts_raw_moneyflow_ind_dc | collected | 20000 | 5000 | 18 |  |
| moneyflow_ind_ths | 行业资金流向(THS) | 股票数据,资金流向数据 | ts_raw_moneyflow_ind_ths | collected | 15000 | 720 | 12 |  |
| moneyflow_mkt_dc | 大盘资金流向(DC) | 股票数据,资金流向数据 | ts_raw_moneyflow_mkt_dc | collected | 416 | 0 | 15 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/moneyflow_mkt_dc (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', p |
| moneyflow_ths | 个股资金流向(THS) | 股票数据,资金流向数据 | ts_raw_moneyflow_ths | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/moneyflow_ths (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port |
| namechange | 股票曾用名 | 股票数据,基础数据 | ts_raw_namechange | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/namechange (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80 |
| new_share | IPO新股上市 | 股票数据,基础数据 | ts_raw_new_share | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/new_share (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| npr | 国家政策库 | 大模型语料专题数据 | ts_raw_npr | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/npr (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): Fail |
| opt_basic | 期权合约信息 | 期权数据 | ts_raw_opt_basic | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/opt_basic (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| opt_daily | 期权日线行情 | 期权数据 | ts_raw_opt_daily | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/opt_daily (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| opt_mins | 期权分钟行情 | 期权数据 | ts_raw_opt_mins | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/opt_mins (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| pledge_detail | 股权质押明细数据 | 股票数据,参考数据 | ts_raw_pledge_detail | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/pledge_detail (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port |
| pledge_stat | 股权质押统计数据 | 股票数据,参考数据 | ts_raw_pledge_stat | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/pledge_stat (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=8 |
| pro_bar | 通用行情接口 | 股票数据,行情数据 | ts_raw_pro_bar | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/pro_bar (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80):  |
| repo_daily | 债券回购日行情 | 债券专题 | ts_raw_repo_daily | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/repo_daily (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80 |
| report_rc | 券商盈利预测数据 | 股票数据,特色数据 | ts_raw_report_rc | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/report_rc (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| repurchase | 股票回购 | 股票数据,参考数据 | ts_raw_repurchase | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/repurchase (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80 |
| rt_etf_k | ETF实时日线 | ETF专题 | ts_raw_rt_etf_k | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/rt_etf_k (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| rt_fut_min | 实时分钟行情 | 期货数据 | ts_raw_rt_fut_min | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/rt_fut_min (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80 |
| rt_hk_k | 港股实时日线 | 港股数据 | ts_raw_rt_hk_k | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/rt_hk_k (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80):  |
| rt_idx_k | 指数实时日线 | 指数专题 | ts_raw_rt_idx_k | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/rt_idx_k (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| rt_idx_min | 指数实时分钟 | 指数专题 | ts_raw_rt_idx_min | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/rt_idx_min (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80 |
| rt_k | 实时日线 | 股票数据,行情数据 | ts_raw_rt_k | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/rt_k (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): Fai |
| rt_min | 实时分钟 | 股票数据,行情数据 | ts_raw_rt_min | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/rt_min (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): F |
| sf_month | 社融增量(月度) | 宏观经济,国内宏观,金融,社会融资 | ts_raw_sf_month | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/sf_month (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| sge_basic | 上海黄金基础信息 | 现货数据 | ts_raw_sge_basic | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/sge_basic (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| sge_daily | 上海黄金现货日行情 | 现货数据 | ts_raw_sge_daily | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/sge_daily (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| share_float | 限售股解禁 | 股票数据,参考数据 | ts_raw_share_float | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/share_float (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=8 |
| shibor | Shibor利率 | 宏观经济,国内宏观,利率数据 | ts_raw_shibor | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/shibor (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): F |
| shibor_lpr | LPR贷款基础利率 | 宏观经济,国内宏观,利率数据 | ts_raw_shibor_lpr | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/shibor_lpr (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80 |
| shibor_quote | Shibor报价数据 | 宏观经济,国内宏观,利率数据 | ts_raw_shibor_quote | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/shibor_quote (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port= |
| slb_len | 转融资交易汇总 | 股票数据,两融及转融通 | ts_raw_slb_len | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/slb_len (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80):  |
| slb_len_mm | 做市借券交易汇总(停) | 股票数据,两融及转融通 | ts_raw_slb_len_mm | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/slb_len_mm (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80 |
| slb_sec | 转融券交易汇总(停) | 股票数据,两融及转融通 | ts_raw_slb_sec | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/slb_sec (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80):  |
| slb_sec_detail | 转融券交易明细(停) | 股票数据,两融及转融通 | ts_raw_slb_sec_detail | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/slb_sec_detail (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', por |
| st | ST风险警示板股票 | 股票数据,基础数据 | ts_raw_st | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/st (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): Faile |
| stk_account | 股票开户数据(停) | 股票数据,参考数据 | ts_raw_stk_account | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_account (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=8 |
| stk_account_old | 股票开户数据(旧) | 股票数据,参考数据 | ts_raw_stk_account_old | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_account_old (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', po |
| stk_ah_comparison | AH股比价 | 股票数据,特色数据 | ts_raw_stk_ah_comparison | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_ah_comparison (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com',  |
| stk_auction | 开盘竞价成交(当日) | 股票数据,打板专题数据 | ts_raw_stk_auction | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_auction (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=8 |
| stk_auction_c | 股票收盘集合竞价数据 | 股票数据,特色数据 | ts_raw_stk_auction_c | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_auction_c (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port |
| stk_holdernumber | 股东人数 | 股票数据,参考数据 | ts_raw_stk_holdernumber | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_holdernumber (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', p |
| stk_holdertrade | 股东增减持 | 股票数据,参考数据 | ts_raw_stk_holdertrade | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_holdertrade (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', po |
| stk_managers | 上市公司管理层 | 股票数据,基础数据 | ts_raw_stk_managers | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_managers (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port= |
| stk_nineturn | 神奇九转指标 | 股票数据,特色数据 | ts_raw_stk_nineturn | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_nineturn (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port= |
| stk_premarket | 每日股本(盘前) | 股票数据,基础数据 | ts_raw_stk_premarket | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_premarket (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port |
| stk_rewards | 管理层薪酬和持股 | 股票数据,基础数据 | ts_raw_stk_rewards | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_rewards (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=8 |
| stk_surv | 机构调研数据 | 股票数据,特色数据 | ts_raw_stk_surv | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_surv (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| stk_week_month_adj | 周月线复权行情(每日更新) | 股票数据,行情数据 | ts_raw_stk_week_month_adj | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_week_month_adj (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', |
| stk_weekly_monthly | 周月线行情(每日更新) | 股票数据,行情数据 | ts_raw_stk_weekly_monthly | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stk_weekly_monthly (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', |
| stock_company | 上市公司基本信息 | 股票数据,基础数据 | ts_raw_stock_company | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stock_company (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port |
| stock_hsgt | 沪深港通股票列表 | 股票数据,基础数据 | ts_raw_stock_hsgt | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stock_hsgt (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80 |
| stock_st | ST股票列表 | 股票数据,基础数据 | ts_raw_stock_st | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/stock_st (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| suspend_d | 每日停复牌信息 | 股票数据,行情数据 | ts_raw_suspend_d | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/suspend_d (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| sz_daily_info | 深圳市场每日交易情况 | 指数专题 | ts_raw_sz_daily_info | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/sz_daily_info (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port |
| tdx_daily | 通达信板块行情 | 股票数据,打板专题数据 | ts_raw_tdx_daily | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/tdx_daily (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| tdx_index | 通达信板块信息 | 股票数据,打板专题数据 | ts_raw_tdx_index | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/tdx_index (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| tdx_member | 通达信板块成分 | 股票数据,打板专题数据 | ts_raw_tdx_member | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/tdx_member (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80 |
| teleplay_record | 全国电视剧备案公示数据 | 行业经济,TMT行业 | ts_raw_teleplay_record | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/teleplay_record (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', po |
| ths_daily | 同花顺概念和行业指数行情 | 股票数据,打板专题数据 | ts_raw_ths_daily | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/ths_daily (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| ths_hot | 同花顺App热榜数 | 股票数据,打板专题数据 | ts_raw_ths_hot | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/ths_hot (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80):  |
| ths_index | 同花顺行业概念板块 | 股票数据,打板专题数据 | ts_raw_ths_index | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/ths_index (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| tmt_twincome | 台湾电子产业月营收 | 行业经济,TMT行业 | ts_raw_tmt_twincome | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/tmt_twincome (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port= |
| tmt_twincomedetail | 台湾电子产业月营收明细 | 行业经济,TMT行业 | ts_raw_tmt_twincomedetail | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/tmt_twincomedetail (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', |
| top10_floatholders | 前十大流通股东 | 股票数据,参考数据 | ts_raw_top10_floatholders | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/top10_floatholders (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', |
| top10_holders | 前十大股东 | 股票数据,参考数据 | ts_raw_top10_holders | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/top10_holders (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port |
| trade_cal | 交易日历 | 股票数据,基础数据 | ts_raw_trade_cal | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/trade_cal (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| us_adjfactor | 美股复权因子 | 美股数据 | ts_raw_us_adjfactor | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_adjfactor (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port= |
| us_balancesheet | 美股资产负债表 | 美股数据 | ts_raw_us_balancesheet | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_balancesheet (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', po |
| us_basic | 美股基础信息 | 美股数据 | ts_raw_us_basic | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_basic (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| us_cashflow | 美股现金流量表 | 美股数据 | ts_raw_us_cashflow | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_cashflow (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=8 |
| us_daily | 美股日线行情 | 美股数据 | ts_raw_us_daily | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_daily (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| us_daily_adj | 美股复权行情 | 美股数据 | ts_raw_us_daily_adj | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_daily_adj (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port= |
| us_fina_indicator | 美股财务指标数据 | 美股数据 | ts_raw_us_fina_indicator | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_fina_indicator (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com',  |
| us_income | 美股利润表 | 美股数据 | ts_raw_us_income | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_income (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80) |
| us_tbr | 短期国债利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_tbr | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_tbr (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): F |
| us_tltr | 国债长期利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_tltr | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_tltr (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80):  |
| us_tradecal | 美股交易日历 | 美股数据 | ts_raw_us_tradecal | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_tradecal (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=8 |
| us_trltr | 国债长期利率平均值 | 宏观经济,国际宏观,美国利率 | ts_raw_us_trltr | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_trltr (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| us_trycr | 国债实际收益率曲线利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_trycr | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_trycr (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| us_tycr | 国债收益率曲线利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_tycr | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/us_tycr (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80):  |
| wz_index | 温州民间借贷利率 | 宏观经济,国内宏观,利率数据 | ts_raw_wz_index | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/wz_index (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): |
| yc_cb | 国债收益率曲线 | 债券专题 | ts_raw_yc_cb | failed | 0 | 0 | 0 | HTTPConnectionPool(host='api.waditu.com', port=80): Max retries exceeded with url: /dataapi/yc_cb (Caused by NameResolutionError("HTTPConnection(host='api.waditu.com', port=80): Fa |
