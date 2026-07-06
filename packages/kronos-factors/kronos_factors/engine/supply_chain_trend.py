"""产业链趋势启动选股 — 硬核科技 × 产业链位置 × 量价择时.

三引擎融合:
  引擎1 (0-50): 硬核科技选股 (毕师傅框架六维)
  引擎2 (0-20): 产业链位置 (大葱解构)
  引擎3 (0-30): 量价趋势启动 (OBV + WR + 资金流向)

Mode: supply_chain_trend_launch
"""

from __future__ import annotations

import os, re, time, logging
from typing import Optional

import numpy as np

from kronos_factors.base import StrategyEngine, ScreeningResult

logger = logging.getLogger("kronos-factors.supply_chain_trend")

# ═══════════════════════════════════════════════════════════════
# 卡脖子关键词 (复用 v5)
# ═══════════════════════════════════════════════════════════════
CHOKEPOINT_WEIGHTS = {
    "垄断": 5, "独家": 5, "首家": 5, "稀缺": 5, "寡头": 5, "唯一": 5,
    "国产替代": 4, "进口替代": 4, "自主可控": 4, "打破垄断": 5, "卡脖子": 4,
    "客户验证": 3, "认证": 3, "供应商": 3, "定点": 3, "进入供应链": 3,
}
CHOKEPOINT_CORE = frozenset({"垄断", "独家", "首家", "稀缺", "寡头", "唯一", "打破垄断", "卡脖子"})
CHOKEPOINT_KEY = frozenset({"国产替代", "进口替代", "自主可控", "客户验证", "认证", "供应商", "定点", "进入供应链"})

# 链权重 (H6 政策共振用)
CHAIN_WEIGHTS = {
    "华为韬定律_先进封装": 3, "半导体": 2.5,
    "光通信": 2, "存储芯片": 2,
    "华为终端": 1.5, "EDA工业软件": 1.5,
    "AI算力": 1, "机器人": 1,
}
ALL_CHAINS = ['半导体','华为韬定律_先进封装','光通信','存储芯片','华为终端','EDA工业软件','AI算力','机器人']

# ═══════════════════════════════════════════════════════════════
# 硬核科技评分函数
# ═══════════════════════════════════════════════════════════════

def _extract_chokepoint_features(
    code: str, name: str, main_business: str,
    report_titles: list[str], node_keywords: list[str],
) -> tuple[float, list[str], str]:
    """从研报+主营+节点关键词提取卡脖子特征."""
    search_text = f"{name} {main_business or ''} {' '.join(report_titles or [])} {' '.join(node_keywords or [])}"
    kw_hits: dict[str, int] = {}
    for kw in CHOKEPOINT_WEIGHTS:
        cnt = search_text.count(kw)
        if cnt > 0:
            kw_hits[kw] = cnt

    total_weight = sum(min(c, 2) * CHOKEPOINT_WEIGHTS.get(kw, 2) for kw, c in kw_hits.items())
    core_hits = {k: v for k, v in kw_hits.items() if k in CHOKEPOINT_CORE}
    key_hits = {k: v for k, v in kw_hits.items() if k in CHOKEPOINT_KEY}

    if core_hits and total_weight >= 10:
        level = "卡脖子核心"
    elif key_hits or total_weight >= 5:
        level = "关键环节"
    else:
        level = "普通"

    return total_weight, list(kw_hits.keys()), level


def _score_h1_chokepoint(cp_weight: float, cp_keywords: list[str], cp_level: str) -> float:
    """H1 卡脖子紧迫度 (0-10)."""
    lm = {"卡脖子核心": 5, "关键环节": 3, "普通": 1}
    ls = lm.get(cp_level, 0)
    if cp_weight >= 20: is_ = 5
    elif cp_weight >= 12: is_ = 4
    elif cp_weight >= 6: is_ = 3
    elif cp_weight >= 2: is_ = 2
    elif cp_weight > 0: is_ = 1
    else: is_ = 0
    if any(k in CHOKEPOINT_CORE for k in (cp_keywords or [])) and is_ < 4:
        is_ = min(5, is_ + 1)
    return min(10.0, float(ls + is_))


