#!/usr/bin/env python3
"""具身智能链 BOM — 第3步: reducer 节点七维评分 + trade_signal.

把第1步(主营占比) + 第2步(卡脖子/商业化证据) 映射成 BOM 七维分项,
调 supply_chain_bom 的 derive_rating + derive_trade_signal 输出评级/信号,
验证 BOM 评分能否正确区分 7 只龙头 (S/A/B/C 分层).

评分规则 (基于 BOM 硬证据, 非V3字段):
  policy(15)          : reducer 属"具身智能"=未来产业主攻方向, policy_weight=1.5 → 基础分 12, 有政策催化证据+3
  bom(15)             : 主营占比映射 (节点集中度). 80%+→15, 50%→12, 25%→8, 10%→4, <10%→2
  chokepoint(20)      : 卡脖子证据命中. 垄断/独家/首家/稀缺 每命中+5, 客户验证/认证/供应商 每命中+3, 上限20
  growth(15)          : 业绩预告预增幅度映射. 预增100%+→15, 50%→12, 0→8, 预减→3, 无→6(中性待填)
  profit(10)          : 本期无财务, 中性 6 (标注待 fina_indicator 填充)
  commercialization(15): 阶段映射. 放量/订单+预增→15, 放量/订单→12, 量产→9, 小批量→6, 样品→3, 未识别→2
  market(10)          : 互动问答热度+研报覆盖. 证据数映射 (20+→10, 10→7, 5→5, <5→3)

输出:
  - 每只公司七维分项 + total + rating + trade_signal
  - 排序 + 分层验证 (龙头是否排前)
  - 导出 CSV

Usage:
    python tools/bom_reducer_score.py
"""
import os
import sys
import ast
from pathlib import Path

import pandas as pd

_PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJ / "packages" / "kronos-factors"))
from kronos_factors.engine.supply_chain_bom import (  # noqa: E402
    DIM_WEIGHTS, derive_rating, derive_trade_signal,
)

REDUCER_LEADERS = [
    ("002472.SZ", "双环传动", "减速器及其他", 8.73),
    ("688017.SH", "绿的谐波", "谐波减速器及金属部件", 83.49),
    ("002896.SZ", "中大力德", "精密减速器", 24.24),
    ("605389.SH", "长龄液压", "回转减速器", 23.33),
    ("300503.SZ", "昊志机电", "减速器等功能部件", 13.79),
    ("301368.SZ", "丰立智能", "精密减速器(谐波)", 28.56),
    ("301596.SZ", "瑞迪智驱", "谐波减速机", 8.44),
]


def _parse_list(s):
    if isinstance(s, list):
        return s
    try:
        v = ast.literal_eval(str(s))
        return v if isinstance(v, list) else []
    except Exception:
        return []


def score_policy(ev_df):
    """reducer 在具身智能链(未来产业主攻方向, policy_weight 1.5). 基础12, 政策催化证据+3."""
    base = 12.0
    # 研报/问答提到"人形机器人量产元年""政策"等催化
    catalytic = ev_df["text"].str.contains("人形机器人|量产元年|政策|战略卡位|具身智能", na=False).any()
    if catalytic:
        base += 3.0
    return min(base, DIM_WEIGHTS["policy"])


def score_bom(main_ratio):
    """主营占比 → 节点集中度."""
    r = float(main_ratio)
    if r >= 80: return 15.0
    if r >= 50: return 12.0
    if r >= 25: return 8.0
    if r >= 10: return 4.0
    return 2.0


# 卡脖子关键词权重
CHOKEPOINT_WEIGHTS = {
    "垄断": 5, "独家": 5, "首家": 5, "稀缺": 5, "寡头": 5, "唯一": 5,
    "国产替代": 4, "进口替代": 4, "自主可控": 4, "打破垄断": 5, "卡脖子": 4,
    "客户验证": 3, "认证": 3, "供应商": 3, "定点": 3, "进入供应链": 3,
}


def score_chokepoint(ev_df):
    """卡脖子证据命中加权."""
    total = 0.0
    hits = {}
    for _, r in ev_df.iterrows():
        for kw in _parse_list(r.get("chokepoint")):
            w = CHOKEPOINT_WEIGHTS.get(kw, 2)
            total += w
            hits[kw] = hits.get(kw, 0) + w
    # 去重衰减: 同关键词多次命中递减 (第2次起×0.5)
    # 简化: 直接 cap
    return min(total, DIM_WEIGHTS["chokepoint"]), hits


def score_growth(fc_signal, ev_df):
    """业绩预告预增幅度. 从 evidence forecast 行解析 p_change."""
    # 找 forecast 证据里最大的 p_change_max
    fc_rows = ev_df[ev_df["source"] == "forecast"]
    max_growth = None
    for _, r in fc_rows.iterrows():
        text = str(r.get("text", ""))
        if "预增" in text:
            # 解析 "业绩预告 预增 104.74~131.45%"
            import re
            m = re.search(r"预增\s*([\d.]+)~([\d.]+)", text)
            if m:
                hi = float(m.group(2))
                max_growth = max(max_growth or 0, hi)
    if "预减" in (fc_signal or ""):
        return 3.0, "预减"
    if max_growth is not None:
        if max_growth >= 100: return 15.0, f"预增{max_growth:.0f}%"
        if max_growth >= 50: return 12.0, f"预增{max_growth:.0f}%"
        return 9.0, f"预增{max_growth:.0f}%"
    return 6.0, "中性(待财务填充)"


