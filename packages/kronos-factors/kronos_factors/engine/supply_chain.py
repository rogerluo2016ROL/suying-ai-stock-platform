"""大葱产业链解构选股 V2 — PG研报直查 + 评级维度."""

import os, re, time, logging
logger = logging.getLogger("kronos-factors.supply_chain")

CHAINS = {
    "半导体": {"industries": ["半导体", "元器件"], "layers": ["材料","设备","封测","设计"]},
    "新能源": {"industries": ["电气设备"], "layers": ["材料","光伏","电池","设备"]},
    "AI算力": {"industries": ["通信设备", "软件服务"], "layers": ["硬件","软件","应用"]},
    "机器人": {"industries": ["专用机械"], "layers": ["核心部件","整机","集成"]},
    "创新药": {"industries": ["化学制药", "生物制药", "医疗保健"], "layers": ["CXO","原料药","创新药"]},
}

MOAT_KW = {
    "独家垄断": (r"独家供应|唯一供应商|不可替代|垄断|寡头", 20),
    "行业龙头": (r"龙头|全球第一|国内第一|市占率第一|遥遥领先|平台型龙头", 15),
    "进口替代": (r"国产替代|进口替代|打破垄断|自主可控|填补空白", 10),
    "技术壁垒": (r"核心专利|技术壁垒|护城河|全球首发|率先突破", 10),
}

RATING_MAP = {"买入":5,"增持":4,"推荐":4,"强烈推荐":5,"跑赢行业":4,"持有":2,"中性":1,"谨慎推荐":2,"减持":-3,"卖出":-5,"回避":-4}


