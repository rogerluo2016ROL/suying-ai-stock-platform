#!/usr/bin/env python3
"""具身智能链 BOM — 第2步: reducer 节点龙头证据采集.

对减速器节点 7 只龙头拉三类证据, 抽取卡脖子 + 商业化阶段:
  1. research_report  — 研报标题 (国产替代/卡脖子/量产/客户验证 证据)
  2. irm_qa_sz/sh     — 互动问答 (产品/客户/产能/量产进度 直接证据, 金矿)
  3. forecast         — 业绩预告 (商业化兑现: 预增=放量, 预减=承压)

抽取方式: 规则 + 关键词 (确定性, 可复现). LLM 抽取留后续.

卡脖子证据维度 (chokepoint):
  - 国产替代/进口替代/打破垄断/自主可控
  - 唯一/独家/首家/稀缺
  - 客户验证/定点/认证/进入供应链
商业化阶段维度 (commercialization):
  - 样品/小批量/量产/批量交付/订单/产能释放/放量的程度

输出:
  - 每只公司的证据清单 (来源/类型/摘要/命中维度)
  - 卡脖子 + 商业化阶段粗判 (基于证据命中数)
  - 导出 CSV/JSON 供七维评分填充

Usage:
    TUSHARE_TOKEN=xxx python tools/bom_reducer_evidence.py
"""
import os
import re
import sys
import time
from collections import defaultdict

import tushare as ts
import pandas as pd

REDUCER_LEADERS = [
    ("002472.SZ", "双环传动", "减速器及其他", 8.73),
    ("688017.SH", "绿的谐波", "谐波减速器及金属部件", 83.49),
    ("002896.SZ", "中大力德", "精密减速器", 24.24),
    ("605389.SH", "长龄液压", "回转减速器", 23.33),
    ("300503.SZ", "昊志机电", "减速器等功能部件", 13.79),
    ("301368.SZ", "丰立智能", "精密减速器(谐波)", 28.56),
    ("301596.SZ", "瑞迪智驱", "谐波减速机", 8.44),
]

START, END = "20240101", "20260615"

# 卡脖子证据关键词
CHOKEPOINT_KW = [
    "国产替代", "进口替代", "打破垄断", "自主可控", "突破封锁", "卡脖子",
    "唯一", "独家", "首家", "稀缺", "寡头", "垄断",
    "定点", "认证", "进入供应链", "客户验证", "供应商", "合格供方",
    "替代进口", "海外替代", "国产化率",
]
# 商业化阶段关键词 (按阶段递进)
COMMERCIALIZATION_KW = {
    "样品/研发": ["样品", "试制", "研发中", "预研", "开发中", "送样", "打样"],
    "小批量": ["小批量", "小批", "试产", "中试", "初步交付"],
    "量产": ["量产", "批量生产", "规模化", "批量交付", "规模交付", "稳定出货"],
    "放量/订单": ["订单", "产能释放", "扩产", "放量", "满产", "需求旺盛", "供不应求"],
}


def hit_keywords(text, keywords):
    text = str(text) if text else ""
    return [kw for kw in keywords if kw in text]


def stage_hits(text):
    """返回命中的商业化阶段 (按递进顺序, 取最高阶段)."""
    text = str(text) if text else ""
    hits = []
    for stage, kws in COMMERCIALIZATION_KW.items():
        if any(kw in text for kw in kws):
            hits.append(stage)
    return hits


