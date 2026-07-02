# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-06-26

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

- **Project:** suying-ai-platform

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

## Key Learnings

### 资金/机构因子能力地图 (2026-07-02 盘点)
项目**已具备**做"暗盘资金"和"机构活跃度"指标的全部数据 + 大部分代码：
- **数据资产(Tushare全套, 填充良好)**: `moneyflow`(1428万行,大单/超大单净额,~06-30) / `top_inst`(201万,龙虎榜机构席位) / `top_list` / `block_trade_data`(大宗) / `ts_raw_stock_hsgt`+`ts_raw_hsgt_top10`(北向) / `ts_raw_top10_floatholders`(十大流通股东,季频) / `stk_holdernumber`(股东户数) / `stk_holdertrade`(增减持) / `research_reports` / `ts_raw_fund_portfolio`(基金持仓)。
- **已有代码**: `packages/kronos-factors/kronos_factors/scorer/advanced_factors.py:875 get_tushare_scores()` 已实现 0-10 分制: `tushare_moneyflow`(大单+超大单买卖对比+主力净额20日趋势) / `tushare_top_inst`(机构net_buy) / `tushare_top_list` / `tushare_block_trade`(折溢价) / `tushare_hk_hold`/`tushare_north_flow`/`tushare_margin`/`tushare_por`。服务 `diagnosis-service:8009` 五维诊断的"资金面"维度已用。
- **真实缺口(2个)**: (1)无Level-2逐笔(`stk_mins`仅5min, `ts_raw_rt_min`是空壳表)→不能做冰山单/对倒/大单吞没,需采购Tushare Lv2;(2)无盘中实时资金流`rt_moneyflow`表→moneyflow是T日收盘后日级,龙虎榜T+1,午后选股场景下盘中看不了实时大单,需接Tushare `rt_moneyflow`/`moneyflow_cx`新建采集。
- **落地路径**: 给午后选股加日级暗盘因子最快(包装get_tushare_scores为批量因子注入run_today_afternoon), 盘中实时版需3-5天(新建rt_moneyflow采集), L2精细版依赖采购。

### Do-Not-Repeat
- **(2026-07-02) 不要再说"Xtquant/QMT 是本项目 L2 零采购路径"** — 实测 `import xtquant` ModuleNotFoundError, `.venv` 根本没装; `services/trade-service/app/xtquant_broker.py:38` 明写"xtquant SDK not installed — STUB mode. Install on Windows host with QMT/miniQMT"。当前 macOS 环境完全跑不了 xtquant, 要走这条需 Windows 机器+QMT客户端+券商账号+L2行情授权(券商L2约100-300元/月), 是重型基建不是"已有"。

### Key Learnings
- **(2026-07-02) Tushare L2 实测真相(已端到端验证, token长度56已配)**:
  - ✅ `ts.realtime_tick(code)` 爬虫逐笔成交, 含 `TYPE`字段(买盘/卖盘/中性)=主买主卖方向, 000001半日2290笔。**已用它算出暗盘指标**: 主买3.67亿/主卖3.52亿/净+0.15亿, 大单(≥1000手)主买90笔/主卖70笔/大单净+0.384亿。→ 盘中实时暗盘**现在就能做**。
  - ✅ `pro.rt_tick`(Pro官方) + `ts.realtime_quote` 返回**五档盘口快照**(B1-5/A1-5 量价 + OHLC + num成交笔数), pro.rt_tick trade_time格式 'YYYY-MM-DD HH:MM:SS'。
  - ❌ 历史逐笔回溯拿不到(`get_tick_data`返回空, `pro.tick`/`pro.stk_tick`报"请指定正确的接口名") — 印证官方导航: 股票无"历史Tick"。
  - ❌ 只有五档(B1-5/A1-5), 无十档(十档需交易所L2授权)。
  - ❌ realtime_tick 仅当日实时, 盘后/历史日期取不到。
  - **结论**: Tushare全权限 = 盘中实时逐笔+主买主卖+五档(可做实时暗盘), 但无历史L2回溯/无十档。真L2回测需聚宽/米筐; 十档需Xtquant(Windows+QMT)。

