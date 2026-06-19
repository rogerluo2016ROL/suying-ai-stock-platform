"""大葱产业链解构选股 — Supply Chain Decomposition Stock Selection.

中长线选股模型 (3-12月持有周期).
五条产业链 × 四维评分 (壁垒/成长/利润/共识).
"""

import os, re, time, logging
logger = logging.getLogger("kronos-factors.supply_chain")

CHAINS = {
    "半导体": {"industries": ["半导体", "元器件"], "layers": ["材料","设备","封测","设计"]},
    "新能源": {"industries": ["电气设备"], "layers": ["材料","光伏","电池","设备"]},
    "AI算力": {"industries": ["通信设备", "软件服务"], "layers": ["硬件","软件","应用"]},
    "机器人": {"industries": ["专用机械"], "layers": ["核心部件","整机","集成"]},
    "创新药": {"industries": ["化学制药", "生物制药", "医疗保健"], "layers": ["CXO","原料药","创新药"]},
}


class SupplyChainEngine:
    mode = "supply_chain"

    def run(self, top_n=30, chain=None, min_score=30, **kw):
        from kronos_factors.scorer._db_stub import _get_db
        t0 = time.time()

        # Load PG data
        fin, broker, industry_peers = {}, {}, {}
        try:
            import psycopg2
            pg = psycopg2.connect(os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"), connect_timeout=5)
            cur = pg.cursor()
            cur.execute("SELECT DISTINCT ON (code) code, roe, gross_margin, net_margin, debt_ratio, eps FROM financial_indicator ORDER BY code, end_date DESC")
            for r in cur.fetchall():
                fin[str(r[0])] = {"roe": float(r[1] or 0), "gross_margin": float(r[2] or 0), "net_margin": float(r[3] or 0), "debt_ratio": float(r[4] or 50), "eps": float(r[5] or 0), "revenue_growth": 0, "profit_growth": 0}
            cur.execute("SELECT DISTINCT ON (code) code, total_revenue, net_profit FROM financial_income ORDER BY code, end_date DESC")
            curr = {str(r[0]): (float(r[1] or 0), float(r[2] or 0)) for r in cur.fetchall()}
            cur.execute("SELECT code, total_revenue, net_profit FROM (SELECT code, total_revenue, net_profit, ROW_NUMBER() OVER (PARTITION BY code ORDER BY end_date DESC) as rn FROM financial_income) t WHERE rn=2")
            for r in cur.fetchall():
                code = str(r[0])
                if code in fin and code in curr:
                    pr, pi = float(r[1] or 0), float(r[2] or 0)
                    cr, ci = curr[code]
                    fin[code]["revenue_growth"] = round((cr/pr-1)*100, 1) if pr > 0 else 0
                    fin[code]["profit_growth"] = round((ci/pi-1)*100, 1) if pi > 0 else 0
            cur.execute("SELECT code, COUNT(DISTINCT broker) FROM broker_recommend GROUP BY code")
            for r in cur.fetchall(): broker[str(r[0])] = r[1]
            cur.execute("SELECT industry, COUNT(*) FROM stocks WHERE is_st=0 GROUP BY industry")
            for r in cur.fetchall(): industry_peers[r[0]] = r[1]
            pg.close()
        except Exception as e:
            logger.warning("PG load failed: %s", e)

        with _get_db(readonly=True) as db:
            names, industries = {}, {}
            for r in db.execute("SELECT code, name, industry FROM stocks WHERE is_st=0").fetchall():
                names[r["code"]] = r["name"] or ""
                industries[r["code"]] = r["industry"] or ""

            chains_to_run = {chain: CHAINS[chain]} if chain in CHAINS else CHAINS
            picks = []

            for ck, cd in chains_to_run.items():
                candidates = set()
                for ind in cd["industries"]:
                    for r in db.execute("SELECT code FROM stocks WHERE is_st=0 AND industry LIKE ?", (f"%{ind}%",)).fetchall():
                        candidates.add(r["code"])

                for ci, code in enumerate(candidates):
                    name = names.get(code, "")
                    industry = industries.get(code, "")
                    fd = fin.get(code, {})
                    bc = broker.get(code, 0)

                    # 1. Competitive Moat (40%) — broker coverage + industry scarcity
                    moat = min(40, bc * 4)  # 1 broker = 4 points
                    peer_cnt = industry_peers.get(industry, 100)
                    if peer_cnt <= 5: moat = min(40, moat + 15)
                    elif peer_cnt <= 10: moat = min(40, moat + 8)
                    moat_sigs = []
                    if bc >= 5: moat_sigs.append(f"{bc}家券商覆盖")
                    if peer_cnt <= 5: moat_sigs.append(f"行业仅{peer_cnt}家(稀缺)")
                    elif peer_cnt <= 10: moat_sigs.append(f"行业{peer_cnt}家(寡头)")

                    # 2. Growth (30%)
                    rg = fd.get("revenue_growth", 0)
                    pg = fd.get("profit_growth", 0)
                    growth = 10.0
                    if rg > 30: growth += 12
                    elif rg > 20: growth += 9
                    elif rg > 10: growth += 6
                    elif rg > 0: growth += 3
                    if pg > 30: growth += 10
                    elif pg > 20: growth += 7
                    elif pg > 10: growth += 4
                    elif pg > 0: growth += 2
                    if rg > 15 and pg > 15: growth += 5
                    if rg > 15 and pg > rg: growth += 3
                    growth = min(30, growth)

                    # 3. Profitability (20%)
                    roe = fd.get("roe", 0)
                    gm = fd.get("gross_margin", 0)
                    debt = fd.get("debt_ratio", 50)
                    profit = 5.0
                    if roe > 25: profit += 8
                    elif roe > 15: profit += 6
                    elif roe > 8: profit += 4
                    elif roe > 0: profit += 2
                    if gm > 60: profit += 6
                    elif gm > 40: profit += 4
                    elif gm > 20: profit += 2
                    if debt < 30: profit += 3
                    elif debt < 50: profit += 2
                    elif debt > 70: profit -= 3
                    profit = max(0, min(20, profit))

                    # 4. Consensus (10%)
                    consensus = min(10, bc * 2)

                    total = moat + growth + profit + consensus
                    if total < min_score: continue

                    grade = "S" if total >= 80 else ("A" if total >= 65 else ("B" if total >= 50 else "C"))

                    picks.append({
                        "code": code, "name": name, "industry": industry,
                        "chain": ck, "layer": cd["layers"][0],
                        "total_score": round(total, 1), "grade": grade,
                        "moat_score": moat, "moat_signals": moat_sigs[:3],
                        "growth_score": round(growth, 1),
                        "profit_score": round(profit, 1),
                        "consensus_score": round(consensus, 1),
                        "revenue_growth": rg, "profit_growth": pg,
                        "roe": roe, "gross_margin": gm,
                    })

        # Dedup: each stock in best chain
        seen = {}
        for p in sorted(picks, key=lambda x: -x["total_score"]):
            if p["code"] not in seen: seen[p["code"]] = p
        picks = sorted(seen.values(), key=lambda x: -x["total_score"])[:top_n]

        elapsed = time.time() - t0
        chn = len(set(p["chain"] for p in picks))
        print(f"产业链解构: {len(picks)} picks, {chn} chains ({elapsed:.1f}s)")
        return {"mode": self.mode, "picks": picks, "total_scored": len(picks), "elapsed": elapsed}
