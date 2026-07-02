# Tushare 批量接入结果

> 生成时间: 2026-07-01T02:11:10

## 汇总

- collected: 152
- requires_params: 26
- unsupported_api: 13

## 明细

| API | 标题 | 分类 | 表 | 状态 | 拉取行数 | 入库行数 | 字段数 | 错误 |
|---|---|---|---|---|---:|---:|---:|---|
| anns_d | 上市公司公告 | 大模型语料专题数据 | ts_raw_anns_d | collected | 66000 | 56410 | 5 |  |
| bak_basic | 股票历史列表 | 股票数据,基础数据 | ts_raw_bak_basic | collected | 77000 | 0 | 24 |  |
| bak_daily | 备用行情 | 股票数据,行情数据 | ts_raw_bak_daily | collected | 70000 | 70000 | 31 |  |
| bc_bestotcqt | 柜台流通式债券最优报价 | 债券专题 | ts_raw_bc_bestotcqt | collected | 6000 | 4940 | 2 |  |
| bc_otcqt | 柜台流通式债券报价 | 债券专题 | ts_raw_bc_otcqt | collected | 20000 | 6000 | 18 |  |
| bo_cinema | 影院日度票房 | 行业经济,TMT行业 | ts_raw_bo_cinema | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| bo_daily | 电影日度票房 | 行业经济,TMT行业 | ts_raw_bo_daily | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| bo_monthly | 电影月度票房 | 行业经济,TMT行业 | ts_raw_bo_monthly | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| bo_weekly | 电影周度票房 | 行业经济,TMT行业 | ts_raw_bo_weekly | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| bond_blk | 大宗交易 | 债券专题 | ts_raw_bond_blk | collected | 10735 | 10735 | 6 |  |
| bond_blk_detail | 大宗交易明细 | 债券专题 | ts_raw_bond_blk_detail | collected | 10972 | 10972 | 8 |  |
| bse_mapping | 北交所新旧代码对照 | 股票数据,基础数据 | ts_raw_bse_mapping | collected | 2728 | 248 | 4 |  |
| cb_basic | 可转债基础信息 | 债券专题 | ts_raw_cb_basic | collected | 12551 | 1141 | 27 |  |
| cb_call | 可转债赎回信息 | 债券专题 | ts_raw_cb_call | collected | 2883 | 2883 | 11 |  |
| cb_daily | 可转债行情 | 债券专题 | ts_raw_cb_daily | collected | 22000 | 22000 | 11 |  |
| cb_factor_pro | 可转债技术面因子(专业版) | 债券专题 | ts_raw_cb_factor_pro | collected | 1112 | 1112 | 89 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| cb_issue | 可转债发行 | 债券专题 | ts_raw_cb_issue | collected | 991 | 991 | 23 |  |
| cb_price_chg | 可转债转股价变动 | 债券专题 | ts_raw_cb_price_chg | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| cb_rate | 可转债票面利率 | 债券专题 | ts_raw_cb_rate | collected | 22000 | 482 | 1 |  |
| cb_share | 可转债转股结果 | 债券专题 | ts_raw_cb_share | collected | 18743 | 18743 | 15 |  |
| ccass_hold | 中央结算系统持股统计 | 股票数据,特色数据 | ts_raw_ccass_hold | collected | 35000 | 34994 | 6 |  |
| ccass_hold_detail | 中央结算系统持股明细 | 股票数据,特色数据 | ts_raw_ccass_hold_detail | collected | 35000 | 35000 | 7 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| cctv_news | 新闻联播文字稿 | 大模型语料专题数据 | ts_raw_cctv_news | collected | 1100 | 100 | 3 |  |
| ci_daily | 中信行业指数日行情 | 指数专题 | ts_raw_ci_daily | collected | 44000 | 44000 | 11 |  |
| ci_index_member | 中信行业成分 | 指数专题 | ts_raw_ci_index_member | collected | 55000 | 5000 | 11 |  |
| cn_cpi | 居民消费价格指数(CPI) | 宏观经济,国内宏观,价格指数 | ts_raw_cn_cpi | collected | 5599 | 509 | 13 |  |
| cn_gdp | 国内生产总值(GDP) | 宏观经济,国内宏观,国民经济 | ts_raw_cn_gdp | collected | 1936 | 176 | 9 |  |
| cn_m | 货币供应量(月) | 宏观经济,国内宏观,金融,货币供应量 | ts_raw_cn_m | collected | 6380 | 580 | 10 |  |
| cn_pmi | 采购经理指数(PMI) | 宏观经济,国内宏观,景气度 | ts_raw_cn_pmi | collected | 2827 | 257 | 65 |  |
| cn_ppi | 工业生产者出厂价格指数(PPI) | 宏观经济,国内宏观,价格指数 | ts_raw_cn_ppi | collected | 4576 | 416 | 31 |  |
| cyq_perf | 每日筹码及胜率 | 股票数据,特色数据 | ts_raw_cyq_perf | collected | 22956 | 22956 | 11 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| daily_info | 沪深市场每日交易统计 | 指数专题 | ts_raw_daily_info | collected | 36224 | 36224 | 14 |  |
| dc_daily | 东财概念和行业指数行情 | 股票数据,打板专题数据 | ts_raw_dc_daily | collected | 14000 | 14000 | 13 |  |
| dc_hot | 东方财富App热榜 | 股票数据,打板专题数据 | ts_raw_dc_hot | collected | 22000 | 2000 | 10 |  |
| dc_index | 东方财富概念板块 | 股票数据,打板专题数据 | ts_raw_dc_index | collected | 15000 | 15000 | 13 |  |
| dc_member | 东方财富概念成分 | 股票数据,打板专题数据 | ts_raw_dc_member | collected | 24000 | 24000 | 4 |  |
| disclosure_date | 财报披露日期表 | 股票数据,财务数据 | ts_raw_disclosure_date | collected | 49892 | 49892 | 5 |  |
| eco_cal | 全球财经事件 | 债券专题 | ts_raw_eco_cal | collected | 1100 | 1053 | 8 |  |
| etf_basic | ETF基本信息 | ETF专题 | ts_raw_etf_basic | collected | 36762 | 3342 | 14 |  |
| etf_index | ETF基准指数 | ETF专题 | ts_raw_etf_index | collected | 16445 | 1495 | 8 |  |
| etf_share_size | ETF份额规模 | ETF专题 | ts_raw_etf_share_size | collected | 55000 | 55000 | 6 |  |
| express | 业绩快报 | 股票数据,财务数据 | ts_raw_express | collected | 17478 | 17478 | 15 |  |
| film_record | 全国电影剧本备案数据 | 行业经济,TMT行业 | ts_raw_film_record | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| fina_audit | 财务审计意见 | 股票数据,财务数据 | ts_raw_fina_audit | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| fina_mainbz | 主营业务构成 | 股票数据,财务数据 | ts_raw_fina_mainbz | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| ft_limit | 期货合约涨跌停价格 | 期货数据 | ts_raw_ft_limit | collected | 44000 | 44000 | 8 |  |
| ft_mins | 历史分钟行情 | 期货数据 | ts_raw_ft_mins | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| fund_adj | ETF复权因子 | ETF专题 | ts_raw_fund_adj | collected | 22000 | 22000 | 3 |  |
| fund_basic | 基金列表 | 公募基金 | ts_raw_fund_basic | collected | 165000 | 15000 | 25 |  |
| fund_company | 基金管理人 | 公募基金 | ts_raw_fund_company | collected | 2233 | 203 | 17 |  |
| fund_daily | ETF日线行情 | ETF专题 | ts_raw_fund_daily | collected | 5905 | 5905 | 11 | 参数校验失败, ts_code和trade_date至少填写一个 |
| fund_div | 基金分红 | 公募基金 | ts_raw_fund_div | collected | 140 | 117 | 16 | 参数校验失败, ts_code,ex_date,pay_data,ann_date必选其一 |
| fund_factor_pro | 基金技术面因子(专业版) | 公募基金 | ts_raw_fund_factor_pro | collected | 5361 | 5361 | 90 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| fund_manager | 基金经理 | 公募基金 | ts_raw_fund_manager | collected | 55000 | 5000 | 10 |  |
| fund_nav | 基金净值 | 公募基金 | ts_raw_fund_nav | requires_params | 0 | 0 | 0 | 参数校验失败, ts_code和nav_date至少填写一个 |
| fund_portfolio | 基金持仓 | 公募基金 | ts_raw_fund_portfolio | collected | 60 | 60 | 8 | 参数校验失败, ts_code,ann_date,period至少输入一个参数 |
| fund_sales_ratio | 各渠道公募基金销售保有规模占比 | 财富管理,基金销售行业数据 | ts_raw_fund_sales_ratio | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| fund_sales_vol | 销售机构公募基金销售保有规模 | 财富管理,基金销售行业数据 | ts_raw_fund_sales_vol | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| fund_share | 基金规模 | 公募基金 | ts_raw_fund_share | collected | 22000 | 22000 | 5 |  |
| fut_basic | 合约信息 | 期货数据 | ts_raw_fut_basic | collected | 110000 | 10000 | 15 |  |
| fut_daily | 日线行情 | 期货数据 | ts_raw_fut_daily | collected | 22000 | 22000 | 15 |  |
| fut_holding | 每日持仓排名 | 期货数据 | ts_raw_fut_holding | collected | 20000 | 20000 | 9 | 参数校验失败, trade_date,symbol参数不能都为空 |
| fut_mapping | 期货主力与连续合约 | 期货数据 | ts_raw_fut_mapping | collected | 55000 | 55000 | 3 |  |
| fut_settle | 每日结算参数 | 期货数据 | ts_raw_fut_settle | collected | 1490 | 1490 | 10 | 参数校验失败, trade_date,ts_code不能都为空 |
| fut_weekly_detail | 期货主要品种交易周报 | 期货数据 | ts_raw_fut_weekly_detail | collected | 44000 | 4000 | 17 |  |
| fut_weekly_monthly | 期货周月线行情(每日更新) | 期货数据 | ts_raw_fut_weekly_monthly | requires_params | 0 | 0 | 0 | 必填参数, freq |
| fut_wsr | 仓单日报 | 期货数据 | ts_raw_fut_wsr | collected | 4452 | 4394 | 8 | 参数校验失败, trade_date,symbol参数不能都为空 |
| fx_daily | 外汇日线行情 | 外汇数据 | ts_raw_fx_daily | collected | 44000 | 44000 | 11 |  |
| fx_obasic | 外汇基础信息(海外) | 外汇数据 | ts_raw_fx_obasic | collected | 759 | 69 | 12 |  |
| ggt_daily | 港股通每日成交统计 | 股票数据,行情数据 | ts_raw_ggt_daily | collected | 2277 | 2277 | 5 |  |
| ggt_monthly | 港股通每月成交统计 | 股票数据,行情数据 | ts_raw_ggt_monthly | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| ggt_top10 | 港股通十大成交股 | 股票数据,行情数据 | ts_raw_ggt_top10 | collected | 80 | 80 | 17 | 参数校验失败,  |
| gz_index | 广州民间借贷利率 | 宏观经济,国内宏观,利率数据 | ts_raw_gz_index | collected | 218 | 218 | 7 |  |
| hibor | Hibor利率 | 宏观经济,国内宏观,利率数据 | ts_raw_hibor | collected | 980 | 980 | 9 |  |
| hk_adjfactor | 港股复权因子 | 港股数据 | ts_raw_hk_adjfactor | collected | 66000 | 66000 | 4 |  |
| hk_balancesheet | 港股资产负债表 | 港股数据 | ts_raw_hk_balancesheet | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| hk_basic | 港股基础信息 | 港股数据 | ts_raw_hk_basic | collected | 30261 | 2751 | 12 |  |
| hk_cashflow | 港股现金流量表 | 港股数据 | ts_raw_hk_cashflow | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| hk_daily | 港股日线行情 | 港股数据 | ts_raw_hk_daily | collected | 88000 | 88000 | 11 |  |
| hk_daily_adj | 港股复权行情 | 港股数据 | ts_raw_hk_daily_adj | collected | 88000 | 70484 | 18 |  |
| hk_fina_indicator | 港股财务指标数据 | 港股数据 | ts_raw_hk_fina_indicator | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| hk_income | 港股利润表 | 港股数据 | ts_raw_hk_income | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| hk_mins | 港股分钟行情 | 港股数据 | ts_raw_hk_mins | requires_params | 0 | 0 | 0 | 必填参数, freq |
| hk_tradecal | 港股交易日历 | 港股数据 | ts_raw_hk_tradecal | collected | 3651 | 3651 | 3 |  |
| hm_detail | 游资交易每日明细 | 股票数据,打板专题数据 | ts_raw_hm_detail | collected | 10000 | 10000 | 8 |  |
| hm_list | 市场游资最全名录 | 股票数据,打板专题数据 | ts_raw_hm_list | collected | 1210 | 110 | 3 |  |
| hsgt_top10 | 沪深股通十大成交股 | 股票数据,行情数据 | ts_raw_hsgt_top10 | collected | 3300 | 3300 | 11 |  |
| idx_factor_pro | 指数技术面因子(专业版) | 指数专题 | ts_raw_idx_factor_pro | collected | 15596 | 15596 | 89 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| idx_mins | 指数历史分钟 | 指数专题 | ts_raw_idx_mins | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| index_classify | 申万行业分类 | 指数专题 | ts_raw_index_classify | collected | 3949 | 359 | 7 |  |
| index_dailybasic | 大盘指数每日指标 | 指数专题 | ts_raw_index_dailybasic | collected | 60 | 60 | 12 | 参数校验失败, trade_date,ts_code参数至少输入一个 |
| index_global | 国际主要指数 | 指数专题 | ts_raw_index_global | collected | 41040 | 41040 | 11 |  |
| index_member_all | 申万行业成分(分级) | 指数专题 | ts_raw_index_member_all | collected | 33000 | 3000 | 11 |  |
| index_monthly | 指数月线行情 | 指数专题 | ts_raw_index_monthly | collected | 5000 | 5000 | 11 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| index_weekly | 指数周线行情 | 指数专题 | ts_raw_index_weekly | collected | 3003 | 3003 | 11 | 参数校验失败, ts_code,trade_date至少输入一个参数 |
| index_weight | 指数成分和权重 | 指数专题 | ts_raw_index_weight | collected | 35000 | 35000 | 4 | 参数校验失败,  |
| irm_qa_sh | 上证e互动问答 | 大模型语料专题数据 | ts_raw_irm_qa_sh | collected | 12000 | 11986 | 6 |  |
| irm_qa_sz | 深证易互动问答 | 大模型语料专题数据 | ts_raw_irm_qa_sz | collected | 13215 | 13196 | 7 |  |
| kpl_concept_cons | 题材成分(开盘啦) | 股票数据,打板专题数据 | ts_raw_kpl_concept_cons | collected | 33000 | 3000 | 7 |  |
| kpl_list | 榜单数据(开盘啦) | 股票数据,打板专题数据 | ts_raw_kpl_list | collected | 72000 | 72000 | 24 |  |
| libor | Libor利率 | 宏观经济,国内宏观,利率数据 | ts_raw_libor | collected | 1002 | 1002 | 9 |  |
| limit_cpt_list | 涨停最强板块统计 | 股票数据,打板专题数据 | ts_raw_limit_cpt_list | collected | 6700 | 6700 | 9 |  |
| limit_list_ths | 同花顺涨跌停榜单 | 股票数据,打板专题数据 | ts_raw_limit_list_ths | collected | 16904 | 16904 | 18 |  |
| limit_step | 涨停股票连板天梯 | 股票数据,打板专题数据 | ts_raw_limit_step | collected | 6470 | 6470 | 4 |  |
| major_news | 新闻通讯(长篇) | 大模型语料专题数据 | ts_raw_major_news | collected | 8800 | 8733 | 4 |  |
| margin | 融资融券交易汇总 | 股票数据,两融及转融通 | ts_raw_margin | collected | 5666 | 5666 | 9 |  |
| margin_secs | 融资融券标的(盘前) | 股票数据,两融及转融通 | ts_raw_margin_secs | collected | 66000 | 66000 | 4 |  |
| moneyflow_cnt_ths | 板块资金流向(THS) | 股票数据,资金流向数据 | ts_raw_moneyflow_cnt_ths | collected | 12000 | 12000 | 12 |  |
| moneyflow_dc | 个股资金流向(DC) | 股票数据,资金流向数据 | ts_raw_moneyflow_dc | collected | 24000 | 24000 | 15 |  |
| moneyflow_ind_dc | 板块资金流向(DC) | 股票数据,资金流向数据 | ts_raw_moneyflow_ind_dc | collected | 20000 | 20000 | 18 |  |
| moneyflow_ind_ths | 行业资金流向(THS) | 股票数据,资金流向数据 | ts_raw_moneyflow_ind_ths | collected | 15000 | 15000 | 12 |  |
| moneyflow_mkt_dc | 大盘资金流向(DC) | 股票数据,资金流向数据 | ts_raw_moneyflow_mkt_dc | collected | 775 | 775 | 15 |  |
| moneyflow_ths | 个股资金流向(THS) | 股票数据,资金流向数据 | ts_raw_moneyflow_ths | collected | 18870 | 18870 | 13 |  |
| namechange | 股票曾用名 | 股票数据,基础数据 | ts_raw_namechange | collected | 6022 | 3854 | 6 |  |
| new_share | IPO新股上市 | 股票数据,基础数据 | ts_raw_new_share | collected | 2917 | 2917 | 12 |  |
| npr | 国家政策库 | 大模型语料专题数据 | ts_raw_npr | collected | 4607 | 4607 | 5 |  |
| opt_basic | 期权合约信息 | 期权数据 | ts_raw_opt_basic | collected | 132000 | 12000 | 20 |  |
| opt_daily | 期权日线行情 | 期权数据 | ts_raw_opt_daily | collected | 160182 | 160182 | 13 |  |
| opt_mins | 期权分钟行情 | 期权数据 | ts_raw_opt_mins | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| pledge_detail | 股权质押明细数据 | 股票数据,参考数据 | ts_raw_pledge_detail | collected | 16500 | 12793 | 14 |  |
| pledge_stat | 股权质押统计数据 | 股票数据,参考数据 | ts_raw_pledge_stat | collected | 9000 | 9000 | 7 |  |
| pro_bar | 通用行情接口 | 股票数据,行情数据 | ts_raw_pro_bar | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| repo_daily | 债券回购日行情 | 债券专题 | ts_raw_repo_daily | collected | 22000 | 22000 | 12 |  |
| report_rc | 券商盈利预测数据 | 股票数据,特色数据 | ts_raw_report_rc | collected | 55000 | 55000 | 21 |  |
| repurchase | 股票回购 | 股票数据,参考数据 | ts_raw_repurchase | collected | 20899 | 15034 | 9 |  |
| rt_etf_k | ETF实时日线 | ETF专题 | ts_raw_rt_etf_k | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| rt_fut_min | 实时分钟行情 | 期货数据 | ts_raw_rt_fut_min | requires_params | 0 | 0 | 0 | 必填参数, freq |
| rt_hk_k | 港股实时日线 | 港股数据 | ts_raw_rt_hk_k | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| rt_idx_k | 指数实时日线 | 指数专题 | ts_raw_rt_idx_k | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| rt_idx_min | 指数实时分钟 | 指数专题 | ts_raw_rt_idx_min | requires_params | 0 | 0 | 0 | 必填参数, freq |
| rt_k | 实时日线 | 股票数据,行情数据 | ts_raw_rt_k | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| rt_min | 实时分钟 | 股票数据,行情数据 | ts_raw_rt_min | requires_params | 0 | 0 | 0 | 必填参数, freq |
| sf_month | 社融增量(月度) | 宏观经济,国内宏观,金融,社会融资 | ts_raw_sf_month | collected | 3223 | 293 | 4 |  |
| sge_basic | 上海黄金基础信息 | 现货数据 | ts_raw_sge_basic | collected | 143 | 13 | 14 |  |
| sge_daily | 上海黄金现货日行情 | 现货数据 | ts_raw_sge_daily | collected | 21308 | 21308 | 14 |  |
| share_float | 限售股解禁 | 股票数据,参考数据 | ts_raw_share_float | collected | 66000 | 64948 | 7 |  |
| shibor | Shibor利率 | 宏观经济,国内宏观,利率数据 | ts_raw_shibor | collected | 2470 | 2470 | 9 |  |
| shibor_lpr | LPR贷款基础利率 | 宏观经济,国内宏观,利率数据 | ts_raw_shibor_lpr | collected | 856 | 856 | 3 |  |
| shibor_quote | Shibor报价数据 | 宏观经济,国内宏观,利率数据 | ts_raw_shibor_quote | collected | 32669 | 32669 | 18 |  |
| slb_len | 转融资交易汇总 | 股票数据,两融及转融通 | ts_raw_slb_len | collected | 2201 | 2201 | 6 |  |
| slb_len_mm | 做市借券交易汇总(停) | 股票数据,两融及转融通 | ts_raw_slb_len_mm | collected | 12664 | 12664 | 7 |  |
| slb_sec | 转融券交易汇总(停) | 股票数据,两融及转融通 | ts_raw_slb_sec | collected | 45000 | 45000 | 7 |  |
| slb_sec_detail | 转融券交易明细(停) | 股票数据,两融及转融通 | ts_raw_slb_sec_detail | collected | 36000 | 36000 | 6 |  |
| st | ST风险警示板股票 | 股票数据,基础数据 | ts_raw_st | collected | 11000 | 1000 | 7 |  |
| stk_account | 股票开户数据(停) | 股票数据,参考数据 | ts_raw_stk_account | collected | 132 | 132 | 5 |  |
| stk_account_old | 股票开户数据(旧) | 股票数据,参考数据 | ts_raw_stk_account_old | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| stk_ah_comparison | AH股比价 | 股票数据,特色数据 | ts_raw_stk_ah_comparison | collected | 2000 | 2000 | 11 |  |
| stk_auction | 开盘竞价成交(当日) | 股票数据,打板专题数据 | ts_raw_stk_auction | collected | 16000 | 16000 | 9 |  |
| stk_auction_c | 股票收盘集合竞价数据 | 股票数据,特色数据 | ts_raw_stk_auction_c | collected | 110000 | 110000 | 9 |  |
| stk_holdernumber | 股东人数 | 股票数据,参考数据 | ts_raw_stk_holdernumber | collected | 60500 | 60500 | 4 |  |
| stk_holdertrade | 股东增减持 | 股票数据,参考数据 | ts_raw_stk_holdertrade | collected | 33000 | 31742 | 11 |  |
| stk_managers | 上市公司管理层 | 股票数据,基础数据 | ts_raw_stk_managers | collected | 32000 | 32000 | 11 |  |
| stk_nineturn | 神奇九转指标 | 股票数据,特色数据 | ts_raw_stk_nineturn | collected | 110000 | 110000 | 13 |  |
| stk_premarket | 每日股本(盘前) | 股票数据,基础数据 | ts_raw_stk_premarket | collected | 24000 | 24000 | 7 |  |
| stk_rewards | 管理层薪酬和持股 | 股票数据,基础数据 | ts_raw_stk_rewards | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| stk_surv | 机构调研数据 | 股票数据,特色数据 | ts_raw_stk_surv | collected | 2400 | 2400 | 9 |  |
| stk_week_month_adj | 周月线复权行情(每日更新) | 股票数据,行情数据 | ts_raw_stk_week_month_adj | requires_params | 0 | 0 | 0 | 必填参数, freq |
| stk_weekly_monthly | 周月线行情(每日更新) | 股票数据,行情数据 | ts_raw_stk_weekly_monthly | requires_params | 0 | 0 | 0 | 必填参数, freq |
| stock_company | 上市公司基本信息 | 股票数据,基础数据 | ts_raw_stock_company | collected | 69234 | 6294 | 18 |  |
| stock_hsgt | 沪深港通股票列表 | 股票数据,基础数据 | ts_raw_stock_hsgt | collected | 22000 | 22000 | 5 |  |
| stock_st | ST股票列表 | 股票数据,基础数据 | ts_raw_stock_st | collected | 11000 | 11000 | 5 |  |
| suspend_d | 每日停复牌信息 | 股票数据,行情数据 | ts_raw_suspend_d | collected | 49837 | 49837 | 4 |  |
| sz_daily_info | 深圳市场每日交易情况 | 指数专题 | ts_raw_sz_daily_info | collected | 21592 | 21592 | 9 |  |
| tdx_daily | 通达信板块行情 | 股票数据,打板专题数据 | ts_raw_tdx_daily | collected | 6000 | 6000 | 38 |  |
| tdx_index | 通达信板块信息 | 股票数据,打板专题数据 | ts_raw_tdx_index | collected | 11000 | 1000 | 9 |  |
| tdx_member | 通达信板块成分 | 股票数据,打板专题数据 | ts_raw_tdx_member | collected | 6000 | 6000 | 4 |  |
| teleplay_record | 全国电视剧备案公示数据 | 行业经济,TMT行业 | ts_raw_teleplay_record | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| ths_daily | 同花顺概念和行业指数行情 | 股票数据,打板专题数据 | ts_raw_ths_daily | collected | 33000 | 33000 | 12 |  |
| ths_hot | 同花顺App热榜数 | 股票数据,打板专题数据 | ts_raw_ths_hot | collected | 22000 | 2000 | 11 |  |
| ths_index | 同花顺行业概念板块 | 股票数据,打板专题数据 | ts_raw_ths_index | collected | 18975 | 1725 | 6 |  |
| tmt_twincome | 台湾电子产业月营收 | 行业经济,TMT行业 | ts_raw_tmt_twincome | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| tmt_twincomedetail | 台湾电子产业月营收明细 | 行业经济,TMT行业 | ts_raw_tmt_twincomedetail | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| top10_floatholders | 前十大流通股东 | 股票数据,参考数据 | ts_raw_top10_floatholders | collected | 66000 | 66000 | 9 |  |
| top10_holders | 前十大股东 | 股票数据,参考数据 | ts_raw_top10_holders | collected | 66000 | 66000 | 9 |  |
| trade_cal | 交易日历 | 股票数据,基础数据 | ts_raw_trade_cal | collected | 3651 | 3651 | 4 |  |
| us_adjfactor | 美股复权因子 | 美股数据 | ts_raw_us_adjfactor | collected | 165000 | 165000 | 5 |  |
| us_balancesheet | 美股资产负债表 | 美股数据 | ts_raw_us_balancesheet | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| us_basic | 美股基础信息 | 美股数据 | ts_raw_us_basic | collected | 66000 | 5999 | 6 |  |
| us_cashflow | 美股现金流量表 | 美股数据 | ts_raw_us_cashflow | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| us_daily | 美股日线行情 | 美股数据 | ts_raw_us_daily | collected | 88000 | 87762 | 11 |  |
| us_daily_adj | 美股复权行情 | 美股数据 | ts_raw_us_daily_adj | collected | 88000 | 87998 | 19 |  |
| us_fina_indicator | 美股财务指标数据 | 美股数据 | ts_raw_us_fina_indicator | collected | 22000 | 22000 | 69 |  |
| us_income | 美股利润表 | 美股数据 | ts_raw_us_income | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| us_tbr | 短期国债利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_tbr | collected | 2495 | 2495 | 11 |  |
| us_tltr | 国债长期利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_tltr | collected | 2494 | 2494 | 4 |  |
| us_tradecal | 美股交易日历 | 美股数据 | ts_raw_us_tradecal | collected | 3651 | 3651 | 3 |  |
| us_trltr | 国债长期利率平均值 | 宏观经济,国际宏观,美国利率 | ts_raw_us_trltr | collected | 2494 | 2494 | 2 |  |
| us_trycr | 国债实际收益率曲线利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_trycr | collected | 2493 | 2493 | 6 |  |
| us_tycr | 国债收益率曲线利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_tycr | collected | 2494 | 2494 | 13 |  |
| wz_index | 温州民间借贷利率 | 宏观经济,国内宏观,利率数据 | ts_raw_wz_index | collected | 1499 | 1499 | 13 |  |
| yc_cb | 国债收益率曲线 | 债券专题 | ts_raw_yc_cb | collected | 22000 | 22000 | 6 |  |