def _score_h2_hardcore(pricing_power: int, barrier: int, gross_margin: float, mapping_status: str) -> float:
    """H2 真硬核纯度 (0-10)."""
    pp = int(pricing_power or 1)
    bar = int(barrier or 1)
    gm = float(gross_margin or 0)
    tech = 5 if pp >= 4 and bar >= 4 else (3 if pp >= 3 and bar >= 3 else (2 if pp >= 2 else 1))
    va = 5 if gm >= 60 else (4 if gm >= 40 else (3 if gm >= 25 else (2 if gm >= 15 else 1)))
    s = tech + va
    if mapping_status == 'weak_evidence': s = max(0, s - 2)
    if gm < 15: s = max(0, s - 2)
    return min(10.0, float(s))


def _score_h3_scarcity(concentration: float, barrier: int, sample_size: int) -> float:
    """H3 稀缺性 (0-8)."""
    conc = float(concentration or 0.15)
    bar = int(barrier or 1)
    n = int(sample_size or 100)
    cs = 4 if conc >= 0.7 else (3 if conc >= 0.5 else (2 if conc >= 0.3 else 1))
    bs = 4 if bar >= 5 else (3 if bar >= 4 else (2 if bar >= 3 else 1))
    premium = 1 if (conc >= 0.7 and bar >= 4 and n <= 15) else 0
    return min(8.0, float(cs + bs + premium))


def _score_h4_stage(evidence_gaps_count: int, revenue_growth: float, report_count: int) -> float:
    """H4 产业阶段 (0-7)."""
    gc = int(evidence_gaps_count or 0)
    rg = float(revenue_growth or 0)
    if gc <= 1 and rg > 50: ss = 4.0
    elif gc <= 2 and rg > 20: ss = 3.5
    elif gc <= 3: ss = 3.0
    elif gc <= 4: ss = 3.5
    else: ss = 2.5
    if gc == 0: es = 3.0
    elif gc <= 1: es = 2.5
    elif gc <= 2: es = 2.0
    elif gc <= 4: es = 1.0
    else: es = 0.5
    rc_bonus = 0.5 if report_count >= 20 else (0.3 if report_count >= 10 else 0.0)
    return min(7.0, round(ss + es + rc_bonus, 1))


def _score_h5_performance(revenue_growth: float, roe: float, profit_growth: float) -> float:
    """H5 业绩验证 (0-10)."""
    rg = float(revenue_growth or 0)
    roe_v = float(roe or 0)
    pg = float(profit_growth or 0)
    rs = 4 if rg >= 100 else (3 if rg >= 50 else (2 if rg >= 20 else (1 if rg >= 0 else 0)))
    ps = 4 if roe_v >= 20 else (3 if roe_v >= 10 else (2 if roe_v >= 5 else (1 if roe_v >= 0 else 0)))
    inf = 2 if (pg > 0 and pg > max(rg, 0) and rg > 0) else 0
    return min(10.0, float(rs + ps + inf))


def _score_h6_policy(chains_found: set[str], upstream_rule_count: int, core_rule_count: int) -> float:
    """H6 政策共振 (0-5)."""
    cc = len(chains_found & {'华为韬定律_先进封装', '半导体'})
    kc = len(chains_found & {'光通信', '存储芯片'})
    nc = len(chains_found & {'华为终端', 'EDA工业软件', 'AI算力', '机器人'})
    chain_score = min(3.0, cc * 1.0 + kc * 0.5 + nc * 0.2)
    obs_rules = int(upstream_rule_count or 0) - int(core_rule_count or 0)
    rule_score = min(2.0, float(core_rule_count or 0) * 0.5 + float(obs_rules) * 0.2)
    return round(chain_score + rule_score, 1)


def _score_e2_position(pricing_power: int, value_added: float, upstream_count: int) -> float:
    """E2 产业链位置 (0-20)."""
    pp = int(pricing_power or 1)
    va = float(value_added or 0)
    up = int(upstream_count or 0)
    ps = {5: 8, 4: 6, 3: 4, 2: 2, 1: 1}.get(pp, 1)
    vs = 6 if va >= 40 else (5 if va >= 30 else (3 if va >= 20 else (2 if va >= 15 else 1)))
    return min(20, ps + vs + min(6, up * 2))


