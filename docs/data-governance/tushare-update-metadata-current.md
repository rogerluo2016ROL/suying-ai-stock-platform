# Tushare 更新时间/频率审计

> 生成时间: 2026-07-02T10:57:15

## 汇总

- 接口数: 224
- 已抽取更新时间或频率: 40
- 未在文档中找到明确描述: 184

## 明细

| API | 更新时间点 | 更新频率 | 状态 | 证据 | 文档 |
|---|---|---|---|---|---|
| rt_min | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/374.md |
| rt_etf_k | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/400.md |
| stk_mins | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/370.md |
| etf_index | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/386.md |
| etf_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/385.md |
| fund_adj | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/199.md |
| fund_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/127.md |
| etf_share_size | 交易所于次日早8点30左右更新上一交易日的数据 | 每日 | extracted | 入库，交易所于次日早8点30左右更新上一交易日的数据；另外，涉及海外的ETF数据更新会晚一些属于正常情况。 限量：单次最大5000条，可根据代码或日期循环提取 积分：需要8000积分可以调取，具体请参阅[积分获取办法](https://tushare.pro/document/1?doc_id=13)  <br> ### 输入参数 名称 ｜ 类型 ｜ 必选  | https://tushare.pro/wctapi/documents/408.md |
| bc_otcqt | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/322.md |
| cb_rate | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/305.md |
| bond_blk_detail | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/272.md |
| bond_blk | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/271.md |
| cb_call | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/269.md |
| repo_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/256.md |
| bc_bestotcqt | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/323.md |
| cb_factor_pro | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/392.md |
| cb_price_chg | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/246.md |
| eco_cal | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/233.md |
| yc_cb | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/201.md |
| cb_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/187.md |
| cb_issue | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/186.md |
| cb_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/185.md |
| cb_share | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/247.md |
| fund_manager | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/208.md |
| fund_share | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/207.md |
| fund_portfolio | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/121.md |
| fund_div | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/120.md |
| fund_nav | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/119.md |
| fund_company | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/118.md |
| fund_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/19.md |
| fund_factor_pro | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/359.md |
| fx_obasic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/178.md |
| fx_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/179.md |
| research_report | 增量每天两次更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/415.md |
| news | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/143.md |
| cctv_news | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/154.md |
| anns_d | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/176.md |
| irm_qa_sz | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/367.md |
| irm_qa_sh | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/366.md |
| major_news | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/195.md |
| npr | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/406.md |
| cn_ppi | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/245.md |
| cn_cpi | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/228.md |
| shibor | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/149.md |
| shibor_lpr | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/151.md |
| libor | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/152.md |
| shibor_quote | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/150.md |
| wz_index | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/173.md |
| hibor | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/153.md |
| gz_index | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/174.md |
| cn_gdp | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/227.md |
| cn_pmi | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/325.md |
| sf_month | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/310.md |
| cn_m | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/242.md |
| us_tbr | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/221.md |
| us_trycr | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/220.md |
| us_tltr | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/222.md |
| us_trltr | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/223.md |
| us_tycr | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/219.md |
| rt_idx_min | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/420.md |
| idx_mins | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/419.md |
| daily_info | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/215.md |
| index_global | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/211.md |
| index_classify | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/181.md |
| sz_daily_info | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/268.md |
| index_dailybasic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/128.md |
| rt_idx_k | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/403.md |
| index_weight | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/96.md |
| ci_index_member | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/373.md |
| idx_factor_pro | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/358.md |
| index_member_all | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/335.md |
| rt_sw_k | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/417.md |
| index_monthly | 描述：获取指数月线行情,每月更新一次 | 每月 | extracted |  | https://tushare.pro/wctapi/documents/172.md |
| ci_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/308.md |
| index_weekly | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/171.md |
| sw_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/327.md |
| index_daily | unknown | unknown | doc_unavailable | 404 Client Error: Not Found for url: https://tushare.pro/wctapi/documents/155.md | https://tushare.pro/wctapi/documents/155.md |
| index_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/94.md |
| opt_mins | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/341.md |
| opt_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/159.md |
| opt_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/158.md |
| fut_weekly_detail | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/216.md |
| ft_limit | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/368.md |
| rt_fut_min | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/340.md |
| fut_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/135.md |
| trade_cal | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/26.md |
| fut_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/138.md |
| fut_holding | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/139.md |
| fut_wsr | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/140.md |
| fut_settle | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/141.md |
| fut_mapping | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/189.md |
| ft_mins | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/313.md |
| fut_weekly_monthly | ## 期货周/月线行情(每日更新) | 每日 | extracted |  | https://tushare.pro/wctapi/documents/337.md |
| hk_cashflow | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/391.md |
| hk_balancesheet | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/390.md |
| hk_income | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/389.md |
| hk_fina_indicator | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/388.md |
| hk_adjfactor | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/401.md |
| hk_daily_adj | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/339.md |
| rt_hk_k | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/383.md |
| hk_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/191.md |
| hk_daily | 每日18点左右更新当日数据 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/192.md |
| hk_mins | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/304.md |
| hk_tradecal | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/250.md |
| sge_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/285.md |
| sge_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/284.md |
| us_fina_indicator | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/393.md |
| us_adjfactor | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/402.md |
| us_cashflow | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/396.md |
| us_balancesheet | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/395.md |
| us_income | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/394.md |
| us_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/254.md |
| us_tradecal | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/253.md |
| us_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/252.md |
| us_daily_adj | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/338.md |
| margin_secs | 每天盘前更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/326.md |
| slb_len | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/331.md |
| slb_sec | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/332.md |
| slb_sec_detail | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/333.md |
| margin_detail | 交易所于每天8点30左右更新上一日数据 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/59.md |
| margin | 交易所于每天8点30左右更新上一日数据 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/58.md |
| slb_len_mm | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/334.md |
| repurchase | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/124.md |
| pledge_stat | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/110.md |
| share_float | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/160.md |
| block_trade | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/161.md |
| stk_account | 从2017年2月10日开始，中国证券登记结算公司停止了发布本周持仓账户数和本周交易账户数 | 每周 | extracted | 数据说明：从2017年2月10日开始，中国证券登记结算公司停止了发布本周持仓账户数和本周交易账户数；另外，2015年5月8日之前的数据结构也不同，具体请参阅[股票开户旧数据](https://tushare.pro/document/2?doc_id=165)接口。 | https://tushare.pro/wctapi/documents/164.md |
| stk_account_old | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/165.md |
| stk_holdernumber | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/166.md |
| stk_holdertrade | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/175.md |
| top10_holders | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/61.md |
| pledge_detail | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/111.md |
| top10_floatholders | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/62.md |
| st | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/423.md |
| stock_hsgt | 提示：每天上午9:20更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/398.md |
| stock_st | 提示：每天上午9:20更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/397.md |
| bse_mapping | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/375.md |
| stk_premarket | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/329.md |
| new_share | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/123.md |
| stk_rewards | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/194.md |
| stk_managers | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/193.md |
| stock_company | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/112.md |
| namechange | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/100.md |
| stock_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/25.md |
| bak_basic | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/262.md |
| dc_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/382.md |
| dc_hot | 状态N每小时更新一次 | unknown | extracted | 更新时间为22：30） <br> <br> **输出参数** 名称 ｜ 类型 ｜ 默认显示 ｜ 描述 --- ｜ ---- ｜ ---- ｜ ---- trade_date ｜ str ｜ Y ｜ 交易日期 data_type ｜ str ｜ Y ｜ 数据类型 ts_code ｜ str ｜ Y ｜ 股票代码 ts_name ｜ str ｜ Y ｜ 股票名称 | https://tushare.pro/wctapi/documents/321.md |
| limit_list_d | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/298.md |
| hm_list | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/311.md |
| kpl_list | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/347.md |
| ths_member | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/261.md |
| ths_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/260.md |
| ths_index | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/259.md |
| top_inst | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/107.md |
| kpl_concept_cons | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/351.md |
| limit_list_ths | 增量每天16点左右更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/355.md |
| limit_step | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/356.md |
| limit_cpt_list | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/357.md |
| dc_index | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/362.md |
| dc_member | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/363.md |
| stk_auction | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/369.md |
| tdx_index | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/376.md |
| top_list | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/106.md |
| tdx_member | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/377.md |
| tdx_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/378.md |
| hm_detail | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/312.md |
| ths_hot | 状态N每小时更新一次 | unknown | extracted | 更新时间为22：30） <br> <br> **输出参数** 名称 ｜ 类型 ｜ 默认显示 ｜ 描述 --- ｜ ---- ｜ ---- ｜ ---- trade_date ｜ str ｜ Y ｜ 交易日期 data_type ｜ str ｜ Y ｜ 数据类型 ts_code ｜ str ｜ Y ｜ 股票代码 ts_name ｜ str ｜ Y ｜ 股票名称 | https://tushare.pro/wctapi/documents/320.md |
| stk_nineturn | 接口：stk_nineturn（由于涉及分钟数据每天21点更新） | 每日 | extracted |  | https://tushare.pro/wctapi/documents/364.md |
| hk_hold | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/188.md |
| broker_recommend | 一般1日~3日内更新当月数据 | 每月 | extracted |  | https://tushare.pro/wctapi/documents/267.md |
| ccass_hold_detail | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/274.md |
| stk_surv | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/275.md |
| report_rc | 每晚19~22点更新当日数据 | unknown | extracted | 更新时间 <br> <br> **接口用法** ```python pro = ts.pro_api() df = pro.report_rc(ts_code='', report_date='20220429') ``` <br> <br> **数据样例**  ts_code name report_date classify org_name quart | https://tushare.pro/wctapi/documents/292.md |
| cyq_perf | 每天18~19点左右更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/293.md |
| cyq_chips | 每天18~19点之间更新当日数据 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/294.md |
| ccass_hold | 描述：获取中央结算系统持股汇总数据，覆盖全部历史数据，根据交易所披露时间，当日数据在下一交易日早上9点前完成入库 | unknown | extracted | 入库 限量：单次最大5000条数据，可循环或分页提供全部 积分：用户120积分可以试用看数据，5000积分每分钟可以请求300次，8000积分以上可以请求500次每分钟，具体请参阅[积分获取办法](https://tushare.pro/document/1?doc_id=13)  <br> <br> **输入参数** 名称 ｜ 类型 ｜ 必选 ｜ 描述 - | https://tushare.pro/wctapi/documents/295.md |
| stk_auction_o | 每天盘后更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/353.md |
| stk_auction_c | 每天盘后更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/354.md |
| stk_ah_comparison | 提示：每天盘后17:00更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/399.md |
| stk_factor_pro | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/328.md |
| daily | 交易日每天15点～16点之间入库 | 交易日每天 | extracted | 入库。本接口是未复权行情，停牌期间不提供数据 调取说明：基础积分每分钟内可调取500次，每次6000条数据，一次请求相当于提取一个股票23年历史 描述：获取股票行情数据，或通过[**通用行情接口**]( https://tushare.pro/document/2?doc_id=109)获取数据，包含了前后复权数据 **输入参数** 名称 ｜ 类型 ｜ 必选 | https://tushare.pro/wctapi/documents/27.md |
| pro_bar | unknown | unknown | not_found | 更新时间**：股票和指数通常在15点～17点之间，具体请参考各接口文档明细。 **描述**：目前整合了股票（未复权、前复权、后复权）、指数、ETF基金、期货、期权的行情数据，未来还将整合包括外汇在内的所有交易行情数据，同时提供分钟数据。不同数据对应不同的积分要求，具体请参阅每类数据的文档说明。 **其它**：由于本接口是集成接口，在SDK层做了一些逻辑处理， | https://tushare.pro/wctapi/documents/109.md |
| monthly | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/145.md |
| rt_k | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/372.md |
| stk_week_month_adj | ## 股票周/月线行情(复权--每日更新) | 每日 | extracted |  | https://tushare.pro/wctapi/documents/365.md |
| stk_weekly_monthly | ## 股票周/月线行情(每日更新) | 每日 | extracted |  | https://tushare.pro/wctapi/documents/336.md |
| bak_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/255.md |
| weekly | 本接口每周最后一个交易日更新 | 每周 | extracted |  | https://tushare.pro/wctapi/documents/144.md |
| suspend_d | 不定期 | unknown | extracted | 更新时间：不定期 描述：按日期方式获取股票每日停复牌信息 **输入参数** 名称 ｜ 类型 ｜ 必选 ｜ 描述 ---- ｜ ----- ｜ ---- ｜ ---- ts_code ｜ str ｜ N ｜ 股票代码(可输入多值) trade_date｜ str ｜ N ｜ 交易日日期 start_date ｜ str ｜ N ｜ 停复牌查询开始日期 end_ | https://tushare.pro/wctapi/documents/214.md |
| ggt_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/196.md |
| stk_limit | 每个交易日8点40左右更新当日股票涨跌停价格 | unknown | extracted |  | https://tushare.pro/wctapi/documents/183.md |
| ggt_top10 | 每天18~20点之间完成当日更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/49.md |
| hsgt_top10 | 每天18~20点之间完成当日更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/48.md |
| daily_basic | 交易日每日15点～17点之间 | 每日 | extracted | 更新时间：交易日每日15点～17点之间 描述：获取全部股票每日重要的基本面指标，可用于选股分析、报表展示等。单次请求最大返回6000条数据，可按日线循环提取全部历史。 积分：至少2000积分才可以调取，5000积分无总量限制，具体请参阅[积分获取办法](https://tushare.pro/document/1?doc_id=13)  **输入参数** 名 | https://tushare.pro/wctapi/documents/32.md |
| adj_factor | 盘前9点15~20分完成当日复权因子入库 | unknown | extracted | 更新时间：盘前9点15~20分完成当日复权因子入库 描述：本接口由Tushare自行生产，获取股票复权因子，可提取单只股票全部历史复权因子，也可以提取单日全部股票的复权因子。 积分要求：2000积分起，5000以上可高频调取 **输入参数** 名称 ｜ 类型 ｜ 必选 ｜ 描述 ---- ｜ ----- ｜ ---- ｜ ---- ts_code ｜ str | https://tushare.pro/wctapi/documents/28.md |
| ggt_monthly | unknown | unknown | doc_unavailable | 404 Client Error: Not Found for url: https://tushare.pro/wctapi/documents/197.md | https://tushare.pro/wctapi/documents/197.md |
| income | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/33.md |
| cashflow | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/44.md |
| balancesheet | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/36.md |
| express | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/46.md |
| fina_indicator | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/79.md |
| fina_mainbz | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/81.md |
| dividend | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/103.md |
| disclosure_date | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/162.md |
| forecast | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/45.md |
| fina_audit | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/80.md |
| moneyflow_hsgt | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/47.md |
| moneyflow | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/170.md |
| moneyflow_ind_ths | 每日盘后更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/343.md |
| moneyflow_ind_dc | 每天盘后更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/344.md |
| moneyflow_mkt_dc | 每日盘后更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/345.md |
| moneyflow_ths | 每日盘后更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/348.md |
| moneyflow_dc | 每日盘后更新 | 每日 | extracted |  | https://tushare.pro/wctapi/documents/349.md |
| moneyflow_cnt_ths | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/371.md |
| film_record | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/156.md |
| teleplay_record | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/180.md |
| tmt_twincomedetail | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/87.md |
| tmt_twincome | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/88.md |
| bo_monthly | 数据更新：本月更新上一月数据 | 每月 | extracted |  | https://tushare.pro/wctapi/documents/113.md |
| bo_daily | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/115.md |
| bo_cinema | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/116.md |
| bo_weekly | 数据更新：本周更新上一周数据 | 每周 | extracted |  | https://tushare.pro/wctapi/documents/114.md |
| fund_sales_ratio | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/265.md |
| fund_sales_vol | unknown | unknown | not_found |  | https://tushare.pro/wctapi/documents/266.md |