### Key Learnings (续)
- **(2026-07-02) 机构活跃度指标实测结论(端到端验证)**:
  - ✅ **直接可用(7维数据健康)**: `top_inst`龙虎榜机构(002636近30天上榜4天)、`block_trade_data`大宗(茅台近90天21笔)、`stk_holdernumber`股东户数(茅台255892→243169 -5.0%筹码集中, 数据质量最高)、`research_reports`研报(茅台近90天10篇)、`stk_holdertrade`增减持、`ts_raw_top10_floatholders`十大流通股东(季频)、`margin_detail`/`margin_summary`两融(⚠️表名不是margin)。
  - ⚠️ **需补采/换表**: ①`ts_raw_fund_portfolio`基金持仓**全表仅60行/最新2024-12-27, 基本未采**, 需重启sync_fund_portfolio; ②北向个股持股量要用`hk_holdings`表(2646行), **`ts_raw_stock_hsgt`只是分类表(type/type_name), 无持股量字段**。
  - ❌ **缺**: 机构调研数据(Tushare有`stk_surv`, 本项目etl.py无sync_stk_surv, 未采)。
  - 🔧 **项目数据治理坑(跨表join必踩)**: ①code格式不统一 — 业务表纯数字(`top_inst.code='600519'`), ts_raw_*表带后缀(`ts_code='600519.SH'`), 批量join需`LEFT(code,6)`转换; ②`top_inst.net_buy`绝对值存疑(002636一个月机构净买入算出143亿, 不合理), 疑似重复入库, 需去重校验; ③各表amount/volume单位不一致, 需统一。
  - **结论**: 机构活跃度比暗盘资金**更容易落地**(日级/季级已落库, 不需实时逐笔)。`advanced_factors.py:875 get_tushare_scores()`已实现`tushare_top_inst`+`tushare_por`评分基础。落地只需: 补采基金持仓+机构调研, 修code格式转换, 即可批量算机构活跃度综合分。

### Do-Not-Repeat (续)
- **(2026-07-02) hk_holdings 北向持股表 code 损坏(第4坑)** — 06-30数据933/935行code是5位存储, 沪市6开头code**整体缺失**(LIKE '6%'返回空)。zfill(6)补0对深市0/3开头码可靠, 对沪市6开头会错(60051→060051张冠李戴)。**北向维度当前不可直接用于全市场排名**, 已从机构活跃度综合分剔除, 仅深市作参考列。根因ETL入库截断, 待修sync_hk_hold用6位ts_code重灌。

### Key Learnings (续)
- **(2026-07-02) 机构活跃度Top20方法论(已跑通)**: 5维percentile加权 = 龙虎榜机构净买入(去重DISTINCT)45% + 上榜天数10% + 股东户数变化(下降=筹码集中)20% + 大宗笔数10% + 研报篇数15%。北向(hk_holdings)因code损坏剔除。每维rank(pct)*100归一化抗异常值, 缺失=0分。top_inst去重关键(1.3x重复)。结果主线: 电子/半导体+新材料(中国巨石82分/东山精密75/云南锗业73), 与午后选股化工/小金属主线呼应。

### Do-Not-Repeat (续)
- **(2026-07-02) 北向个股持股 2024-08 起停止披露(政策)** — hk_hold接口exchange值是SH/SZ(非SSE/SZSE), 2023-12-29北向SH1513/SZ1758行; 但2024-07起全部返回空(交易所2024-08-19停止披露北向实时/个股持股)。本项目hk_holdings是南向港股通(pro.hk_hold默认HKEX, .HK码5位), 注释"north-bound"错误。**不要再尝试用hk_hold拿近期北向个股持股**——数据源已断。机构活跃度北向维度只能用`hsgt_top10`(每日十大成交net_amount, ts_raw_hsgt_top10, 收盘后公布, 近期数据正常)。

