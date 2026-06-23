"""毕师傅趋势启动战法 — 可调参数集中模块（M15 拆分，原 bi_trend_launch.py:28-241）.

audit-model-2026-06-22 §M15：bi_trend_launch.py 2168 行单文件违反单一职责，
其中 ~210 行纯参数常量与因子/评分/选股逻辑混在一起，使 M02/M09 过拟合治理
需 grep 全文确认副作用。本模块把全部可调参数抽离集中。

标注约定（与 M02/M09 一致）：
  - `# DEPRECATED: in-sample anecdote (M09)` — 单股事件反推的阈值，保留数值
    但标明非学术默认，待 walk-forward 校准（具体标的见审计报告，代码保持中性）。
  - Vxx 注释为版本演化史，保留以便追溯调参路径（M02 禁止再基于 6 月调参，
    但历史注释允许保留作决策记录）。

bi_trend_launch.py 通过 `from kronos_factors.engine.params import *` re-export
保持向后兼容（外部 `from bi_trend_launch import WEIGHTS` 不破）。
"""

#    V5.3: 降低止损率 - 连阳确认 + 深度回踩 + 派发检测
# V6.0 权重再平衡 (回测驱动: S级悖论修复)
# OBV 30->22 (减动量) | WR 28->30 (增回踩质量) | Vol 8->10 | Freshness 3->5
WEIGHTS = {
    "obv_trend": 22,            # V6.0: 30->22 (大幅降权, 减少追高依赖)
    "wr_pullback": 30,          # V6.0: 28->30 (回踩质量比趋势长度更重要)
    "volume_contract": 15,      # V10: 10→15 (缩量是大涨前最一致信号)
    "ma_trend": 10,             # 不变
    "trend_strength": 8,        # 不变
    "sector_momentum": 7,       # 不变
    "freshness": 5,             # V6.0: 3->5 (新鲜回踩=更高安全边际)
    "rebound_strength": 3,      # 不变
    "obv_accel": 3,             # 不变
    "hard_tech_track": 3,       # 不变
    "chokepoint_scarcity": 2,   # 不变
    "short_pullback": 3,        # V7.0: 1-2天短回调加分 (72%暴涨前兆)
    # V10: 移除 momentum_continue — 我们要的是启动, 不是延续
    "range_position": 3,        # V8.0: 区间底部加分 (弹簧压缩)
    "ignition": 4,              # V8.0: 点火检测加分 (放量金叉)
    "coiling": 3,               # V8.0: 蓄力检测加分 (点火后缩量横盘)
}

#    V5.8: 硬科技 + 卡脖子筛选 (国家鼓励方向)
HARD_TECH_ONLY = True  # 默认开启硬科技门控

# 硬科技行业关键词 与 advanced_factors.py HARD_TECH_KEYWORDS 对齐 轻量纯字符串匹配
HARD_TECH_INDUSTRY_KW = [
    # AI算力
    "算力", "光模块", "服务器", "AI芯片", "GPU", "CPO", "HBM", "数据中心", "智算",
    # 半导体
    "半导体", "芯片", "集成电路", "晶圆", "光刻", "EDA", "封装", "测试", "存储", "碳化硅",
    # 机器人/智造
    "机器人", "伺服", "减速器", "具身智能", "机器视觉", "传感器", "丝杠",
    # 锂电储能
    "锂电池", "锂电", "储能", "固态电池", "逆变器", "充电桩", "新能源车",
    # 信创国产
    "国产OS", "数据库", "工业软件", "信创", "国产替代", "操作系统", "中间件",
    # 低空经济
    "无人机", "eVTOL", "空管", "低空", "通航", "航天", "卫星",
    # 显示面板
    "OLED", "面板", "MLED", "MiniLED", "MicroLED", "液晶",
    # 通信
    "通信", "5G", "光通信", "光纤", "基站",
    # 新材料
    "新材料", "碳纤维", "复合材料", "电子化学品", "特种", "精密", "稀土",
    # 医药生物
    "创新药", "医疗器械", "生物", "基因",
    # 军工
    "军工", "航空",
    # 工业母机
    "数控", "精密制造",
]
HARD_TECH_TRACK_WEIGHT = 3     # 硬科技赛道额外加分 (满分3)
CHOKEPOINT_SCARCITY_WEIGHT = 2  # 卡脖子稀缺性加分 (满分2)

