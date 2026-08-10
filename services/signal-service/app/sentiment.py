"""市场情绪指数 — 纯评分函数 (无 IO, 便于单测).

设计依据: docs/design/New design/01 PRD 文档/1.1 智能看板-市场情绪详细设计.md
- 等级: 极牛/偏牛/中性/偏熊/极熊/黑天鹅 (score>=80/60/40/20 分档, 风险维度<20 强制黑天鹅)
- 八维权重: 趋势25 + 广度20 + 流动性15 + 杠杆10 + 外资5 + 估值5 + 风险15 + 情绪5
- 预警: 过热 score>=80 / 冰点 score<=20 / 急转 |change|>=20
路由与数据装配见 app/routers/sentiment.py。
"""

from __future__ import annotations

# ── 八维定义: key → (中文 label, 权重) — 与 market_regime_v2 / PRD 对齐 ──
DIMENSION_DEFS: dict[str, tuple[str, float]] = {
    "trend": ("趋势", 0.25),
    "breadth": ("广度", 0.20),
    "liquidity": ("流动性", 0.15),
    "leverage": ("杠杆", 0.10),
    "foreign": ("外资", 0.05),
    "valuation": ("估值", 0.05),
    "risk_events": ("风险", 0.15),
    "sentiment": ("情绪", 0.05),
}

# ── 等级配置: label / 操作基调 / 仓位建议 (PRD §4.2) ──
LEVEL_CONFIG: dict[str, dict] = {
    "BULL": {
        "label": "极牛",
        "hint": "市场过热，短期回调风险增大。建议逐步降低仓位，锁定利润，严格止损。",
        "position": "3-5 成",
    },
    "NEUTRAL_BULL": {
        "label": "偏牛",
        "hint": "市场偏牛，关注强势板块趋势延续机会。控制仓位在 7-8 成，警惕情绪过热。",
        "position": "7-8 成",
    },
    "NEUTRAL": {
        "label": "中性",
        "hint": "市场中性，以精选个股为主。关注结构性机会，波段操作，不宜追涨杀跌。",
        "position": "5-6 成",
    },
    "NEUTRAL_BEAR": {
        "label": "偏熊",
        "hint": "市场偏弱，以防御为主。降低仓位至 3-4 成，关注低估值防御性板块。",
        "position": "3-4 成",
    },
    "BEAR": {
        "label": "极熊",
        "hint": "市场极熊，恐慌蔓延。建议轻仓或空仓观望，等待企稳信号。现金为王。",
        "position": "0-2 成",
    },
    "BLACK_SWAN": {
        "label": "黑天鹅",
        "hint": "⚠️ 黑天鹅事件触发！系统性风险升高，市场可能大幅波动。建议立即减仓，回避风险。",
        "position": "0-1 成",
    },
}

# ── 预警阈值 (PRD §3 预警指示灯) ──
ALERT_THRESHOLDS = {"overheat": 80, "ice_point": 20, "sharp_reversal": 20}


def clamp_score(value: float) -> float:
    """夹取到 0-100 并保留 1 位小数."""
    return round(max(0.0, min(100.0, float(value))), 1)


def score_to_level(score: float, risk_score: float | None = None) -> str:
    """score → 情绪等级. 风险维度 < 20 时强制 BLACK_SWAN (与 regime_v2 一致)."""
    if risk_score is not None and risk_score < 20:
        return "BLACK_SWAN"
    if score >= 80:
        return "BULL"
    if score >= 60:
        return "NEUTRAL_BULL"
    if score >= 40:
        return "NEUTRAL"
    if score >= 20:
        return "NEUTRAL_BEAR"
    return "BEAR"


def level_label(level: str) -> str:
    return LEVEL_CONFIG.get(level, LEVEL_CONFIG["NEUTRAL"])["label"]


def operation_hint(level: str) -> dict:
    """操作基调 + 仓位建议 (PRD §4.2)."""
    cfg = LEVEL_CONFIG.get(level, LEVEL_CONFIG["NEUTRAL"])
    return {"hint": cfg["hint"], "position": cfg["position"]}


def combine_dimensions(dimensions: dict[str, float | None]) -> float | None:
    """八维加权合成总分 (0-100).

    缺失维度 (None) 不参与加权, 权重按可用维度归一化;
    全部缺失返回 None (调用方应视为 insufficient_data, 不得当中性 50).
    """
    total_weight = 0.0
    weighted = 0.0
    for key, (_, weight) in DIMENSION_DEFS.items():
        value = dimensions.get(key)
        if value is None:
            continue
        weighted += float(value) * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return clamp_score(weighted / total_weight)


def derive_daily_score(
    avg_chg: float,
    up_count: int,
    down_count: int,
    total: int,
    limit_up: int = 0,
    limit_down: int = 0,
) -> float:
    """由单日全市场聚合数据推导情绪分 (0-100) — 确定性纯函数.

    分量:
      - 动量 (50%): avg_chg 经 (x+3)/6×100 归一化 (沿用 dashboard-summary 映射)
      - 广度 (35%): 上涨家数占比 ×100
      - 涨跌停 (15%): 涨停/(涨停+跌停+1) ×100
    全跌 → ~0 (极熊/冰点), 全涨 → ~100 (极牛/过热).
    """
    momentum = clamp_score((float(avg_chg) + 3.0) / 6.0 * 100.0)
    breadth = (float(up_count) / total * 100.0) if total > 0 else 50.0
    limit_ratio = float(limit_up) / (float(limit_up) + float(limit_down) + 1.0) * 100.0
    return clamp_score(momentum * 0.50 + breadth * 0.35 + limit_ratio * 0.15)


def build_alerts(score: float, change: float, trade_date: str | None = None) -> list[dict]:
    """三类情绪预警: 过热 / 冰点 / 急转 (PRD SentimentAlert).

    返回固定 3 条 (triggered 标记是否触发), 未触发时 level=info.
    """
    t = ALERT_THRESHOLDS
    rules = [
        ("overheat", "过热", score >= t["overheat"], "danger",
         f"score >= {t['overheat']}",
         f"市场情绪过热 (score={score:.1f} ≥ {t['overheat']})，短期回调风险增大，建议降低仓位锁定利润。"),
        ("ice_point", "冰点", score <= t["ice_point"], "warning",
         f"score <= {t['ice_point']}",
         f"市场情绪冰点 (score={score:.1f} ≤ {t['ice_point']})，恐慌蔓延，关注超跌反弹与企稳信号。"),
        ("sharp_reversal", "急转", abs(change) >= t["sharp_reversal"], "warning",
         f"|change| >= {t['sharp_reversal']}",
         f"情绪急转 (单日变化 {change:+.1f}，阈值 ±{t['sharp_reversal']})，市场方向突变，注意风控。"),
    ]
    alerts = []
    for alert_type, name, triggered, level, threshold, message in rules:
        alerts.append({
            "type": alert_type,
            "name": name,
            "level": level if triggered else "info",
            "message": message if triggered else f"{name}预警未触发 (阈值 {threshold})。",
            "triggered": triggered,
            "threshold": threshold,
            "current_value": round(change if alert_type == "sharp_reversal" else score, 1),
            "time": trade_date,
        })
    return alerts