### Key Learnings (续)
- **(2026-07-02) Tushare hk_hold exchange参数** — 值是'SH'/'SZ'/'HK'(非'SSE'/'SZSE'/'HKEX')。不传exchange默认返回南向港股(.HK)。北向(SH/SZ)2024-08后空(政策停)。之前3轮把hk_holdings当"北向code损坏"修是误判, 真相=南向+北向政策停止。

### Do-Not-Repeat (续)
- **(2026-07-02 终极结论) 北向个股资金流 2024-08 全面停止, 勿再尝试** — 实测4个接口: ①hk_hold北向(SH/SZ)2024-07起空; ②hsgt_top10 net_amount/buy/sell 近期**全NULL**(只剩上榜名单ts_code/name); ③stock_hsgt只有标的分类无持股量。**Tushare全权限也拿不到2024-08后的北向个股资金流**(交易所2024-08-19停止披露)。机构活跃度"北向个股"维度在当前数据源下**不可实现**, 已永久放弃改用5维(龙虎榜机构+户数+大宗+研报+增减持)。moneyflow_hsgt(北向总量)仍可用但只作宏观市场环境, 非个股。如必须做北向个股: 需采购第三方估算数据(如韭菜网/某些券商研报的北向估算), Tushare无解。

### Key Learnings (续)
- **(2026-07-02) 机构活跃度已固化 tools/institutional_activity_top.py** — 5维percentile加权(龙虎榜机构净买40%+天数10%+户数筹码集中20%+大宗10%+研报15%+增减持5%), 北向弃用。3个接口: ①`calc_top(top_n)` 全市场Top(批量, 启动算一次); ②`score_for(code)` 单股明细(**性能注意:每次全市场重算, 仅适合单股诊断如diagnosis-service, 切勿逐股批量调用**); ③`enrich_picks(codes)` 给候选列表标注(午后选股交叉, 一次calc_top后O(1)查)。午后选股集成用 calc_top 生成 dict 启动时算一次, score_stock里 INST.get(code,0)*0.10。
- **(2026-07-02) 午后选股×机构活跃度交叉发现**: 午后A级候选里 002842翔鹭钨业(机构分42)+002378章源钨业(36) 有"机构净买"背书=技术面+机构资金双共振; 但黄金股(000975/600988)机构分仅16-19(游资行情机构少), 多只化工中小盘(605020/002326)无机构数据。→ 机构活跃度维度天然偏向机构参与的中大盘股, 题材游资股覆盖少, 用作"机构背书确认"而非主筛。
- **(2026-07-02) sync_hk_hold docstring已修正** — 原"north-bound"误导(实际南向港股通), 改为注明exchange参数(SH/SZ北向/HK南向)+北向2024-08停止。etl.py:443。

### Do-Not-Repeat (续)
- **(2026-07-02) 机构活跃度因子 IC正但Top组追高回落, 勿基于IC盲目做多Top** — 月频IC回测36月: Rank IC均值+0.056/ICIR0.54/胜率70.6%(看似有效), **但分组多空Top-Bot年化-52.3%**(Top组+0.69%/月 vs Bot组+5.00%/月)。原因: 机构活跃度极高=龙虎榜热门/游资接力=短期高点, 20日均值回归。**因子非线性: 中间段IC正但极端高分段反转**。结论: 不能单边做多Top(年化-52%); 适合作组合/共振/剔除因子, 不单独选股。Bot组(低机构活跃)+5%/月需查可交易性(流动性/幸存者偏差)。呼应[[bi-trend-net-backtest-finding]]教训: "看起来好但样本外亏", IC指标有欺骗性, 必须看分组多空方向。

### Key Learnings (续)
- **(2026-07-02) 因子回测判定必须结合IC+分组方向** — backtest_institutional_activity.py 判定逻辑已修正: ICIR>0.5且胜率>55%且多空>0 → 可做多; ICIR>0.5但多空<0 → "有信息量但极端值反转, 不能单边做多"。单看IC会误判(本次IC+0.056/70%胜率但实际做多亏-52%)。月频IC回测脚本tools/backtest_institutional_activity.py, 复用calc_top截面+daily_kline前向收益。