def score_profit():
    """本期无财务数据, 中性."""
    return 6.0, "中性(待fina_indicator)"


def score_commercialization(stage, fc_signal):
    """商业化阶段 + 业绩兑现."""
    base = {"放量/订单": 12.0, "量产": 9.0, "小批量": 6.0, "样品/研发": 3.0, "未识别": 2.0}.get(stage, 2.0)
    note = stage
    if "预增" in (fc_signal or "") and base >= 9:
        base = min(base + 3, DIM_WEIGHTS["commercialization"])
        note = f"{stage}+业绩兑现"
    return base, note


def score_market(ev_df):
    """互动问答热度 + 研报覆盖 → 市场关注度."""
    n = len(ev_df)
    if n >= 20: return 10.0
    if n >= 10: return 7.0
    if n >= 5: return 5.0
    if n >= 1: return 3.0
    return 1.0


def main():
    ev_all = pd.read_csv(_PROJ / "outputs" / "bom_reducer_evidence.csv")

    results = []
    for code, name, product, ratio in REDUCER_LEADERS:
        ev_df = ev_all[ev_all["code"] == code].copy()
        fc_signal = ""
        fc_rows = ev_df[ev_df["source"] == "forecast"]
        if len(fc_rows):
            # 从 summary 取 fc_signal 更准, 这里重算
            for _, r in fc_rows.iterrows():
                if "预增" in str(r.get("text", "")):
                    fc_signal = "业绩预增(放量兑现)"; break
                if "预减" in str(r.get("text", "")):
                    fc_signal = "业绩预减(承压)"; break

        # 商业化阶段 (从证据 stage 命中推断最高阶段)
        stage_order = ["放量/订单", "量产", "小批量", "样品/研发"]
        stage_hits = set()
        for _, r in ev_df.iterrows():
            for s in _parse_list(r.get("stage")):
                stage_hits.add(s)
        top_stage = ""
        for s in stage_order:
            if s in stage_hits:
                top_stage = s; break
        if not top_stage:
            top_stage = "未识别"

        policy = score_policy(ev_df)
        bom = score_bom(ratio)
        chokepoint, ch_hits = score_chokepoint(ev_df)
        growth, g_note = score_growth(fc_signal, ev_df)
        profit, p_note = score_profit()
        commercialization, c_note = score_commercialization(top_stage, fc_signal)
        market = score_market(ev_df)
        risk = 0.0  # 本期未抽取风险扣分项

        dims = {
            "policy": policy, "bom": bom, "chokepoint": chokepoint,
            "growth": growth, "profit": profit,
            "commercialization": commercialization, "market": market,
            "risk": risk,
        }
        total = round(sum(dims[k] for k in DIM_WEIGHTS) - min(risk, 10), 1)
        total = min(total, 100)
        rating = derive_rating(total)
        signal = derive_trade_signal(total, dims)

        results.append({
            "code": code, "name": name, "product": product, "main_ratio_pct": ratio,
            "policy": policy, "bom": bom, "chokepoint": chokepoint,
            "growth": growth, "profit": profit, "commercialization": commercialization,
            "market": market, "risk": risk,
            "total": total, "rating": rating, "trade_signal": signal,
            "n_evidence": len(ev_df),
            "chokepoint_hits": ch_hits,
            "growth_note": g_note, "comm_note": c_note,
            "stage": top_stage,
        })

    df = pd.DataFrame(results).sort_values("total", ascending=False)

    print("=" * 110)
    print("  具身智能链 reducer 节点 — BOM 七维评分")
    print("=" * 110)
    print(f"  {'名称':<8} {'主营%':>5} {'policy':>6} {'bom':>5} {'choke':>6} {'growth':>6} {'profit':>6} {'comm':>5} {'market':>6} {'total':>6} {'评级':>4} {'信号':<8}")
    print("  " + "-" * 106)
    for _, r in df.iterrows():
        print(f"  {r['name']:<8} {r['main_ratio_pct']:>5.1f} {r['policy']:>6.1f} {r['bom']:>5.1f} "
              f"{r['chokepoint']:>6.1f} {r['growth']:>6.1f} {r['profit']:>6.1f} {r['commercialization']:>5.1f} "
              f"{r['market']:>6.1f} {r['total']:>6.1f} {r['rating']:>4} {r['trade_signal']:<8}")
    print()
    print("  分项说明:")
    for _, r in df.iterrows():
        ch = ", ".join(f"{k}×{v:.0f}" for k, v in r["chokepoint_hits"].items()) or "无"
        print(f"    {r['name']:<8} | chokepoint: {ch} | growth: {r['growth_note']} | comm: {r['comm_note']} | 证据{r['n_evidence']}条")

    # 分层验证
    print()
    print("  分层验证 (BOM 评分是否区分龙头):")
    for rating in ["S", "A", "B", "C", "D"]:
        g = df[df["rating"] == rating]
        if len(g):
            print(f"    {rating}级 ({len(g)}只): {', '.join(g['name'].tolist())}")

    out = _PROJ / "outputs" / "bom_reducer_score.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n  导出: {out}")


if __name__ == "__main__":
    main()
