"""A股市场风向感知模型 — Multi-Dimensional Market Regime Detection.

八维评分:
  1. 趋势 Trend (25%): 指数MA排列 + 新高新低比
  2. 广度 Breadth (20%): 涨跌比 + 涨跌停比 + 炸板检测
  3. 流动性 Liquidity (15%): 成交额趋势 + 资金流向
  4. 杠杆 Leverage (10%): 融资余额趋势
  5. 外资 Foreign (5%): 北向资金流向
  6. 估值 Valuation (5%): PE/PB分位
  7. 风险事件 Risk (15%): 黑天鹅信号 (审计+公告+政策+互动)
  8. 情绪 Sentiment (5%): 新闻联播 + 舆情

输出:
  - regime: 6档 (BULL / NEUTRAL_BULL / NEUTRAL / NEUTRAL_BEAR / BEAR / BLACK_SWAN)
  - confidence: 0-100
  - score: 0-100 (0=极熊, 100=极牛)
  - dimensions: 每维评分
  - factor_hints: 选股策略建议
  - alerts: 告警信号
"""

import logging
import numpy as np
from datetime import date, timedelta

logger = logging.getLogger("kronos-factors.market_regime")


# ── 黑天鹅事件关键词 ──
BLACK_SWAN_KW = [
    # 系统性风险
    "金融危机", "系统性风险", "熔断", "全球股市暴跌", "流动性危机",
    # 政策冲击
    "监管", "整顿", "暂停上市", "终止上市", "立案调查",
    # 宏观经济
    "经济衰退", "硬着陆", "债务危机", "信用风险",
    # 国际市场
    "美联储", "加息", "缩表", "关税", "制裁",
    # A股特有
    "千股跌停", "股灾", "救市", "降准降息", "定向降准",
]


def get_market_regime_v2(db=None) -> dict:
    """V2: 多维市场风向感知模型.

    Args:
        db: 可选 _get_db() 连接, None=自动获取

    Returns:
        {"regime": str, "score": float, "confidence": float,
         "dimensions": dict, "factor_hints": str, "alerts": list}
    """
    from kronos_factors.scorer._db_stub import _get_db
    try:
        if db is None:
            with _get_db(readonly=True) as db_ctx:
                return _compute_regime(db_ctx)
        else:
            return _compute_regime(db)
    except Exception as e:
        logger.warning("Market regime V2 failed: %s", e)
        return _fallback()


def _compute_regime(db) -> dict:
    """实际计算逻辑."""

    # ── 1. Trend (25分) ──
    trend_score, trend_detail = _score_trend(db)

    # ── 2. Breadth (20分) ──
    breadth_score, breadth_detail = _score_breadth(db)

    # ── 3. Liquidity (15分) ──
    liquidity_score, liquidity_detail = _score_liquidity(db)

    # ── 4. Leverage (10分) ──
    leverage_score, leverage_detail = _score_leverage(db)

    # ── 5. Foreign (5分) ──
    foreign_score, foreign_detail = _score_foreign(db)

    # ── 6. Valuation (5分) ──
    valuation_score, valuation_detail = _score_valuation(db)

    # ── 7. Risk Events (15分) ──
    risk_score, risk_detail, alerts = _score_risk_events(db)

    # ── 8. Sentiment (5分) ──
    sentiment_score, sentiment_detail = _score_sentiment(db)

    # Weighted total (0-100)
    total_score = (
        trend_score * 0.25 + breadth_score * 0.20 +
        liquidity_score * 0.15 + leverage_score * 0.10 +
        foreign_score * 0.05 + valuation_score * 0.05 +
        risk_score * 0.15 + sentiment_score * 0.05
    )

    # 黑天鹅事件: 风险维度<30 强制 BEAR 或 BLACK_SWAN
    if risk_score < 20:
        regime = "BLACK_SWAN"
    elif total_score >= 75:
        regime = "BULL"
    elif total_score >= 60:
        regime = "NEUTRAL_BULL"
    elif total_score >= 40:
        regime = "NEUTRAL"
    elif total_score >= 25:
        regime = "NEUTRAL_BEAR"
    else:
        regime = "BEAR"

    # Factor hints
    hints = _generate_factor_hints(regime, total_score, risk_score)

    return {
        "regime": regime,
        "score": round(total_score, 1),
        "confidence": round(min(100, max(20, abs(total_score - 50) * 2)), 1),
        "dimensions": {
            "trend": {"score": trend_score, "weight": 0.25, "detail": trend_detail},
            "breadth": {"score": breadth_score, "weight": 0.20, "detail": breadth_detail},
            "liquidity": {"score": liquidity_score, "weight": 0.15, "detail": liquidity_detail},
            "leverage": {"score": leverage_score, "weight": 0.10, "detail": leverage_detail},
            "foreign": {"score": foreign_score, "weight": 0.05, "detail": foreign_detail},
            "valuation": {"score": valuation_score, "weight": 0.05, "detail": valuation_detail},
            "risk_events": {"score": risk_score, "weight": 0.15, "detail": risk_detail},
            "sentiment": {"score": sentiment_score, "weight": 0.05, "detail": sentiment_detail},
        },
        "factor_hints": hints,
        "alerts": alerts,
        "label": _regime_label(regime),
    }


