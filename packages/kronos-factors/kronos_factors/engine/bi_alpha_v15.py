#!/usr/bin/env python3
"""毕师傅 V15 — 横截面多因子 alpha 选股引擎 (信号源根本重设).

背景
----
bi_trend (OBV+WR+ADX 技术规则) 样本外确定性亏 (Sharpe -3.178, 见 memory
phase1-sample-out-conclusion). V15 换信号源: 从无 alpha 的纯技术规则, 转向
阶段A IC 速测验证有 alpha 的横截面因子.

阶段A 结论 (硬科技池, 2024-2025, 20日前向 RankIC, 见
docs/superpowers/specs/2026-06-25-bi-alpha-v15-stage-a-ic-report.md):
  - 低换手反转  ICIR 0.422  (唯一稳健通过门控)
  - 低PB反转    ICIR 0.281  (边缘, 正IC月占比62%)
  - 营收增长    ICIR 0.271  (边缘, 数据修复后, 正IC月占比58%)
三因子互补: 反转(低换手) + 价值(低PB) + 成长(营收), 经典多因子框架.

设计
----
1. 硬科技池内对每只票算三因子横截面"百分位排名"(0-1, 高=预期涨).
2. 按 ICIR 归一化加权合成 composite (低换手 0.43 / 低PB 0.29 / 营收 0.28).
3. composite 分位映射 grade (S/A/B), 算年化波动定 vol_regime.
4. 复用 V14 风控 apply_v14_risk_controls (分散化+分级仓位+分级止损).

纪律 (M02/M09): 权重来自 2024-2025 ICIR 校准, 禁基于 6月/2026上半年调参.
任何"盈利"陈述必须先过 walk_forward 样本外关 (tools/walk_forward.py).
"""

import numpy as np

from kronos_factors.engine.bi_trend_launch import (
    _is_hard_tech_stock, _get_hard_tech_track, apply_v14_risk_controls,
)
from kronos_factors.engine.params import (
    HIGH_VOL_ANNUAL, EXTREME_VOL_ANNUAL, GRADE_THRESHOLDS,
)

# 阶段A ICIR 归一化权重 (低换手 0.422 / 低PB 0.281 / 营收 0.271 → 归一化).
# DEPRECATED-style 标注: 数值由 2024-2025 样本 ICIR 校准, 待更长样本 walk-forward 复校.
FACTOR_ICIR = {"turnover_inv": 0.422, "pb_inv": 0.281, "revenue_growth": 0.271}
_W_SUM = sum(FACTOR_ICIR.values())
FACTOR_WEIGHTS = {k: round(v / _W_SUM, 4) for k, v in FACTOR_ICIR.items()}  # ~0.43/0.29/0.28

# 财报发布滞后假设 (天): 截面日 T 只看 end_date <= T-90 的财报, 防前视 (与 IC 速测一致).
FIN_PUBLISH_LAG_DAYS = 90

# composite 分位 → grade 阈值 (分位制, 与 bi_trend 的总分制不同).
# S = 前15%, A = 前35%, B = 前60%, 其余淘汰.
GRADE_PCTL = {"S": 0.85, "A": 0.65, "B": 0.40}


def _annual_vol_regime(closes: np.ndarray) -> tuple:
    """年化波动 → vol_regime (供 V14 分级止损). 与 HIGH/EXTREME_VOL_ANNUAL 对齐."""
    if len(closes) < 21:
        return 50.0, "normal"
    rets = np.diff(closes[-21:]) / closes[-21:-1]
    rets = rets[np.isfinite(rets)]
    if len(rets) < 5:
        return 50.0, "normal"
    annual_vol = float(np.std(rets) * np.sqrt(252) * 100)
    if annual_vol > EXTREME_VOL_ANNUAL:
        regime = "extreme"
    elif annual_vol > HIGH_VOL_ANNUAL:
        regime = "high"
    else:
        regime = "normal"
    return round(annual_vol, 1), regime


def _pctile_ranks(values: dict) -> dict:
    """{code: raw_value} → {code: 百分位排名 0-1}. 高 raw → 高分位 (已统一为'高=预期涨')."""
    if not values:
        return {}
    codes = list(values.keys())
    arr = np.array([values[c] for c in codes], dtype=np.float64)
    order = arr.argsort()  # 升序
    ranks = np.empty(len(arr))
    ranks[order] = np.arange(len(arr))
    pct = ranks / max(1, len(arr) - 1)
    return {c: float(pct[i]) for i, c in enumerate(codes)}