GRADE_THRESHOLDS = {"S": 70, "A": 55, "B": 40}
MIN_OBV_DAYS = 3             # V6.0: 2->3, 数据驱动
MIN_TREND_20D = 0
OBV_NEGATIVE_SKIP = True      # DEPRECATED: in-sample anecdote (原个股事件反推, M09).
                               # 学术默认 (OBV<0 即资金净流出跳过) 合理, 保留数值但待 walk-forward 校准.
                               # V7.0: OBV负值直接跳过 (长期资金流出=信号失效)
SHORT_PULLBACK_BONUS = 3      # V7.0: 1天短回调加分 (72%暴涨前兆)
# V10: 移除 MOMENTUM_BONUS — 奖励启动非延续
RANGE_POSITION_BONUS = 3      # V8.0: 区间底部加分 (收盘在14日区间底部25%)
IGNITION_BONUS = 4            # V8.0: 点火检测 (3-5天前放量>2x+金叉)
COILING_BONUS = 3             # V8.0: 蓄力检测 (点火后缩量横盘2-3天)
IGNITION_LOOKBACK_START = 3   # V8.0: 点火回溯起始天数
IGNITION_LOOKBACK_END = 6     # V8.0: 点火回溯结束天数
IGNITION_VOL_MIN = 2.0        # V8.0: 点火最小量比
COILING_VOL_MAX = 0.7         # V8.0: 蓄力最大量比
COILING_PRICE_CHG_MAX = 2.0   # V8.0: 蓄力最大价格波动(%)

# V12.1: 高波动股过滤器 (年化波动>100%的股票信号完全失效)
# DEPRECATED (M09): 下列倍率/阈值由单股事件反推, 为 in-sample anecdote (具体标的见审计报告, 不在此列出以保持代码中性).
# 学术默认方向: 高波动 → 信号衰减 (保留), 但具体倍率 0.3/0.5/0.6/0.7 待 walk-forward 校准.
HIGH_VOL_ANNUAL = 80            # 高波动阈值 (>80%年化波动 → 信号衰减)
EXTREME_VOL_ANNUAL = 100        # 极端波动阈值 (>100%年化波动 → 信号大幅衰减)
HIGH_VOL_OBV_MULT = 0.6         # 高波动OBV倍率 (DEPRECATED: anecdote, M09)
HIGH_VOL_WR_MULT = 0.7          # 高波动WR倍率  (DEPRECATED: anecdote, M09)
EXTREME_VOL_OBV_MULT = 0.3      # 极端波动OBV倍率 (DEPRECATED: anecdote, M09)
EXTREME_VOL_WR_MULT = 0.5       # 极端波动WR倍率  (DEPRECATED: anecdote, M09)
# V12.1: WR极值+点火反转 (WR>=95时点火=顶部出货信号, 非蓄力)
WR_EXTREME_IGNITION = 95        # WR极值阈值
WR_EXTREME_IGNITION_PENALTY = 8 # 极值点火惩罚分 (DEPRECATED: anecdote, M09)
# V12.1: WR高位缩量要求 (WR>80时放量=出货嫌疑, 缩量要求收紧)
WR_HIGH_VOL_THRESHOLD = 0.85    # WR>80时的缩量要求 (DEPRECATED: anecdote, M09)
WR_HIGH_VOL_PENALTY = 5         # 放量出货惩罚分 (DEPRECATED: anecdote, M09)
STRONG_WR_DROP = 20         # V6.0: -25->-20, 轻踩优于深踩
STRONG_OBV_DAYS = 7          # V6.0: 10->7, Sharpe分界线
HOLD_OBV_DAYS = 15           # V6.0: 持有信号
SELL_OBV_BELOW_DAYS = 2      # V6.0: 下穿MA10清仓
TIME_STOP_DAYS = 10          # V6.0: 时间止损
TIME_STOP_MIN_RET = 2.0      # V6.0: 最低收益%