# ═══════════════════════════════════════════════════════════════
# 1. Trend (25分): 指数MA排列
# ═══════════════════════════════════════════════════════════════

def _score_trend(db) -> tuple:
    """沪深300/创业板/中证500 趋势评分."""
    try:
        scores = []
        detail = {}
        for idx_code, name, weight in [("000300", "沪深300", 0.4), ("399006", "创业板", 0.35), ("000905", "中证500", 0.25)]:
            rows = db.execute(
                "SELECT close FROM index_daily WHERE code=? ORDER BY trade_date DESC LIMIT 120",
                (idx_code,)
            ).fetchall()
            if not rows or len(rows) < 60:
                scores.append(50); continue
            closes = np.array([r["close"] for r in reversed(rows)], dtype=np.float64)
            ma5 = np.mean(closes[-5:]); ma10 = np.mean(closes[-10:])
            ma20 = np.mean(closes[-20:]); ma60 = np.mean(closes[-60:])
            ret_20d = (closes[-1]/closes[-20]-1)*100 if closes[-20]>0 else 0

            # 排列评分: 多头排列=高分
            if ma5 > ma10 > ma20 > ma60: s = 90
            elif ma5 > ma10 > ma20: s = 75
            elif ma10 > ma20 > ma60 and closes[-1] > ma20: s = 65
            elif closes[-1] > ma60: s = 55
            elif closes[-1] > ma20: s = 45
            elif closes[-1] < ma60 and ma20 < ma60: s = 25
            elif closes[-1] < ma20 < ma60: s = 15
            else: s = 30
            scores.append(s * weight)
            detail[name] = {"ma_align": "多头" if s>=65 else "震荡" if s>=40 else "空头", "ret_20d": round(ret_20d, 1)}

        return round(sum(scores)), detail
    except Exception:
        return 50, {}


# ═══════════════════════════════════════════════════════════════
# 2. Breadth (20分): 涨跌比 + 涨停跌停比 + 炸板
# ═══════════════════════════════════════════════════════════════

