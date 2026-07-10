# Tushare 批量接入结果

> 生成时间: 2026-07-10T23:29:26

## 汇总

- collected: 60
- requires_params: 14
- unsupported_api: 5

## 明细

| API | 标题 | 分类 | 表 | 状态 | 拉取行数 | 入库行数 | 字段数 | 错误 |
|---|---|---|---|---|---:|---:|---:|---|
| moneyflow_ths | 个股资金流向(THS) | 股票数据,资金流向数据 | ts_raw_moneyflow_ths | collected | 18870 | 6000 | 13 |  |
| namechange | 股票曾用名 | 股票数据,基础数据 | ts_raw_namechange | collected | 8422 | 1260 | 6 |  |
| new_share | IPO新股上市 | 股票数据,基础数据 | ts_raw_new_share | collected | 4290 | 1379 | 12 |  |
| npr | 国家政策库 | 大模型语料专题数据 | ts_raw_npr | collected | 6333 | 1726 | 5 |  |
| opt_basic | 期权合约信息 | 期权数据 | ts_raw_opt_basic | collected | 252000 | 1248 | 20 |  |
| opt_daily | 期权日线行情 | 期权数据 | ts_raw_opt_daily | collected | 180000 | 34818 | 13 |  |
| opt_mins | 期权分钟行情 | 期权数据 | ts_raw_opt_mins | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| pledge_detail | 股权质押明细数据 | 股票数据,参考数据 | ts_raw_pledge_detail | collected | 28624 | 21086 | 14 |  |
| pledge_stat | 股权质押统计数据 | 股票数据,参考数据 | ts_raw_pledge_stat | collected | 12721 | 7139 | 7 |  |
| pro_bar | 通用行情接口 | 股票数据,行情数据 | ts_raw_pro_bar | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| repo_daily | 债券回购日行情 | 债券专题 | ts_raw_repo_daily | collected | 42000 | 20421 | 12 |  |
| report_rc | 券商盈利预测数据 | 股票数据,特色数据 | ts_raw_report_rc | collected | 105000 | 51983 | 21 |  |
| repurchase | 股票回购 | 股票数据,参考数据 | ts_raw_repurchase | collected | 25017 | 2697 | 9 |  |
| rt_etf_k | ETF实时日线 | ETF专题 | ts_raw_rt_etf_k | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| rt_fut_min | 实时分钟行情 | 期货数据 | ts_raw_rt_fut_min | requires_params | 0 | 0 | 0 | 必填参数, freq |
| rt_hk_k | 港股实时日线 | 港股数据 | ts_raw_rt_hk_k | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| rt_idx_k | 指数实时日线 | 指数专题 | ts_raw_rt_idx_k | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| rt_idx_min | 指数实时分钟 | 指数专题 | ts_raw_rt_idx_min | requires_params | 0 | 0 | 0 | 必填参数, freq |
| rt_k | 实时日线 | 股票数据,行情数据 | ts_raw_rt_k | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| rt_min | 实时分钟 | 股票数据,行情数据 | ts_raw_rt_min | requires_params | 0 | 0 | 0 | 必填参数, freq |
| sf_month | 社融增量(月度) | 宏观经济,国内宏观,金融,社会融资 | ts_raw_sf_month | collected | 6153 | 2 | 4 |  |
| sge_basic | 上海黄金基础信息 | 现货数据 | ts_raw_sge_basic | collected | 273 | 0 | 14 |  |
| sge_daily | 上海黄金现货日行情 | 现货数据 | ts_raw_sge_daily | collected | 38245 | 17265 | 14 |  |
| share_float | 限售股解禁 | 股票数据,参考数据 | ts_raw_share_float | collected | 119421 | 58719 | 7 |  |
| shibor | Shibor利率 | 宏观经济,国内宏观,利率数据 | ts_raw_shibor | collected | 4913 | 2443 | 9 |  |
| shibor_lpr | LPR贷款基础利率 | 宏观经济,国内宏观,利率数据 | ts_raw_shibor_lpr | collected | 1530 | 674 | 3 |  |
| shibor_quote | Shibor报价数据 | 宏观经济,国内宏观,利率数据 | ts_raw_shibor_quote | collected | 71538 | 38869 | 18 |  |
| slb_len | 转融资交易汇总 | 股票数据,两融及转融通 | ts_raw_slb_len | collected | 2811 | 610 | 6 |  |
| slb_len_mm | 做市借券交易汇总(停) | 股票数据,两融及转融通 | ts_raw_slb_len_mm | collected | 12664 | 0 | 7 |  |
| slb_sec | 转融券交易汇总(停) | 股票数据,两融及转融通 | ts_raw_slb_sec | collected | 59510 | 14510 | 7 |  |
| slb_sec_detail | 转融券交易明细(停) | 股票数据,两融及转融通 | ts_raw_slb_sec_detail | collected | 36000 | 0 | 6 |  |
| st | ST风险警示板股票 | 股票数据,基础数据 | ts_raw_st | collected | 21000 | 6 | 7 |  |
| stk_account | 股票开户数据(停) | 股票数据,参考数据 | ts_raw_stk_account | collected | 192 | 60 | 5 |  |
| stk_account_old | 股票开户数据(旧) | 股票数据,参考数据 | ts_raw_stk_account_old | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| stk_ah_comparison | AH股比价 | 股票数据,特色数据 | ts_raw_stk_ah_comparison | collected | 2000 | 1017 | 11 |  |
| stk_auction | 开盘竞价成交(当日) | 股票数据,打板专题数据 | ts_raw_stk_auction | collected | 16000 | 8000 | 9 |  |
| stk_auction_c | 股票收盘集合竞价数据 | 股票数据,特色数据 | ts_raw_stk_auction_c | collected | 180000 | 86427 | 9 |  |
| stk_holdernumber | 股东人数 | 股票数据,参考数据 | ts_raw_stk_holdernumber | collected | 112621 | 80317 | 4 |  |
| stk_holdertrade | 股东增减持 | 股票数据,参考数据 | ts_raw_stk_holdertrade | collected | 54380 | 21670 | 11 |  |
| stk_managers | 上市公司管理层 | 股票数据,基础数据 | ts_raw_stk_managers | collected | 32000 | 0 | 11 |  |
| stk_nineturn | 神奇九转指标 | 股票数据,特色数据 | ts_raw_stk_nineturn | collected | 210000 | 114405 | 13 |  |
| stk_premarket | 每日股本(盘前) | 股票数据,基础数据 | ts_raw_stk_premarket | collected | 24000 | 8000 | 7 |  |
| stk_rewards | 管理层薪酬和持股 | 股票数据,基础数据 | ts_raw_stk_rewards | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| stk_surv | 机构调研数据 | 股票数据,特色数据 | ts_raw_stk_surv | collected | 2400 | 400 | 9 |  |
| stk_week_month_adj | 周月线复权行情(每日更新) | 股票数据,行情数据 | ts_raw_stk_week_month_adj | requires_params | 0 | 0 | 0 | 必填参数, freq |
| stk_weekly_monthly | 周月线行情(每日更新) | 股票数据,行情数据 | ts_raw_stk_weekly_monthly | requires_params | 0 | 0 | 0 | 必填参数, freq |
| stock_company | 上市公司基本信息 | 股票数据,基础数据 | ts_raw_stock_company | collected | 132174 | 0 | 18 |  |
| stock_hsgt | 沪深港通股票列表 | 股票数据,基础数据 | ts_raw_stock_hsgt | collected | 22000 | 2654 | 5 |  |
| stock_st | ST股票列表 | 股票数据,基础数据 | ts_raw_stock_st | collected | 11000 | 1270 | 5 |  |
| suspend_d | 每日停复牌信息 | 股票数据,行情数据 | ts_raw_suspend_d | collected | 99932 | 55105 | 4 |  |
| sz_daily_info | 深圳市场每日交易情况 | 指数专题 | ts_raw_sz_daily_info | collected | 37736 | 16144 | 9 |  |
| tdx_daily | 通达信板块行情 | 股票数据,打板专题数据 | ts_raw_tdx_daily | collected | 6000 | 3000 | 38 |  |
| tdx_index | 通达信板块信息 | 股票数据,打板专题数据 | ts_raw_tdx_index | collected | 21000 | 0 | 9 |  |
| tdx_member | 通达信板块成分 | 股票数据,打板专题数据 | ts_raw_tdx_member | collected | 6000 | 0 | 4 |  |
| teleplay_record | 全国电视剧备案公示数据 | 行业经济,TMT行业 | ts_raw_teleplay_record | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| ths_daily | 同花顺概念和行业指数行情 | 股票数据,打板专题数据 | ts_raw_ths_daily | collected | 60000 | 30000 | 12 |  |
| ths_hot | 同花顺App热榜数 | 股票数据,打板专题数据 | ts_raw_ths_hot | collected | 42000 | 1335 | 11 |  |
| ths_index | 同花顺行业概念板块 | 股票数据,打板专题数据 | ts_raw_ths_index | collected | 36225 | 0 | 6 |  |
| tmt_twincome | 台湾电子产业月营收 | 行业经济,TMT行业 | ts_raw_tmt_twincome | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| tmt_twincomedetail | 台湾电子产业月营收明细 | 行业经济,TMT行业 | ts_raw_tmt_twincomedetail | unsupported_api | 0 | 0 | 0 | 请指定正确的接口名 |
| top10_floatholders | 前十大流通股东 | 股票数据,参考数据 | ts_raw_top10_floatholders | collected | 120000 | 60937 | 9 |  |
| top10_holders | 前十大股东 | 股票数据,参考数据 | ts_raw_top10_holders | collected | 120000 | 66005 | 9 |  |
| trade_cal | 交易日历 | 股票数据,基础数据 | ts_raw_trade_cal | collected | 7301 | 3650 | 4 |  |
| us_adjfactor | 美股复权因子 | 美股数据 | ts_raw_us_adjfactor | collected | 315000 | 165497 | 5 |  |
| us_balancesheet | 美股资产负债表 | 美股数据 | ts_raw_us_balancesheet | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| us_basic | 美股基础信息 | 美股数据 | ts_raw_us_basic | collected | 126000 | 0 | 6 |  |
| us_cashflow | 美股现金流量表 | 美股数据 | ts_raw_us_cashflow | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| us_daily | 美股日线行情 | 美股数据 | ts_raw_us_daily | collected | 168000 | 92766 | 11 |  |
| us_daily_adj | 美股复权行情 | 美股数据 | ts_raw_us_daily_adj | collected | 168000 | 90429 | 19 |  |
| us_fina_indicator | 美股财务指标数据 | 美股数据 | ts_raw_us_fina_indicator | collected | 41596 | 28297 | 69 |  |
| us_income | 美股利润表 | 美股数据 | ts_raw_us_income | requires_params | 0 | 0 | 0 | 必填参数, ts_code |
| us_tbr | 短期国债利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_tbr | collected | 4999 | 2504 | 11 |  |
| us_tltr | 国债长期利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_tltr | collected | 4997 | 2503 | 4 |  |
| us_tradecal | 美股交易日历 | 美股数据 | ts_raw_us_tradecal | collected | 7301 | 3650 | 3 |  |
| us_trltr | 国债长期利率平均值 | 宏观经济,国际宏观,美国利率 | ts_raw_us_trltr | collected | 4997 | 2503 | 2 |  |
| us_trycr | 国债实际收益率曲线利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_trycr | collected | 4996 | 2503 | 6 |  |
| us_tycr | 国债收益率曲线利率 | 宏观经济,国际宏观,美国利率 | ts_raw_us_tycr | collected | 4997 | 2503 | 13 |  |
| wz_index | 温州民间借贷利率 | 宏观经济,国内宏观,利率数据 | ts_raw_wz_index | collected | 2324 | 825 | 13 |  |
| yc_cb | 国债收益率曲线 | 债券专题 | ts_raw_yc_cb | collected | 22000 | 2000 | 6 |  |