class SupplyChainEngine:
    mode = "supply_chain"

    def run(self, top_n=30, chain=None, min_score=30, **kw):
        from kronos_factors.scorer._db_stub import _get_db
        t0 = time.time()

        fin, broker, reports, peers = {}, {}, {}, {}
        try:
            import psycopg2
            pg = psycopg2.connect(os.environ.get("KRONOS_PG_URL","postgresql://kronos:kronos@localhost:6432/kronos"),connect_timeout=5)
            cur = pg.cursor()
            cur.execute("SELECT DISTINCT ON (code) code, roe, COALESCE(gross_margin,30), net_margin, debt_ratio, eps, revenue_growth, profit_growth FROM financial_indicator ORDER BY code, end_date DESC")
            for r in cur.fetchall():
                fin[str(r[0])]={"roe":float(r[1]or 0),"gross_margin":float(r[2]or 30),"net_margin":float(r[3]or 0),"debt_ratio":float(r[4]or 50),"eps":float(r[5]or 0),"revenue_growth":float(r[6]or 0),"profit_growth":float(r[7]or 0)}
            cur.execute("SELECT code, COUNT(DISTINCT broker) FROM broker_recommend GROUP BY code")
            for r in cur.fetchall(): broker[str(r[0])]=r[1]
            cur.execute("SELECT code, title, rating FROM research_reports_tushare WHERE code IS NOT NULL AND code != 'nan' LIMIT 50000")
            for r in cur.fetchall():
                code=str(r[0]or""); title=str(r[1]or""); rating=str(r[2]or"")
                if code not in reports: reports[code]={"moat":0,"sigs":[],"ratings":[]}
                for mt,(pat,sc) in MOAT_KW.items():
                    if re.search(pat,title):
                        reports[code]["moat"]=min(40,reports[code]["moat"]+sc)
                        if mt not in reports[code]["sigs"]: reports[code]["sigs"].append(mt)
                mapped=RATING_MAP.get(rating,0)
                if mapped!=0: reports[code]["ratings"].append(mapped)
            cur.execute("SELECT industry, COUNT(*) FROM stocks WHERE is_st=0 GROUP BY industry")
            for r in cur.fetchall(): peers[r[0]]=r[1]
            pg.close()
        except Exception as e: logger.warning("PG: %s",e)

        with _get_db(readonly=True) as db:
            names,industries={},{}
            for r in db.execute("SELECT code,name,industry FROM stocks WHERE is_st=0").fetchall():
                names[r["code"]]=r["name"]or""; industries[r["code"]]=r["industry"]or""
            chains_to_run={chain:CHAINS[chain]} if chain in CHAINS else CHAINS
            picks=[]
            for ck,cd in chains_to_run.items():
                candidates=set()
                for ind in cd["industries"]:
                    for r in db.execute("SELECT code FROM stocks WHERE is_st=0 AND industry LIKE ?",(f"%{ind}%",)).fetchall():
                        candidates.add(r["code"])
                for code in candidates:
                    name=names.get(code,""); industry=industries.get(code,"")
                    fd=fin.get(code,{}); bc=broker.get(code,0); rp=reports.get(code,{"moat":0,"sigs":[],"ratings":[]})

                    # 1. Moat (40%)
                    moat=rp.get("moat",0); moat_sigs=rp.get("sigs",[])[:]
                    if bc>=5: moat=min(40,moat+8); moat_sigs.append(f"{bc}券商")
                    elif bc>=3: moat=min(40,moat+4)
                    pc=peers.get(industry,100)
                    if pc<=5: moat=min(40,moat+10); moat_sigs.append(f"仅{pc}家")
                    elif pc<=10: moat=min(40,moat+5); moat_sigs.append(f"{pc}家寡头")

                    # 2. Growth (30%)
                    rg=fd.get("revenue_growth",0); pg=fd.get("profit_growth",0)
                    growth=10.0
                    if rg>30:growth+=12
                    elif rg>20:growth+=9
                    elif rg>10:growth+=6
                    elif rg>0:growth+=3
                    if pg>30:growth+=10
                    elif pg>20:growth+=7
                    elif pg>10:growth+=4
                    elif pg>0:growth+=2
                    if rg>15 and pg>15:growth+=5
                    if rg>15 and pg>rg:growth+=3
                    growth=min(30,growth)

                    # 3. Profit (15%)
                    roe=fd.get("roe",0); gm=fd.get("gross_margin",30); debt=fd.get("debt_ratio",50)
                    profit=5.0
                    if roe>25:profit+=5
                    elif roe>15:profit+=4
                    elif roe>8:profit+=2
                    if gm>60:profit+=5
                    elif gm>40:profit+=3
                    elif gm>20:profit+=1
                    if debt<30:profit+=3
                    elif debt<50:profit+=2
                    elif debt>70:profit-=2
                    profit=max(0,min(15,profit))

                    # 4. Rating (10%) + Consensus (5%)
                    ratings=rp.get("ratings",[])
                    rating_score=5.0
                    if ratings: rating_score=min(10,5+sum(ratings)/len(ratings)*0.5)
                    consensus=min(5,bc*1.0)
                    total=moat+growth+profit+rating_score+consensus
                    if total<min_score: continue
                    grade="S" if total>=80 else("A" if total>=65 else("B" if total>=50 else"C"))

                    picks.append({"code":code,"name":name,"industry":industry,"chain":ck,"layer":cd["layers"][0],
                        "total_score":round(total,1),"grade":grade,"moat_score":moat,"moat_signals":moat_sigs[:4],
                        "growth_score":round(growth,1),"profit_score":round(profit,1),
                        "rating_score":round(rating_score,1),"consensus_score":round(consensus,1),
                        "revenue_growth":rg,"profit_growth":pg,"roe":roe,"gross_margin":gm,"report_count":len(ratings)})

        seen={}
        for p in sorted(picks,key=lambda x:-x["total_score"]):
            if p["code"] not in seen: seen[p["code"]]=p
        picks=sorted(seen.values(),key=lambda x:-x["total_score"])[:top_n]
        elapsed=time.time()-t0
        print(f"产业链解构V2: {len(picks)} picks, {len(set(p['chain'] for p in picks))} chains ({elapsed:.1f}s)")
        return {"mode":self.mode,"picks":picks,"total_scored":len(picks),"elapsed":elapsed}