# ═══════════════════════════════════════════════════════════════
# 引擎3: 量价趋势启动
# ═══════════════════════════════════════════════════════════════

def _compute_obv(closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    """Compute On-Balance Volume."""
    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]
    return obv


def _compute_wr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Compute Williams %R."""
    wr = np.full(len(closes), np.nan)
    for i in range(period - 1, len(closes)):
        hh = np.max(highs[i - period + 1:i + 1])
        ll = np.min(lows[i - period + 1:i + 1])
        if hh != ll:
            wr[i] = (hh - closes[i]) / (hh - ll) * -100
    return wr


def score_trend_launch(df) -> dict:
    """Combine OBV trend + WR launch + Money Flow into a 0-30 score.

    Args:
        df: pd.DataFrame with columns [open, high, low, close, volume]

    Returns:
        {"score": 0-30, "signal": str, "obv_trend": str, "wr_signal": str, "mf_signal": str}
    """
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    volumes = df["volume"].values.astype(float)

    n = len(closes)
    if n < 30:
        return {"score": 15.0, "signal": "数据不足", "obv_trend": "-", "wr_signal": "-", "mf_signal": "-"}

    score = 15.0  # baseline

    # ── 1. OBV 趋势 (0-8) ──
    obv = _compute_obv(closes, volumes)
    obv_slope = (obv[-1] - obv[-10]) / (abs(obv[-10]) + 1)
    obv_ma10 = np.mean(obv[-10:])
    obv_ma20 = np.mean(obv[-20:]) if n >= 20 else obv_ma10

    if obv_slope > 0.03 and obv[-1] > obv_ma20:
        obv_trend = "↑ 强势流入"
        score += 5
    elif obv_slope > 0.01:
        obv_trend = "↗ 温和流入"
        score += 3
    elif obv_slope < -0.03 and obv[-1] < obv_ma20:
        obv_trend = "↓ 持续流出"
        score -= 5
    elif obv_slope < -0.01:
        obv_trend = "↘ 温和流出"
        score -= 3
    else:
        obv_trend = "→ 持平"

    # OBV 与价格背离检测
    price_chg_10 = (closes[-1] / closes[-10] - 1) * 100 if n >= 10 else 0
    if price_chg_10 > 3 and obv_slope < 0:
        obv_trend += " ⚠️价升OBV跌"
        score -= 3
    elif price_chg_10 < -3 and obv_slope > 0:
        obv_trend += " 💡价跌OBV升(吸筹)"
        score += 3

    # ── 2. WR 启动信号 (0-12) ──
    wr = _compute_wr(highs, lows, closes, 14)
    wr_latest = wr[-1] if not np.isnan(wr[-1]) else -50
    wr_prev = wr[-2] if n >= 2 and not np.isnan(wr[-2]) else wr_latest

    # WR 从超卖区回升 → 启动信号
    if wr_prev <= -80 and wr_latest > -80:
        wr_signal = "🚀 超卖反弹启动"
        score += 8
    elif wr_prev <= -80 and wr_latest > -50:
        wr_signal = "🔥 强超卖反转"
        score += 12
    elif wr_latest <= -80:
        wr_signal = "📉 深度超卖"
        score -= 2
    elif wr_latest >= -20:
        wr_signal = "📈 超买区"
        score -= 4
    elif -50 <= wr_latest <= -30:
        wr_signal = "⚖ 中性偏强"
        score += 2
    else:
        wr_signal = "⚖ 中性"

    # ── 3. 资金流向 (0-10) ──
    typical = (highs + lows + closes) / 3.0
    money_flow = typical * volumes

    # MFI (14-period)
    mfi_period = 14
    pos_flow = np.zeros(n)
    neg_flow = np.zeros(n)
    for i in range(1, n):
        if typical[i] > typical[i - 1]:
            pos_flow[i] = money_flow[i]
        else:
            neg_flow[i] = money_flow[i]

    mfi_values = []
    for i in range(mfi_period, n):
        ps = pos_flow[i - mfi_period + 1:i + 1].sum()
        ns = neg_flow[i - mfi_period + 1:i + 1].sum()
        mfi = 100.0 - (100.0 / (1.0 + ps / (ns + 1e-10)))
        mfi_values.append(mfi)

    mfi = float(np.mean(mfi_values[-5:])) if mfi_values else 50.0

    if mfi > 80:
        mf_signal = "超买流出"
        score -= 3
    elif mfi > 60:
        mf_signal = "资金流入"
        score += 3
    elif mfi < 20:
        mf_signal = "超卖吸筹"
        score += 5
    elif mfi < 40:
        mf_signal = "资金流出"
        score -= 3
    else:
        mf_signal = "平衡"

    # 最终信号
    score = max(0.0, min(30.0, round(score, 1)))
    if score >= 24: signal = "强启动"
    elif score >= 18: signal = "启动"
    elif score >= 12: signal = "关注"
    else: signal = "观望"

    return {
        "score": score, "signal": signal,
        "obv_trend": obv_trend, "wr_signal": wr_signal, "mf_signal": mf_signal,
        "mfi": round(mfi, 1), "wr_value": round(wr_latest, 1),
    }


# ═══════════════════════════════════════════════════════════════
# TrendLaunchEngine
# ═══════════════════════════════════════════════════════════════

class TrendLaunchEngine(StrategyEngine):
    """产业链趋势启动选股引擎.

    三引擎融合:
      - 引擎1: 硬核科技 (H1-H6, 0-50)
      - 引擎2: 产业链位置 (E2, 0-20)
      - 引擎3: 量价趋势启动 (OBV+WR+MFI, 0-30)

    信号: 强启动(≥75) / 启动(≥60) / 关注(≥45) / 观察(<45)
    """

    mode = "supply_chain_trend_launch"

    def __init__(self):
        pass

    def get_factor_weights(self) -> dict:
        return {
            "hardcore_tech": 0.50,
            "supply_chain_position": 0.20,
            "trend_launch": 0.30,
        }

    def run(self, top_n: int = 30, chain: str = "半导体",
            min_score: float = 30, trade_date: str | None = None,
            require_trend: bool = False, **kw) -> ScreeningResult:
        """Run trend launch screening.

        Args:
            top_n: Max picks to return.
            chain: Base supply chain to screen (default: 半导体).
            min_score: Minimum hardcore tech score to consider.
            trade_date: Historical cutoff date.
            require_trend: If True, only return stocks with trend score >= 18.
        """
        import pandas as pd
        import psycopg2
        from kronos_factors.engine.supply_chain import SupplyChainEngine, match_upstream_influence_rules, load_upstream_influence_rules

        t0 = time.time()
        pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
        pg = psycopg2.connect(pg_url, connect_timeout=10)
        cur = pg.cursor()

        # ── Step 1: 获取基础候选池 (from SupplyChainEngine) ──
        base_engine = SupplyChainEngine()
        base_result = base_engine.run(top_n=80, chain=chain, min_score=min_score, trade_date=trade_date)
        base_picks = base_result.picks[:80]
        codes = [str(p['code']) for p in base_picks]

        if not codes:
            pg.close()
            return ScreeningResult(mode=self.mode, picks=[], total_scored=0, elapsed=time.time()-t0)

        rules = load_upstream_influence_rules()
        ph = ','.join(['%s'] * len(codes))

        # ── Step 2: 批量加载产业链数据 ──
        # node value_chain + competition
        cur.execute(f"""
            SELECT DISTINCT ON (regexp_replace(cm.code, '\\.(SZ|SH|BJ)$', ''))
                regexp_replace(cm.code, '\\.(SZ|SH|BJ)$', '') as c,
                cn.value_chain, cn.competition, cm.chokepoint_score, bm.status, cm.evidence
            FROM company_chain_mapping cm
            JOIN chain_nodes cn ON cm.node_id = cn.node_id
            LEFT JOIN company_bom_mapping bm ON bm.code = cm.code AND bm.node_id = cm.node_id
            WHERE regexp_replace(cm.code, '\\.(SZ|SH|BJ)$', '') IN ({ph})
            ORDER BY regexp_replace(cm.code, '\\.(SZ|SH|BJ)$', ''), cm.policy_match_score DESC
        """, codes)
        node_data = {}
        for r in cur.fetchall():
            node_data[r[0]] = r

        # 公司基本信息
        cur.execute(f"""
            SELECT s.code, s.industry, sp.main_business
            FROM stocks s LEFT JOIN stock_profiles sp ON s.code = sp.code
            WHERE s.code IN ({ph}) AND s.is_st = 0
        """, codes)
        biz_data = {}
        for r in cur.fetchall():
            biz_data[r[0]] = (r[1] or '', r[2] or '')

        # 研报标题 (按 trade_date 过滤, 防未来信息泄露)
        if trade_date:
            cur.execute(f"""
                SELECT code, title FROM research_reports_tushare
                WHERE code IN ({ph}) AND code IS NOT NULL AND code != 'nan'
                  AND pub_date <= %s
                ORDER BY pub_date DESC LIMIT 5000
            """, codes + [trade_date])
        else:
            cur.execute(f"""
                SELECT code, title FROM research_reports_tushare
                WHERE code IN ({ph}) AND code IS NOT NULL AND code != 'nan'
                ORDER BY pub_date DESC LIMIT 5000
            """, codes)
        rt_map: dict[str, list[str]] = {}
        for c, t in cur.fetchall():
            rt_map.setdefault(c, []).append(str(t or ''))

        # 研报数 (按 trade_date 过滤)
        if trade_date:
            cur.execute(f"SELECT code, COUNT(*) FROM research_reports_tushare WHERE code IN ({ph}) AND pub_date <= %s GROUP BY code", codes + [trade_date])
        else:
            cur.execute(f"SELECT code, COUNT(*) FROM research_reports_tushare WHERE code IN ({ph}) GROUP BY code", codes)
        rc_map = {r[0]: r[1] for r in cur.fetchall()}

        # ── Step 3: 跨链召回索引 ──
        chain_idx: dict[str, set[str]] = {}
        for ch in ALL_CHAINS:
            r = base_engine.run(top_n=200, chain=ch, min_score=0, trade_date=trade_date)
            for p in r.picks:
                chain_idx.setdefault(str(p['code']), set()).add(ch)

        # ── Step 4: 逐股打分 ──
        picks = []
        for p in base_picks:
            code = str(p['code'])
            name = p['name']
            gm = float(p.get('gross_margin', 0))
            rg = float(p.get('revenue_growth', 0))
            roe = float(p.get('roe', 0))
            profit_g = float(p.get('profit_growth', 0))

            # 节点数据
            nd = node_data.get(code)
            vc = nd[1] if nd and len(nd) > 1 else {}
            comp = nd[2] if nd and len(nd) > 2 else {}
            cps = float(nd[3] or 0) if nd and len(nd) > 3 else 0
            ms = nd[4] if nd and len(nd) > 4 else 'pending'
            ev = nd[5] if nd and len(nd) > 5 else {}

            # 基本信息
            bi = biz_data.get(code, ('', ''))
            rt = rt_map.get(code, [])
            rc = rc_map.get(code, 0)
            up_rules = match_upstream_influence_rules(code, name, bi[0], bi[1], rules)
            chains_found = chain_idx.get(code, set())
            core_rules = sum(1 for r in up_rules if r.get('pool_status') == '核心池')

            # 节点关键词
            node_kw = []
            if isinstance(vc, dict):
                meta = vc.get('_meta', {})
                if isinstance(meta, dict):
                    node_kw = meta.get('keywords', [])

            # ── 引擎1: 硬核科技 ──
            cpw, cpk, cpl = _extract_chokepoint_features(code, name, bi[1], rt, node_kw)
            h1 = _score_h1_chokepoint(cpw, cpk, cpl)
            h2 = _score_h2_hardcore(vc.get('pricing_power', 1), comp.get('barrier', 1), gm, ms)
            h3 = _score_h3_scarcity(comp.get('concentration', 0.15), comp.get('barrier', 1), vc.get('sample_size', 100) if isinstance(vc, dict) else 100)
            ev_gaps = (ev or {}).get('evidence_gaps', []) if isinstance(ev, dict) else []
            h4 = _score_h4_stage(len(ev_gaps) if isinstance(ev_gaps, list) else 0, rg, rc)
            h5 = _score_h5_performance(rg, roe, profit_g)
            h6 = _score_h6_policy(chains_found, len(up_rules), core_rules)
            engine1 = round(h1 + h2 + h3 + h4 + h5 + h6, 1)

            if h2 <= 2:
                continue  # 伪概念过滤

            # ── 引擎2: 产业链位置 ──
            engine2 = _score_e2_position(vc.get('pricing_power', 1), vc.get('value_added', 0), len(up_rules))

            # ── 引擎3: 量价趋势 (按 trade_date 过滤 K线, 防未来信息泄露) ──
            engine3 = 15.0  # default neutral
            trend_detail = {}
            try:
                if trade_date:
                    cur.execute("""
                        SELECT open, high, low, close, volume, trade_date
                        FROM daily_kline WHERE code = %s AND trade_date <= %s
                        ORDER BY trade_date DESC LIMIT 60
                    """, (code, trade_date))
                else:
                    cur.execute("""
                        SELECT open, high, low, close, volume, trade_date
                        FROM daily_kline WHERE code = %s
                        ORDER BY trade_date DESC LIMIT 60
                    """, (code,))
                klines = cur.fetchall()
                if klines and len(klines) >= 30:
                    df = pd.DataFrame(klines, columns=['open', 'high', 'low', 'close', 'volume', 'trade_date'])
                    df = df.sort_values('trade_date')
                    trend_detail = score_trend_launch(df)
                    engine3 = trend_detail.get('score', 15.0)
            except Exception as e:
                logger.debug("Trend launch failed for %s: %s", code, e)

            total = engine1 + engine2 + engine3

            # 信号判定
            if total >= 75: signal = "强启动"
            elif total >= 60: signal = "启动"
            elif total >= 45: signal = "关注"
            else: signal = "观察"

            if require_trend and engine3 < 18:
                signal = "观察(趋势不足)"

            picks.append({
                "code": code, "name": name,
                "total_score": round(total, 1),
                "signal": signal,
                "engine1_hardcore": engine1,
                "engine2_position": engine2,
                "engine3_trend": engine3,
                "h1_chokepoint": h1, "h2_purity": h2, "h3_scarcity": h3,
                "h4_stage": h4, "h5_performance": h5, "h6_policy": h6,
                "chokepoint_level": cpl,
                "chokepoint_keywords": cpk[:5],
                "supply_score": p['total_score'],
                "moat_score": p.get('moat_score', 0),
                "gross_margin": gm,
                "revenue_growth": rg,
                "roe": roe,
                "chains_found": len(chains_found),
                "upstream_rules": len(up_rules),
                "report_count": rc,
                "obv_trend": trend_detail.get('obv_trend', '-'),
                "wr_signal": trend_detail.get('wr_signal', '-'),
                "mf_signal": trend_detail.get('mf_signal', '-'),
                "mfi": trend_detail.get('mfi', 50),
                "wr_value": trend_detail.get('wr_value', -50),
            })

        pg.close()

        # 排序
        picks.sort(key=lambda x: -x['total_score'])
        picks = picks[:top_n]

        elapsed = time.time() - t0
        logger.info("TrendLaunch: %d picks from %d candidates (%.1fs)", len(picks), len(base_picks), elapsed)

        return ScreeningResult(
            mode=self.mode, picks=picks, total_scored=len(picks),
            total_excluded=len(base_picks) - len(picks),
            elapsed=elapsed,
            metadata={
                "base_chain": chain, "trade_date": trade_date,
                "require_trend": require_trend,
                "engine_weights": self.get_factor_weights(),
            },
        )