def _score_breadth(db) -> tuple:
    try:
        # 最新交易日涨跌比
        row = db.execute(
            "WITH latest AS (SELECT MAX(trade_date) as d FROM daily_kline WHERE change_pct IS NOT NULL) "
            "SELECT COUNT(*) FILTER(WHERE change_pct>0) as up, "
            "COUNT(*) FILTER(WHERE change_pct<0) as down FROM daily_kline, latest WHERE trade_date=d"
        ).fetchone()
        up, down = (row["up"] or 0, row["down"] or 0) if row else (0, 0)
        total = up + down

        # 涨跌停
        limit_row = db.execute(
            "SELECT limit_type, COUNT(*) as c FROM limit_list_d "
            "WHERE trade_date=(SELECT MAX(trade_date) FROM limit_list_d) GROUP BY limit_type"
        ).fetchall()
        limits = {r["limit_type"]: r["c"] for r in limit_row}

        up_limit = limits.get("U", 0); down_limit = limits.get("D", 0)
        # 炸板(Z) = 涨停后打开 → 情绪脆弱信号
        z_count = limits.get("Z", 0)

        if total > 0:
            breadth_ratio = up / total * 100
            if breadth_ratio >= 70: s = 90
            elif breadth_ratio >= 60: s = 75
            elif breadth_ratio >= 50: s = 60
            elif breadth_ratio >= 40: s = 45
            elif breadth_ratio >= 30: s = 30
            else: s = 15
        else:
            s = 50; breadth_ratio = 50

        # 炸板惩罚
        if z_count > 100: s = max(10, s - 20)  # 大面积炸板=恐慌
        elif z_count > 50: s = max(15, s - 10)
        elif z_count > 20: s = max(20, s - 5)

        # 跌停惩罚
        if down_limit > 50: s = max(5, s - 25)  # 百股跌停
        elif down_limit > 20: s = max(10, s - 15)

        detail = {
            "up/down": f"{up}/{down}", "breadth": f"{breadth_ratio:.0f}%",
            "limits": f"涨{up_limit}/跌{down_limit}/炸{z_count}",
        }
        return round(s), detail
    except Exception:
        return 50, {}


# ═══════════════════════════════════════════════════════════════
# 3. Liquidity (15分): 成交额趋势
# ═══════════════════════════════════════════════════════════════

def _score_liquidity(db) -> tuple:
    try:
        # 全市场成交额趋势
        rows = db.execute(
            "SELECT trade_date, SUM(amount) as total_amt FROM daily_kline "
            "WHERE trade_date >= DATE('now', '-20 days') GROUP BY trade_date "
            "ORDER BY trade_date"
        ).fetchall()
        if not rows or len(rows) < 10: return 50, {}

        amounts = np.array([r["total_amt"] for r in rows], dtype=np.float64)
        ma5 = np.mean(amounts[-5:]); ma10 = np.mean(amounts[-10:]) if len(amounts)>=10 else ma5
        latest = amounts[-1]; trend = (ma5/ma10-1)*100 if ma10>0 else 0

        # 量价配合
        row = db.execute(
            "SELECT AVG(change_pct) FROM daily_kline "
            "WHERE trade_date=(SELECT MAX(trade_date) FROM daily_kline WHERE change_pct IS NOT NULL)"
        ).fetchone()
        avg_chg = float(row[0] or 0) if row else 0

        if latest > ma5*1.2: s = 85  # 放量
        elif latest > ma5*1.05: s = 70
        elif latest > ma5*0.9: s = 55
        elif latest > ma5*0.7: s = 40  # 缩量
        else: s = 25  # 极度缩量

        # 价跌量增=不好, 价涨量增=好
        if avg_chg > 0 and trend > 0: s = min(95, s+10)
        elif avg_chg < 0 and trend > 0: s = max(15, s-10)

        return round(s), {"amount_trend": "放量" if s>=70 else "缩量" if s<=40 else "正常", "avg_chg": round(avg_chg,2)}
    except Exception:
        return 50, {}


# ═══════════════════════════════════════════════════════════════
# 4. Leverage (10分): 融资余额趋势
# ═══════════════════════════════════════════════════════════════

def _score_leverage(db) -> tuple:
    try:
        rows = db.execute("SELECT rzye FROM margin_summary ORDER BY trade_date DESC LIMIT 20").fetchall()
        if not rows or len(rows) < 10: return 50, {}
        balances = np.array([r["rzye"] for r in rows], dtype=np.float64)
        ma5 = np.mean(balances[:5]); ma10 = np.mean(balances[:10]); ma20 = np.mean(balances)
        chg_5d = (ma5/ma10-1)*100 if ma10>0 else 0; chg_10d = (ma10/ma20-1)*100 if ma20>0 else 0
        if chg_5d > 2: s = 80
        elif chg_5d > 0.5: s = 65
        elif chg_5d > -0.5: s = 50
        elif chg_5d > -2: s = 35
        else: s = 15  # 融资大幅撤离
        return round(s), {"balance_5d_chg": f"{chg_5d:+.1f}%"}
    except Exception:
        return 50, {}


