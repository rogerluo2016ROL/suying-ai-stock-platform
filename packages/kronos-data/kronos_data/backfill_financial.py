"""supply_chain financial_indicator 历史回填 (P4 前置).

回填产业链候选池的历史 fina_indicator growth 字段 (revenue_growth/profit_growth 等),
修复 etl 列名映射缺陷导致的全期 NULL. 用 update 模式回填已有行 + 扩展历史 code 覆盖.

用法:
  PYTHONPATH=packages/kronos-data python -m kronos_data.backfill_financial \\
      --start 2020Q1 --end 2025Q4
"""

import argparse
import sys


def _quarters(start: str, end: str) -> list:
    """生成 [start, end] 区间季度列表 (YYYYMMDD, 如 20200331). start/end 格式 YYYYQN."""
    def parse(q):
        y, qn = int(q[:4]), int(q[5])
        return y, qn
    sy, sq = parse(start); ey, eq = parse(end)
    out = []
    y, q = sy, sq
    while (y, q) <= (ey, eq):
        md = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}[q]
        out.append(f"{y}{md}")
        q += 1
        if q > 4:
            q, y = 1, y + 1
    return out


def _chain_codes() -> list:
    """产业链候选池 codes (按 supply_chain CHAINS 的 industry LIKE 取, ~1900 股)."""
    from kronos_data.etl import _get_etl_db
    from kronos_factors.engine.supply_chain import CHAINS
    db = _get_etl_db()
    codes = set()
    for cd in CHAINS.values():
        for ind in cd["industries"]:
            for r in db.execute("SELECT code FROM stocks WHERE is_st=0 AND industry LIKE ?", (f"%{ind}%",)).fetchall():
                codes.add(r["code"])
    return sorted(codes)


def main():
    ap = argparse.ArgumentParser(description="financial_indicator 历史回填 (P4 前置)")
    ap.add_argument("--start", default="2020Q1", help="起始季度 YYYYQN")
    ap.add_argument("--end", default="2025Q4", help="结束季度 YYYYQN")
    ap.add_argument("--codes", default="chain", choices=["chain", "all"], help="chain=产业链候选池, all=全市场")
    args = ap.parse_args()

    from kronos_data.etl import _sync_per_stock_financial, _get_all_codes, _get_etl_db

    periods = _quarters(args.start, args.end)
    print(f"回填区间: {args.start}~{args.end} = {len(periods)} 季度 {periods}", flush=True)

    if args.codes == "chain":
        codes = _chain_codes()
    else:
        codes = _get_all_codes(_get_etl_db())
    print(f"回填股票: {len(codes)} 只 ({args.codes})", flush=True)

    fields = ("ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin,"
              "debt_to_assets,eps,current_ratio,or_yoy,netprofit_yoy")
    # 分批回填 (每批 200 股 × 全部季度), 便于进度可见 + 限流可控
    BATCH = 200
    total_written = 0
    for i in range(0, len(codes), BATCH):
        batch = codes[i:i + BATCH]
        res = _sync_per_stock_financial("financial_indicator", "fina_indicator", fields, periods,
                                        conflict_action="update", codes=batch)
        total_written += res.get("written", 0)
        print(f"  批次 {i // BATCH + 1}/{(len(codes) + BATCH - 1) // BATCH}: "
              f"{len(batch)} 股, 累计写入 {total_written} 行", flush=True)
    print(f"\n回填完成: {len(codes)} 股 × {len(periods)} 季度, 总写入 {total_written} 行", flush=True)


if __name__ == "__main__":
    main()