def main():
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("❌ TUSHARE_TOKEN 未设置"); sys.exit(1)
    ts.set_token(token)
    pro = ts.pro_api()

    all_evidence = []  # 每条证据
    summary = []       # 每只公司汇总

    for code, name, product, ratio in REDUCER_LEADERS:
        print(f"\n{'='*80}")
        print(f"  {code} {name} — 主营: {product} ({ratio}%)")
        print(f"{'='*80}")
        company_ev = []
        chokepoint_hits = []
        stage_hits_all = []

        # 1) 研报
        try:
            rr = pro.research_report(ts_code=code, start_date=START, end_date=END)
            if rr is None:
                rr = pd.DataFrame()
        except Exception as e:
            rr = pd.DataFrame(); print(f"  研报 err: {str(e)[:50]}")
        for _, r in rr.head(30).iterrows():
            title = str(r.get("title", ""))
            ch = hit_keywords(title, CHOKEPOINT_KW)
            st = stage_hits(title)
            if ch or st:
                company_ev.append({"code": code, "name": name, "source": "research_report",
                                   "date": str(r.get("trade_date", "")), "text": title[:120],
                                   "chokepoint": ch, "stage": st})
                chokepoint_hits.extend(ch)
                stage_hits_all.extend(st)
        print(f"  研报: {len(rr)} 篇, 命中证据 {sum(1 for e in company_ev if e['source']=='research_report')} 条")

        # 2) 互动问答 (深市 irm_qa_sz, 沪市 irm_qa_sh, 按 trade_date 全市场过滤)
        qa_count = 0
        qa_hits = 0
        for api, qa_code in [("irm_qa_sz", code), ("irm_qa_sh", code)]:
            if (api == "irm_qa_sz" and not code.endswith(".SZ")) or \
               (api == "irm_qa_sh" and not code.endswith(".SH")):
                continue
            try:
                # irm_qa 按全市场日拉太重; 直接用 ts_code 试 (部分接口支持)
                qa = getattr(pro, api)(ts_code=qa_code, start_date=START, end_date=END)
                if qa is None:
                    qa = pd.DataFrame()
            except Exception:
                qa = pd.DataFrame()
            qa_count += len(qa)
            for _, r in qa.head(50).iterrows():
                q = str(r.get("q", "")) + " " + str(r.get("a", ""))
                ch = hit_keywords(q, CHOKEPOINT_KW)
                st = stage_hits(q)
                if ch or st:
                    company_ev.append({"code": code, "name": name, "source": api,
                                       "date": str(r.get("trade_date", "")),
                                       "text": (str(r.get("q", ""))[:80] + " | " + str(r.get("a", ""))[:80]),
                                       "chokepoint": ch, "stage": st})
                    chokepoint_hits.extend(ch)
                    stage_hits_all.extend(st)
                    qa_hits += 1
        print(f"  互动问答: {qa_count} 条, 命中证据 {qa_hits} 条")

        # 3) 业绩预告 (商业化兑现)
        try:
            fc = pro.forecast(ts_code=code, start_date=START, end_date=END)
            if fc is None:
                fc = pd.DataFrame()
        except Exception:
            fc = pd.DataFrame()
        fc_latest = fc.head(3) if len(fc) else pd.DataFrame()
        fc_signal = ""
        for _, r in fc_latest.iterrows():
            ftype = str(r.get("type", ""))
            pmin = r.get("p_change_min"); pmax = r.get("p_change_max")
            company_ev.append({"code": code, "name": name, "source": "forecast",
                               "date": str(r.get("ann_date", "")),
                               "text": f"业绩预告 {ftype} {pmin}~{pmax}%",
                               "chokepoint": [], "stage": []})
        if len(fc_latest):
            latest_type = str(fc_latest.iloc[0].get("type", ""))
            if "预增" in latest_type or "续盈" in latest_type:
                fc_signal = "业绩预增(放量兑现)"
                stage_hits_all.append("放量/订单")
            elif "预减" in latest_type or "预亏" in latest_type:
                fc_signal = "业绩预减(承压)"
        print(f"  业绩预告: {len(fc_latest)} 条, 信号: {fc_signal or '无'}")

        # 汇总
        from collections import Counter
        ch_counter = Counter(chokepoint_hits)
        st_counter = Counter(stage_hits_all)
        # 商业化阶段定级 (取命中的最高阶段)
        stage_order = ["样品/研发", "小批量", "量产", "放量/订单"]
        top_stage = ""
        for s in reversed(stage_order):
            if s in st_counter:
                top_stage = s; break

        print(f"  → 卡脖子证据: {dict(ch_counter.most_common(5))}")
        print(f"  → 商业化阶段: {top_stage or '未识别'}  (阶段命中: {dict(st_counter)})")

        summary.append({
            "code": code, "name": name, "product": product, "main_ratio_pct": ratio,
            "n_evidence": len(company_ev),
            "n_chokepoint_hits": len(chokepoint_hits),
            "chokepoint_top": ", ".join([f"{k}×{v}" for k, v in ch_counter.most_common(5)]),
            "commercialization_stage": top_stage or "未识别",
            "forecast_signal": fc_signal,
            "stage_hits": dict(st_counter),
        })
        all_evidence.extend(company_ev)
        time.sleep(0.5)

    # 导出
    ev_df = pd.DataFrame(all_evidence)
    sm_df = pd.DataFrame(summary)
    ev_path = "outputs/bom_reducer_evidence.csv"
    sm_path = "outputs/bom_reducer_evidence_summary.csv"
    ev_df.to_csv(ev_path, index=False, encoding="utf-8-sig")
    sm_df.to_csv(sm_path, index=False, encoding="utf-8-sig")

    print(f"\n{'='*80}")
    print(f"  汇总 — reducer 节点 7 只龙头证据采集")
    print(f"{'='*80}")
    print(sm_df[["name", "main_ratio_pct", "n_evidence", "n_chokepoint_hits",
                 "commercialization_stage", "forecast_signal"]].to_string(index=False))
    print(f"\n  导出: {ev_path} ({len(ev_df)} 证据) + {sm_path}")


if __name__ == "__main__":
    main()