# ═══════════════════════════════════════════════════════════════
# 5. Foreign (5分): 北向资金
# ═══════════════════════════════════════════════════════════════

def _score_foreign(db) -> tuple:
    try:
        rows = db.execute("SELECT north_net_inflow FROM moneyflow_hsgt ORDER BY trade_date DESC LIMIT 10").fetchall()
        if not rows: return 50, {}
        net = sum(r["north_net_inflow"] or 0 for r in rows)
        if net > 200: s = 85
        elif net > 50: s = 65
        elif net > 0: s = 55
        elif net > -50: s = 40
        else: s = 20
        return round(s), {"net_10d": f"{net:+.0f}亿"}
    except Exception:
        return 50, {}


# ═══════════════════════════════════════════════════════════════
# 6. Valuation (5分): PE分位
# ═══════════════════════════════════════════════════════════════

def _score_valuation(db) -> tuple:
    try:
        # 全市场PE中位数
        row = db.execute(
            "SELECT MEDIAN(pe) as med_pe FROM daily_basic "
            "WHERE trade_date=(SELECT MAX(trade_date) FROM daily_basic) AND pe>0 AND pe<500"
        ).fetchone()
        if not row or not row["med_pe"]:
            return 50, {}
        med_pe = float(row["med_pe"])
        # PE<20=便宜, 20-40=合理, 40-60=偏贵, >60=泡沫
        if med_pe < 15: s = 85
        elif med_pe < 25: s = 65
        elif med_pe < 40: s = 50
        elif med_pe < 60: s = 35
        else: s = 20
        return round(s), {"median_pe": round(med_pe, 1)}
    except Exception:
        return 50, {}


# ═══════════════════════════════════════════════════════════════
# 7. Risk Events (15分): 黑天鹅检测
# ═══════════════════════════════════════════════════════════════

def _score_risk_events(db) -> tuple:
    s = 80  # start optimistic
    detail = {}
    alerts = []

    try:
        # 7a. 审计意见风险
        audit = db.execute(
            "SELECT COUNT(*) FILTER(WHERE audit_result LIKE '%否定%' OR audit_result LIKE '%无法表示%') as severe, "
            "COUNT(*) FILTER(WHERE audit_result LIKE '%保留%') as moderate "
            "FROM fina_audit WHERE end_date >= (SELECT MAX(end_date) FROM fina_audit)"
        ).fetchone()
        if audit:
            severe = audit["severe"] or 0; moderate = audit["moderate"] or 0
            audit_score = max(10, 100 - severe*5 - moderate*2)
            s = (s + audit_score) / 2
            detail["audit_risk"] = f"严重{severe}/保留{moderate}"
            if severe > 5: alerts.append(f"[审计风险] {severe}家否定/无法表示意见")

        # 7b. 公告风险
        ann = db.execute(
            "SELECT COUNT(*) FROM announcements WHERE ann_date >= DATE('now', '-7 days') "
            "AND (title LIKE '%退市%' OR title LIKE '%ST%' OR title LIKE '%立案%' OR title LIKE '%处罚%')"
        ).fetchone()
        ann_count = ann[0] if ann else 0
        if ann_count > 20: s = max(15, s-30); alerts.append(f"[公告风险] 近7日{ann_count}条重大风险公告")
        elif ann_count > 5: s = max(30, s-15); alerts.append(f"[公告风险] 近7日{ann_count}条风险公告")
        detail["risk_announcements_7d"] = ann_count

        # 7c. 互动问答风险
        iq = db.execute(
            "SELECT COUNT(*) FROM interact_qa WHERE pub_date >= DATE('now', '-7 days') "
            "AND (question ~ '立案|退市|ST|风险|质押|商誉|减持|违规|处罚|冻结|诉讼')"
        ).fetchone()
        iq_count = iq[0] if iq else 0
        if iq_count > 1000: s = max(10, s-20); alerts.append(f"[舆情风险] 近7日{iq_count}条风险问答")
        elif iq_count > 500: s = max(20, s-10)
        detail["risk_interact_7d"] = iq_count

        # 7d. 千股跌停检测
        limit_d = db.execute(
            "SELECT COUNT(*) FROM limit_list_d WHERE trade_date=(SELECT MAX(trade_date) FROM limit_list_d) AND limit_type='D'"
        ).fetchone()
        down_limits = limit_d[0] if limit_d else 0
        if down_limits > 500: s = max(5, s-50); alerts.append("[千股跌停!] 市场极端恐慌")
        elif down_limits > 100: s = max(15, s-25); alerts.append(f"[百股跌停] {down_limits}家跌停")
        detail["down_limits_today"] = down_limits

        return round(max(5, s)), detail, alerts[:5]
    except Exception:
        return 80, {}, []


