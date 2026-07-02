#!/usr/bin/env python3
"""全市场机构活跃度评分 — 5 维 percentile 加权。

北向个股维度因 2024-08-19 交易所停止披露已弃用 (hk_hold SH/SZ 空 + hsgt_top10
net_amount 全 NULL, Tushare 全权限也不可得)。详见 .wolf/cerebrum.md Do-Not-Repeat。

维度 (无北向):
  - 龙虎榜机构净买入 (top_inst, DISTINCT 去重 1.3x 重复入库)  权重 0.40
  - 龙虎榜机构上榜天数                                        权重 0.10
  - 股东户数变化 (stk_holdernumber, 下降=筹码集中, 反转计分)   权重 0.20
  - 大宗交易笔数 (block_trade_data)                           权重 0.10
  - 研报覆盖篇数 (research_reports, 近 90 天)                 权重 0.15
  - 股东增减持次数 (stk_holdertrade)                          权重 0.05

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \\
    python tools/institutional_activity_top.py --top-n 20
    python tools/institutional_activity_top.py --code 600176      # 单股明细
    python tools/institutional_activity_top.py --cross-afternoon  # 给午后选股候选标注

作为因子注入午后选股 (run_today_afternoon.py):
    from tools.institutional_activity_top import score_for
    inst = score_for(code)  # {'综合分': 0-100, '机构净买亿': ..., ...}
    # 在 score_stock 里: total += inst['综合分'] * 0.1  # 机构背书加分
"""
import argparse, os
import psycopg2
import pandas as pd

WEIGHTS = {
    "龙虎榜净买入亿": 0.40,
    "龙虎榜天数": 0.10,
    "股东户数变化%": 0.20,   # 反转 (下降得分高)
    "大宗笔数": 0.10,
    "研报篇数": 0.15,
    "增减持次": 0.05,
}
# 各维度回看窗口 (天数), 0=取最新两期 (季频)
LOOKBACK = {
    "龙虎榜净买入亿": 30, "龙虎榜天数": 30,
    "大宗笔数": 30, "研报篇数": 90, "增减持次": 30,
}


def _conn():
    url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    return psycopg2.connect(url)


def _c6(df):
    """过滤纯 6 位 A 股 code (排除带后缀/北交所)."""
    df = df.copy()
    df["code"] = df["code"].astype(str)
    return df[df["code"].str.match(r"^\d{6}$")]


def _latest_date(conn):
    """取 top_inst 最新交易日作为基准日 (默认)."""
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(trade_date) FROM top_inst")
        r = cur.fetchone()
        return r[0] if r and r[0] else pd.Timestamp.today().date()