def _load_factor_raw(db, trade_date: str, codes: set) -> dict:
    """取截面日各因子原始值 {factor: {code: value}}, 已统一为'高分=预期涨'.

    turnover_inv = -换手率 (低换手反转), pb_inv = -PB (低PB反转),
    revenue_growth = 营收同比 (高增长, 财报滞后90日防前视).
    """
    import datetime
    out = {"turnover_inv": {}, "pb_inv": {}, "revenue_growth": {}}

    # daily_basic: PB + 换手率
    for r in db.execute(
        "SELECT code, pb, turnover_rate FROM daily_basic WHERE trade_date=?",
        (trade_date,),
    ).fetchall():
        c = r["code"]
        if c not in codes:
            continue
        if r["pb"] and r["pb"] > 0:
            out["pb_inv"][c] = -float(r["pb"])
        if r["turnover_rate"] is not None:
            out["turnover_inv"][c] = -float(r["turnover_rate"])

    # financial_indicator: 营收增长 (end_date <= T-90, 防前视)
    td_dt = datetime.datetime.strptime(trade_date, "%Y-%m-%d").date()
    fin_cutoff = (td_dt - datetime.timedelta(days=FIN_PUBLISH_LAG_DAYS)).strftime("%Y-%m-%d")
    for r in db.execute(
        "SELECT DISTINCT ON (code) code, revenue_growth FROM financial_indicator "
        "WHERE end_date <= ? ORDER BY code, end_date DESC",
        (fin_cutoff,),
    ).fetchall():
        c = r["code"]
        if c in codes and r["revenue_growth"] is not None:
            out["revenue_growth"][c] = float(r["revenue_growth"])

    return out


def run_alpha_screening(db, trade_date, top_n=20, hard_tech_only=True):
    """毕师傅 V15 横截面多因子选股.

    Returns: (top_picks, all_scores, market_info) — 与 run_bi_screening 同签名,
    便于 walk_forward / 回测脚本统一调用.
    """
    # 硬科技池 (与 bi_trend 同口径)
    rows = db.execute(
        "SELECT code, name, industry FROM stocks WHERE is_st=0 AND name NOT LIKE '%ST%'"
    ).fetchall()
    if hard_tech_only:
        pool = [r for r in rows if _is_hard_tech_stock(r["industry"] or "")]
    else:
        pool = list(rows)
    codes = {r["code"] for r in pool}
    info_by_code = {r["code"]: r for r in pool}

    # 因子原始值 → 百分位排名 → ICIR 加权合成
    raw = _load_factor_raw(db, trade_date, codes)
    pct = {f: _pctile_ranks(raw[f]) for f in FACTOR_WEIGHTS}

    # 取价 (算波动率定 vol_regime); 复权用 daily_kline 原始 close 序列即可 (波动率比例对复权不敏感)
    scores = []
    for code in codes:
        # 至少 2 个因子有值才入选 (避免单因子噪音)
        fvals = {f: pct[f].get(code) for f in FACTOR_WEIGHTS}
        present = {f: v for f, v in fvals.items() if v is not None}
        if len(present) < 2:
            continue
        # 缺失因子用中位 0.5 填充 (中性), 加权合成
        composite = sum(FACTOR_WEIGHTS[f] * (fvals[f] if fvals[f] is not None else 0.5)
                        for f in FACTOR_WEIGHTS)

        # 波动率 (供分级止损)
        kl = db.execute(
            "SELECT close FROM daily_kline WHERE code=? AND trade_date<=? "
            "ORDER BY trade_date DESC LIMIT 30", (code, trade_date)
        ).fetchall()
        closes = np.array([float(r["close"]) for r in reversed(kl) if r["close"]], dtype=np.float64)
        annual_vol, vol_regime = _annual_vol_regime(closes)

        r = info_by_code[code]
        scores.append({
            "code": code,
            "name": r["name"] or "",
            "industry": r["industry"] or "其他",
            "composite": round(composite, 4),
            "factor_pctl": {f: round(v, 3) for f, v in present.items()},
            "annual_vol": annual_vol,
            "vol_regime": vol_regime,
            "hard_tech_track": _get_hard_tech_track(r["industry"] or ""),
        })

    if not scores:
        return [], [], {"env": "no_candidates", "effective_n": 0}

    # composite 分位 → grade
    comps = np.array([s["composite"] for s in scores])
    for s in scores:
        p = float((comps < s["composite"]).mean())  # 该票 composite 的分位
        s["pctl"] = round(p, 3)
        s["total_score"] = round(p * 100, 1)  # 兼容字段 (回测/前端读 total_score)
        if p >= GRADE_PCTL["S"]:
            s["grade"] = "S"
        elif p >= GRADE_PCTL["A"]:
            s["grade"] = "A"
        elif p >= GRADE_PCTL["B"]:
            s["grade"] = "B"
        else:
            s["grade"] = "C"
        s["signal"] = "watch"  # V15 无择时信号, 统一 watch (排序靠 composite)

    # 候选: 仅 B 级以上 (前60%), 按 composite 降序
    candidates = [s for s in scores if s["grade"] in ("S", "A", "B")]
    candidates.sort(key=lambda s: -s["composite"])

    # effective_n: V15 无市场择时, 直接用 top_n (风控里有最低分散化兜底)
    top = apply_v14_risk_controls(candidates, top_n)

    market_info = {
        "env": "alpha_v15", "effective_n": len(top),
        "n_pool": len(codes), "n_scored": len(scores),
        "factor_weights": FACTOR_WEIGHTS,
    }
    return top, scores, market_info