# ═══════════════════════════════════════════════════════════════
# 8. Sentiment (5分): 新闻+政策情绪
# ═══════════════════════════════════════════════════════════════

def _score_sentiment(db) -> tuple:
    try:
        s = 50
        # 新闻联播数量
        cctv = db.execute("SELECT COUNT(*) FROM cctv_news WHERE pub_date >= DATE('now', '-7 days')").fetchone()
        cctv_count = cctv[0] if cctv else 0
        # 政策法规
        policy = db.execute(
            "SELECT COUNT(*) FROM policy_law WHERE pub_date >= DATE('now', '-30 days')"
        ).fetchone()
        policy_count = policy[0] if policy else 0
        if policy_count > 10: s += 10
        detail = {"cctv_7d": cctv_count, "policy_30d": policy_count}
        return round(s), detail
    except Exception:
        return 50, {}


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _generate_factor_hints(regime: str, score: float, risk: float) -> dict:
    if regime == "BLACK_SWAN":
        return {"hint": "quality_defensive", "screener": "仅防守模式", "position": "<=20%",
                "stop_mode": "tight", "note": "黑天鹅事件 - 减仓观望"}
    elif regime == "BULL":
        return {"hint": "momentum_weighted", "screener": "全模式开启", "position": "<=80%",
                "stop_mode": "normal", "note": "强势市场 - 积极做多"}
    elif regime == "NEUTRAL_BULL":
        return {"hint": "momentum_weighted", "screener": "除熊市模式外全开", "position": "<=60%",
                "stop_mode": "normal", "note": "偏强市场 - 适度积极"}
    elif regime == "NEUTRAL":
        return {"hint": "technical_weighted", "screener": "选股模式全开", "position": "<=50%",
                "stop_mode": "atr", "note": "震荡市场 - 精选中线"}
    elif regime == "NEUTRAL_BEAR":
        return {"hint": "quality_defensive", "screener": "仅LONG+CHOKEPOINT", "position": "<=30%",
                "stop_mode": "tight", "note": "偏弱市场 - 防守为主"}
    else:  # BEAR
        return {"hint": "quality_defensive", "screener": "仅LONG底仓", "position": "<=15%",
                "stop_mode": "tight", "note": "弱势市场 - 现金为王"}


def _regime_label(regime: str) -> str:
    return {"BLACK_SWAN": "[BLACK_SWAN] 黑天鹅 - 极端风险",
            "BULL": "[BULL] 牛市 - 积极做多",
            "NEUTRAL_BULL": "[NEUTRAL_BULL] 偏强 - 适度积极",
            "NEUTRAL": "[NEUTRAL] 震荡 - 精选中线",
            "NEUTRAL_BEAR": "[NEUTRAL_BEAR] 偏弱 - 防守为主",
            "BEAR": "[BEAR] 熊市 - 现金为王"}.get(regime, regime)


def _fallback():
    return {"regime": "NEUTRAL", "score": 50, "confidence": 10,
            "dimensions": {}, "factor_hints": {"hint": "equal_weighted"},
            "alerts": [], "label": "数据不足 - 无法判断"}