def load_dims(conn, end_date):
    """加载 5 个维度 (end_date 为基准日, 各按 LOOKBACK 回看)."""
    end = pd.Timestamp(end_date)
    d30 = (end - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    d90 = (end - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    sql = lambda s: pd.read_sql(s, conn)

    # 龙虎榜机构 (DISTINCT 去重 — top_inst 主键自增 id, 重复 1.3x)
    d1 = sql(
        f"""SELECT code, SUM(net_buy)/1e8 v, COUNT(DISTINCT trade_date) d FROM (
            SELECT DISTINCT code, trade_date, exalter, buy, sell, net_buy FROM top_inst
            WHERE trade_date >= '{d30}' AND exalter LIKE '%机构%'
        ) t GROUP BY code"""
    )
    d1 = _c6(d1)
    d1.columns = ["code", "龙虎榜净买入亿", "龙虎榜天数"]

    # 股东户数变化 (最新两期环比, 季频)
    d3 = sql(
        """WITH r AS (
            SELECT code, end_date, holder_num,
                   ROW_NUMBER() OVER(PARTITION BY code ORDER BY end_date DESC) rn
            FROM stk_holdernumber)
        SELECT a.code, (a.holder_num*1.0/b.holder_num - 1)*100 chg
        FROM r a JOIN r b ON a.code=b.code AND a.rn=1 AND b.rn=2"""
    )
    d3 = _c6(d3)
    d3.columns = ["code", "股东户数变化%"]

    # 大宗交易
    d4 = sql(
        f"""SELECT code, COUNT(*) deals, COALESCE(SUM(amount),0)/1e8 amt
            FROM block_trade_data WHERE trade_date >= '{d30}' GROUP BY code"""
    )
    d4 = _c6(d4)
    d4.columns = ["code", "大宗笔数", "大宗额亿"]

    # 研报 (近 90 天)
    d5 = sql(
        f"""SELECT code, COUNT(*) reports FROM research_reports
            WHERE pub_date >= '{d90}' GROUP BY code"""
    )
    d5 = _c6(d5)
    d5.columns = ["code", "研报篇数"]

    # 股东增减持
    d6 = sql(
        f"""SELECT code, COUNT(*) deals FROM stk_holdertrade
            WHERE ann_date >= '{d30}' GROUP BY code"""
    )
    d6 = _c6(d6)
    d6.columns = ["code", "增减持次"]

    return {"d1": d1, "d3": d3, "d4": d4, "d5": d5, "d6": d6}


def _merge_dims(dims):
    from functools import reduce
    dfs = [d.set_index("code") for d in dims.values() if len(d) > 0]
    return reduce(lambda a, b: pd.merge(a, b, left_index=True, right_index=True, how="outer"), dfs)


def _score_frame(M):
    """对合并后的 DataFrame 做 percentile 归一化 + 加权综合分."""
    def pct(s, invert=False):
        s = s.dropna()
        r = s.rank(pct=True) * 100
        return 100 - r if invert else r

    invert = {"股东户数变化%": True}
    sc = pd.DataFrame(index=M.index)
    for c in WEIGHTS:
        if c in M.columns:
            sc[c] = pct(M[c], invert=c in invert)
    sc = sc.fillna(0)
    M = M.copy()
    M["综合分"] = sum(sc[c] * w for c, w in WEIGHTS.items() if c in sc.columns)
    return M


def _attach_name(M, conn):
    nm = pd.read_sql("SELECT code, name FROM stocks", conn).drop_duplicates("code")
    nm["code"] = nm["code"].astype(str)
    M = M.copy()
    M["name"] = nm.set_index("code")["name"]
    M = M[M.index.astype(str).str.match(r"^\d{6}$")]
    M = M[~M.index.astype(str).str.startswith(("92", "83", "87", "4", "8"))]  # 排除北交所
    M = M[~M["name"].fillna("").str.upper().str.contains("ST")]
    return M


def calc_top(end_date=None, top_n=20, conn=None):
    """全市场机构活跃度 Top-N. 返回 DataFrame (含各维度 + 综合分)."""
    own = conn is None
    if own:
        conn = _conn()
    try:
        if end_date is None:
            end_date = _latest_date(conn)
        dims = load_dims(conn, end_date)
        M = _merge_dims(dims)
        M = _attach_name(M, conn)
        M = _score_frame(M)
        return M.sort_values("综合分", ascending=False).head(top_n)
    finally:
        if own:
            conn.close()


def score_for(code, end_date=None, conn=None):
    """单股机构活跃度明细. 返回 dict (含综合分 0-100 + 各维度原值).

    供午后选股 score_stock 调用作为机构背书因子:
        inst = score_for(code); total += inst['综合分'] * 0.1
    """
    own = conn is None
    if own:
        conn = _conn()
    try:
        if end_date is None:
            end_date = _latest_date(conn)
        dims = load_dims(conn, end_date)
        M = _merge_dims(dims)
        M = _attach_name(M, conn)
        M = _score_frame(M)
        code = str(code)
        if code not in M.index:
            return {"code": code, "综合分": 0, "available": False}
        row = M.loc[code]
        return {"code": code, "综合分": round(float(row["综合分"]), 1), "available": True,
                **{c: (None if pd.isna(row[c]) else float(row[c])) for c in WEIGHTS if c in row.index}}
    finally:
        if own:
            conn.close()


def enrich_picks(codes, end_date=None, conn=None):
    """给一组 code (如午后选股候选) 标注机构活跃度分. 返回 [(code, name, 综合分, 信号)]."""
    own = conn is None
    if own:
        conn = _conn()
    try:
        if end_date is None:
            end_date = _latest_date(conn)
        top = calc_top(end_date=end_date, top_n=9999, conn=conn)  # 全市场算一次
        out = []
        for c in codes:
            c = str(c)
            if c in top.index:
                r = top.loc[c]
                sig = []
                if pd.notna(r.get("龙虎榜净买入亿")) and r["龙虎榜净买入亿"] > 0:
                    sig.append("机构净买")
                if pd.notna(r.get("股东户数变化%")) and r["股东户数变化%"] < 0:
                    sig.append("筹码集中")
                if pd.notna(r.get("研报篇数")) and r["研报篇数"] >= 3:
                    sig.append("研报覆盖")
                out.append((c, r.get("name"), round(float(r["综合分"]), 0), "+".join(sig)))
            else:
                out.append((c, None, 0, "无机构数据"))
        return out
    finally:
        if own:
            conn.close()


def _fmt(v, fmt="{:.1f}"):
    return fmt.format(v) if v is not None and not pd.isna(v) else "-"


def main():
    p = argparse.ArgumentParser(description="全市场机构活跃度评分 (5维, 无北向)")
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--code", type=str, help="单股明细")
    p.add_argument("--end-date", type=str, default=None, help="基准日 YYYY-MM-DD (默认最新)")
    p.add_argument("--cross-afternoon", action="store_true",
                   help="读取午后选股候选 (从 tools/last_afternoon_picks.txt) 标注机构活跃度")
    args = p.parse_args()

    conn = _conn()
    end_date = args.end_date or _latest_date(conn)

    if args.code:
        r = score_for(args.code, end_date=end_date, conn=conn)
        print(f"\n  {args.code} 机构活跃度 (基准日 {end_date})")
        for k, v in r.items():
            print(f"    {k}: {v}")
    elif args.cross_afternoon:
        picks_file = "tools/last_afternoon_picks.txt"
        if not os.path.exists(picks_file):
            print(f"  ⚠️ {picks_file} 不存在, 先跑 run_today_afternoon.py 生成")
            conn.close()
            return
        codes = [l.strip()[:6] for l in open(picks_file) if l.strip()[:6].isdigit()]
        rows = enrich_picks(codes, end_date=end_date, conn=conn)
        print(f"\n  午后选股候选 × 机构活跃度 (基准日 {end_date})")
        print(f"  {'代码':<7}{'名称':<9}{'机构分':>6}  信号")
        for c, n, s, sig in rows:
            print(f"  {c:<7}{str(n or '')[:7]:<9}{s:>6.0f}  {sig}")
    else:
        top = calc_top(end_date=end_date, top_n=args.top_n, conn=conn)
        print(f"\n{'='*112}")
        print(f"  全市场机构活跃度 Top{args.top_n} (基准日 {end_date})  5维: 龙虎榜机构40%+户数20%+大宗10%+研报15%+增减持5%")
        print(f"  ⚠️ 北向个股维度因 2024-08 政策停止已弃用")
        print(f"{'='*112}")
        print(f"{'#':>2} {'代码':<7}{'名称':<9}{'综合':>4}{'龙虎净(亿)':>10}{'天':>3}{'户数%':>7}{'大宗':>5}{'研报':>4}{'增减':>4}  信号")
        print("-" * 112)
        for i, (code, r) in enumerate(top.iterrows(), 1):
            sig = []
            if pd.notna(r.get("龙虎榜净买入亿")) and r["龙虎榜净买入亿"] > 0:
                sig.append("机构净买")
            if pd.notna(r.get("股东户数变化%")) and r["股东户数变化%"] < 0:
                sig.append("筹码集中")
            if pd.notna(r.get("研报篇数")) and r["研报篇数"] >= 3:
                sig.append("研报覆盖")
            if pd.notna(r.get("增减持次")) and r["增减持次"] > 0:
                sig.append("股东异动")
            print(f"{i:>2} {code:<7}{str(r['name'])[:7]:<9}{r['综合分']:>4.0f}"
                  f"{_fmt(r.get('龙虎榜净买入亿'),'{:+.1f}'):>10}{_fmt(r.get('龙虎榜天数'),'{:.0f}'):>3}"
                  f"{_fmt(r.get('股东户数变化%'),'{:+.1f}'):>7}{_fmt(r.get('大宗笔数'),'{:.0f}'):>5}"
                  f"{_fmt(r.get('研报篇数'),'{:.0f}'):>4}{_fmt(r.get('增减持次'),'{:.0f}'):>4}  {'+'.join(sig)}")
    conn.close()


if __name__ == "__main__":
    main()