# V5.1: 追高惩罚
# V6.0: 梯度追高惩罚 (修复S级悖论)
# 回测: S级胜率29% vs A级52%, 根因=OBV超15天仍高分追高
CHASE_PENALTY_OBV_DAYS_EXTREME = 20   # 极度追高
CHASE_PENALTY_OBV_DAYS_HIGH = 15      # 明显追高 (原18)
CHASE_PENALTY_OBV_DAYS_MILD = 12      # 轻度追高 (新增)
CHASE_PENALTY_WR_THRESHOLD = 45      # WR回踩不足阈值
CHASE_PENALTY_WR_EXTREME = 50        # 极度追高WR阈值
CHASE_PENALTY_SCORE = 8               # 明显追高扣分
CHASE_PENALTY_SCORE_EXTREME = 12      # 极度追高扣分
CHASE_PENALTY_SCORE_MILD = 4          # 轻度追高扣分

# V5.1: 回踩新鲜度
FRESH_PULLBACK_DAYS = 2
FRESH_PULLBACK_BONUS = 3

# V5.1: 反弹量能确认
REBOUND_VOL_MIN_RATIO = 0.9

# V5.2: 入场精细化
REBOUND_STRONG_GAIN = 2.0
REBOUND_STRONG_BONUS = 3        # 2->3
DEAD_CAT_BOUNCE_DAYS = 3
DEAD_CAT_MIN_DROP = -1.5
EARLY_STOP_LOSS_DAYS = 3
EARLY_STOP_LOSS_PCT = -12
DAY3_CHECK_LOSS_THRESHOLD = -10  # <-10%才需干预, 否则全是误杀

# V5.3: 方向A - 连阳确认 (防一日游)
CONSECUTIVE_UP_DAYS = 2          # 需要连续N天收阳 (反弹确认非一日游)
CONSECUTIVE_UP_BONUS = 2         # 连阳加分

# V5.3: 方向B - WR深度要求 (更深回踩=更大反弹空间)
MIN_WR_DEPTH_FOR_BUY = 50       # buy/strong_buy信号WR必须低于此值
MIN_WR_DEPTH_FOR_WATCH = -35     # watch信号WR低于此值即可

# V5.3: 方向C - MA20距离过滤 (防追高空中加油)
MA20_EXTENSION_MAX = 1.15        # 价格/MA20 < 此值 (不超过MA20的15%)

# V5.3: 方向D - 派发量检测 (最大量日为阴线=主力出货)
DISTRIBUTION_LOOKBACK = 5        # 近N日检测
DISTRIBUTION_PENALTY = 5         # 派发嫌疑降分

# V5.2: buy分层
BUY_PREMIUM_CONDITIONS = ["_fresh", "_rebound", "!_chase"]

# V5.2: 大盘预警 (保留)
MARKET_BREADTH_CRASH = 18
MARKET_BREADTH_WEAK = 25             # DEPRECATED: in-sample anecdote (原 35→25 单股事件反推, M09).
                                       # 学术默认 35 (1/3 涨跌比为弱市分界), 待 walk-forward 校准.
POST_CRASH_SKIP_BREADTH = 30
PRE_WARNING_BREADTH_DROP = 40
CONSECUTIVE_DROP_DAYS = 2
SH_INDEX_MA_DAYS = 20
WEAK_BREADTH_5D = 35
BEAR_BREADTH_5D = 30
MIN_HOLD_DAYS = 5

# V5.4: 10日涨跌比均线 - 仅用于仓位管理, 不再熔断
MIDTERM_BREADTH_WINDOW = 10       # 10日滚动窗口
MIDTERM_BREADTH_BEAR = 42         # 10日均涨跌比<42% -> 弱市/减仓
MIDTERM_BEAR_RECOVERY_DAILY = 50  # 单日涨跌比>此值 + 10日均>RECOVERY_10D -> 恢复
MIDTERM_BEAR_RECOVERY_10D = 48    # 10日均涨跌比恢复阈值

