#!/usr/bin/env python3
"""Tushare VIP 接口可用性 probe (supply-chain-bom-v4 数据底盘验证).

逐一探测 PRD §5.3 列出的 BOM 拆解关键接口, 用最小调用 (单票/单日) 记录:
  - 是否可调 (权限/积分是否够)
  - 返回行数 + 字段
  - 报错信息 (Tushare 权限不足会返回明确 code/msg)

判定:
  OK     = 有数据
  EMPTY  = 可调但无数据 (接口可用, 该参数无匹配)
  DENIED = 权限/积分不足 (接口存在但当前 token 不可用)
  ERROR  = 调用异常 (网络/参数/接口名错)

Usage:
    TUSHARE_TOKEN=xxx python tools/tushare_vip_probe.py [--code 300308] [--date 20260615]
"""
import argparse
import os
import sys
import time
import traceback

import tushare as ts


def probe(pro, name, api_name, fields=None, **params):
    """单接口探测. 返回 dict(status, rows, fields, msg)."""
    rec = {"api": api_name, "name": name, "status": "?", "rows": 0,
           "fields": [], "msg": "", "elapsed": 0}
    t0 = time.time()
    try:
        df = getattr(pro, api_name)(**({**({"fields": fields} if fields else {}), **params}))
        rec["elapsed"] = round(time.time() - t0, 2)
        if df is None:
            rec["status"] = "EMPTY"; rec["msg"] = "returned None"
        else:
            rec["rows"] = len(df)
            rec["fields"] = list(df.columns)[:15]
            rec["status"] = "OK" if len(df) > 0 else "EMPTY"
            rec["msg"] = "" if len(df) > 0 else "0 rows (接口可调, 参数无匹配)"
    except Exception as e:
        rec["elapsed"] = round(time.time() - t0, 2)
        msg = str(e)
        rec["msg"] = msg[:200]
        # Tushare 权限不足常见措辞
        low = msg.lower()
        if any(k in low for k in ["权限", "积分", "permission", "no access",
                                   "not enough", "未授权", "抱歉", "40001", "40002"]):
            rec["status"] = "DENIED"
        else:
            rec["status"] = "ERROR"
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="300308", help="测试股票代码 (中际旭创)")
    ap.add_argument("--date", default="20260615", help="测试日期 YYYYMMDD")
    ap.add_argument("--start", default="20260101")
    ap.add_argument("--end", default="20260615")
    args = ap.parse_args()

    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("❌ TUSHARE_TOKEN 未设置"); sys.exit(1)
    ts.set_token(token)
    pro = ts.pro_api()

    # 先确认 token 身份 + 积分
    print("=" * 90)
    print("  Tushare VIP 接口可用性 probe")
    print("=" * 90)
    try:
        user = pro.user()  # 部分版本可用
        print(f"  token 身份: {user}")
    except Exception:
        print(f"  token: {token[:8]}...{token[-4:]} (len={len(token)}, pro_api 已初始化)")
    print(f"  测试标的: {args.code} | 日期: {args.date} | 区间: {args.start}~{args.end}")
    print()

    code = args.code
    ts_code = code + (".SH" if code.startswith(("6", "5")) else ".SZ" if code.startswith(("0", "3")) else ".BJ")
    ann_code = code  # anns_d 用 6 位
    date = args.date

    probes = [
        # ── 主营构成 (BOM 核心: 企业-产品-材料锚定) ──
        ("主营构成 fina_mainbz_vip", "fina_mainbz_vip", {"ts_code": ts_code, "period": "20251231"}),
        ("主营构成 fina_mainbz (普通)", "fina_mainbz", {"ts_code": ts_code}),

        # ── 互动问答 (LLM 抽取金矿) ──
        ("互动问答 irm_qa_sh", "irm_qa_sh", {"ts_code": ts_code, "start_date": args.start, "end_date": args.end}),
        ("互动问答 irm_qa_sz", "irm_qa_sz", {"ts_code": ts_code, "start_date": args.start, "end_date": args.end}),

        # ── 研报 ──
        ("研报 research_report", "research_report", {"ts_code": ts_code, "start_date": args.start, "end_date": args.end}),
        ("券商共识 broker_recommend", "broker_recommend", {"ts_code": ts_code}),

        # ── 公告 (量产/订单/客户证据) ──
        ("公告 anns_d", "anns_d", {"ts_code": ann_code, "start_date": args.start, "end_date": args.end}),

        # ── 行业/主题分类 (BOM 骨架) ──
        ("同花顺概念 ths_index", "ths_index", {}),
        ("同花顺成员 ths_member", "ths_member", {"ts_code": ts_code}),
        ("同花顺概念日线 ths_daily", "ths_daily", {"ts_code": "885538.TI", "start_date": args.start, "end_date": args.end}),
        ("申万行业分类 index_classify", "index_classify", {"level": "L1", "src": "SW2021"}),
        ("申万成员 index_member_all", "index_member_all", {"ts_code": ts_code}),

        # ── 政策/新闻 ──
        ("新闻 major_news", "major_news", {"ts_code": ann_code, "start_date": args.start, "end_date": args.end}),
        ("新闻 news", "news", {"src": "sina", "start_date": args.start, "end_date": args.end}),
        ("央视新闻 cctv_news", "cctv_news", {"date": date}),

        # ── 财务 ──
        ("利润表 income", "income", {"ts_code": ts_code, "period": "20251231"}),
        ("财务指标 fina_indicator", "fina_indicator", {"ts_code": ts_code, "period": "20251231"}),
        ("业绩预告 forecast", "forecast", {"ts_code": ts_code, "period": "20251231"}),

        # ── 资金/筹码 (market 分项) ──
        ("资金流 moneyflow", "moneyflow", {"ts_code": ts_code, "start_date": args.start, "end_date": args.end}),
        ("沪深港通 hsgt_top10", "hsgt_top10", {"trade_date": date}),
        ("龙虎榜 top_list", "top_list", {"trade_date": date}),
        ("筹码 cyq_chips", "cyq_chips", {"ts_code": ts_code, "trade_date": date}),
        ("涨停股 limit_list_d", "limit_list_d", {"trade_date": date}),
    ]

    results = []
    for name, api_name, params in probes:
        print(f"  ▶ {name:<32} ", end="", flush=True)
        rec = probe(pro, name, api_name, **params)
        results.append(rec)
        status_icon = {"OK": "✅", "EMPTY": "⚪", "DENIED": "⛔", "ERROR": "❌"}.get(rec["status"], "?")
        extra = f"{rec['rows']}行 {rec['fields'][:4]}" if rec["status"] == "OK" else rec["msg"][:60]
        print(f"{status_icon} {rec['status']:<6} {rec['elapsed']:>4}s | {extra}")
        time.sleep(0.3)  # Tushare 频控友好

    # ── 汇总 ──
    print()
    print("=" * 90)
    print("  汇总")
    print("=" * 90)
    from collections import Counter
    c = Counter(r["status"] for r in results)
    print(f"  ✅ OK={c['OK']}  ⚪ EMPTY={c['EMPTY']}  ⛔ DENIED={c['DENIED']}  ❌ ERROR={c['ERROR']}  / 共 {len(results)}")
    print()
    print(f"  {'接口':<28} {'状态':<7} {'行数':>5} {'耗时':>5}  说明")
    print("  " + "-" * 84)
    for r in results:
        status_icon = {"OK": "✅", "EMPTY": "⚪", "DENIED": "⛔", "ERROR": "❌"}.get(r["status"], "?")
        note = ""
        if r["status"] == "OK":
            note = f"字段: {', '.join(r['fields'][:6])}"
        elif r["status"] in ("DENIED", "ERROR"):
            note = r["msg"][:60]
        elif r["status"] == "EMPTY":
            note = r["msg"]
        print(f"  {r['api']:<28} {status_icon}{r['status']:<6} {r['rows']:>5} {r['elapsed']:>4}s  {note}")

    # 重点 VIP 接口结论
    print()
    print("  ★ BOM 拆解关键接口结论:")
    key_apis = {"fina_mainbz_vip", "fina_mainbz", "irm_qa_sh", "irm_qa_sz",
                "research_report", "anns_d", "ths_index", "ths_member", "ths_daily"}
    for r in results:
        if r["api"] in key_apis:
            tag = "可用 ✅" if r["status"] == "OK" else ("权限不足 ⛔" if r["status"] == "DENIED" else f"{r['status']}")
            print(f"    {r['api']:<22} {tag}")


if __name__ == "__main__":
    main()