# V5.7: 周线趋势确认 - 仅惩罚逆势, 不奖励顺势(好股已自证)
WEEKLY_MA_PERIOD = 50           # MA50   10周线
WEEKLY_BEARISH_PENALTY = 6      # 周线空头惩罚 (price<MA50 AND MA50下降)
WEEKLY_SLOPE_LOOKBACK = 10      # MA50斜率检测窗口

# V5.6 P1续: 动态仓位管理 - 市场环境 -> Top-N, 信号质量 -> 权重
# 市场五档 -> 选股数量比例
POSITION_REGIME = {
    "bull":       1.0,    # 10日均>55%: 满仓
    "neutral":    0.7,    # 10日均 48-55%: 7成仓
    "weak":       0.4,    # 10日均 42-48%: 4成仓
    "recovery":   0.3,    # 刚从熊市恢复: 3成仓试探
    "bear":       0.3,    # 已废弃 (不再熔断, 统一用weak)
}
# 信号质量 -> 仓位权重 (叠加市场档位)
SIGNAL_WEIGHT = {
    "strong_buy":     1.0,
    "buy_premium":    0.8,
    "buy_standard":   0.6,
    "buy_weak":       0.3,
    "S_watch":        0.5,
    "A_watch":        0.3,
    "B_watch":        0.0,
}

# V5.3: 卖出优化 - 止损硬上限 + 时间止损
SELL_STOP_LOSS_BASE = -10
SELL_STOP_ATR_MULT = 1.5
SELL_MAX_STOP_LOSS = -15          # V5.3: 止损硬上限 (防-22%极端亏损)
SELL_TIME_STOP_DAYS = 5           # V5.3: 持有N天仍亏损+无改善 -> 时间止损
SELL_TIME_STOP_THRESHOLD = -5     # -3%太紧, 日内波动就触发

# V5.5 P1: 五档分级移动止盈 - 盈利越大止盈越宽, 让牛股跑远
SELL_TRAILING_TIER1_PROFIT = 5    # 盈利<5% -> Tier1
SELL_TRAILING_TIER1_STOP = -7     # -7% (刚起步, 给空间)
SELL_TRAILING_TIER2_PROFIT = 15   # 盈利5-15% -> Tier2
SELL_TRAILING_TIER2_STOP = -5     # -5% (标准保护)
SELL_TRAILING_TIER3_PROFIT = 30   # V5.5: 盈利15-30% -> Tier3
SELL_TRAILING_TIER3_STOP = -5     # V5.5: -5% (不过早截断)
SELL_TRAILING_TIER4_PROFIT = 60   # V5.5: 盈利30-60% -> Tier4
SELL_TRAILING_TIER4_STOP = -8     # V5.5: -8% (让趋势跑)
SELL_TRAILING_TIER5_STOP = -12    # V5.5: 盈利>60% -> -12% (超级牛股, 给足空间)
SELL_TAKE_PROFIT_FIXED = 15       # 固定止盈+15% (保留, 但移动止盈优先)

# V5.9 P4: 弱市快进快出 - 弱市/中性市场缩短持仓周期
# 6月回测: T+1胜率50%均值+0.86%, T+3胜率降至37.5%
WEAK_MARKET_TAKE_PROFIT = 5.0     # 弱市止盈目标 (快进快出)
WEAK_MARKET_STOP_LOSS = -5.0      # 弱市止损线 (更紧)

# 向后兼容别名
SELL_STOP_LOSS = SELL_STOP_LOSS_BASE
SELL_TRAILING_STOP = SELL_TRAILING_TIER2_STOP
SELL_TRAILING_STOP_TIGHT = SELL_TRAILING_TIER3_STOP  # now -5%
TRAILING_PROFIT_THRESHOLD = SELL_TRAILING_TIER2_PROFIT

WEAK_MARKET_S_ONLY = True
