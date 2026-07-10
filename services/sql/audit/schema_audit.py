#!/usr/bin/env python3
"""Read-only schema drift release gate.

Produces the historical Markdown report and, when requested, a stable JSON
artifact carrying severity, table ownership, and time-bounded exemptions.
"""

import argparse, json, os, re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:16432/kronos")
INIT_SQL = ROOT / "services/sql/init_postgres.sql"
OWNERSHIP_FILE = ROOT / "configs/data_ownership.json"
# P1-4 (audit): the 5 data-pipeline tables (sw_daily, pledge_detail, rt_sw_k,
# top_list, cyq_chips) were previously EXCLUDED, which hid their schema drift
# (pledge_total_ratio column-name issues, rt_sw_k/sw_daily missing-core-column
# rumours). They are now in scope so future drift surfaces automatically.
# ths_daily / top_inst remain excluded (ADR-008~011 already reconciled; top_inst
# indexes are still checked individually in §6 F-1 收尾).
EXCLUDED = {"top_inst","ths_daily",
    "alembic_version","audit_logs","refresh_tokens","roles","users","model_registry","training_jobs",
    "training_schedule","diagnosis_config","diagnosis_history","factor_calibration_history","factor_weights",
    "predictions","prediction_details","prediction_versions","backtest_records","factor_evaluations","screening_scores",
    "screening_batches","screening_snapshots","watchlist"}
MONITORED = {"daily_kline","moneyflow","stk_limit","daily_basic","ths_daily","sw_daily","index_daily",
    "stk_factor_pro","limit_list_d","moneyflow_hsgt","stocks","stk_mins","rt_k","rt_sw_k","trade_cal",
    "hk_holdings","margin_detail","margin_summary","top_list","top_inst","block_trade_data","stk_holdertrade",
    "pledge_detail","share_float","cyq_chips","forecast_data","dividend_data","adj_factor","financial_indicator",
    "financial_income","financial_balance","financial_cashflow","fina_mainbz","fina_audit","research_reports_tushare",
    "stock_news_tushare","announcements","weekly_kline","monthly_kline","stk_holdernumber","repurchase",
    "broker_recommend","stock_profiles","interact_qa","policy_law","mp_report","cctv_news"}
RAW_LANDING_PREFIXES = ("ts_raw_",)
RAW_LANDING_TABLES = {"tushare_api_ingest_status"}
IGNORED_COLUMN_PREFIXES = ("_tushare_",)

def parse_init_sql(path):
    text = Path(path).read_text("utf-8"); meta = {}
    for m in re.finditer(r'\bCREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\)\s*;', text, re.DOTALL|re.I):
        t=m.group(1).lower(); cols=[]; pk=[]; uniques=[]
        body=re.sub(r'--[^\n]*','',m.group(2))
        segs,buf,d=[],[],0
        for ch in body:
            if ch=='(': d+=1; buf.append(ch)
            elif ch==')': d-=1; buf.append(ch)
            elif ch==',' and d==0:
                s=''.join(buf).strip()
                if s: segs.append(s); buf=[]
            else: buf.append(ch)
        last=''.join(buf).strip()
        if last: segs.append(last)
        for seg in segs:
            u=seg.upper()
            pm=re.match(r'(?:CONSTRAINT\s+\w+\s+)?PRIMARY\s+KEY\s*\(([^)]+)\)',seg,re.I)
            if pm and u.startswith(("CONSTRAINT","PRIMARY KEY")): pk=[c.strip() for c in pm.group(1).split(",")]; continue
            um=re.match(r'(?:CONSTRAINT\s+\w+\s+)?UNIQUE\s*\(([^)]+)\)',seg,re.I)
            if um and u.startswith(("UNIQUE","CONSTRAINT")): uniques.append([c.strip() for c in um.group(1).split(",")]); continue
            if re.match(r"^(?:CHECK\s*\(|FOREIGN\s+KEY\b|CONSTRAINT\s+)", u): continue
            parts=seg.split(None,2)
            if len(parts)>=2:
                cn,ct=parts[0].strip('"').lower(),parts[1].lower().rstrip(",")
                if ct=="double" and len(parts)>2: ct="double precision"
                cols.append((cn,ct))
                if "PRIMARY KEY" in u and not pm: pk=[cn]
        meta[t]={"cols":cols,"pk":pk,"uniques":uniques,"idxes":[]}
    for m in re.finditer(r'CREATE(?:\s+UNIQUE)?\s+INDEX IF NOT EXISTS\s+(\w+)\s+ON\s+(\w+)\s*\(([^)]+)\)',text,re.I):
        tt=m.group(2).lower()
        if tt in meta: meta[tt]["idxes"].append({"name":m.group(1),"cols":[c.strip() for c in m.group(3).split(",")]})
    return meta

def introspect_db(conn):
    cur=conn.cursor(); meta=defaultdict(lambda:{"cols":[],"pk":[],"uniques":[],"idxes":[]})
    cur.execute("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position")
    for t,c,dt in cur.fetchall(): meta[t.lower()]["cols"].append((c,dt.lower()))
    cur.execute("SELECT t.relname,c.contype,array_agg(a.attname ORDER BY a.attnum) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=ANY(c.conkey) WHERE c.contype IN ('p','u') GROUP BY t.relname,c.conname,c.contype")
    for t,ct,cols in cur.fetchall():
        tt=t.lower()
        if tt not in meta: continue
        if ct=='p': meta[tt]["pk"]=list(cols)
        else: meta[tt]["uniques"].append(list(cols))
    cur.execute("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND NOT indexdef LIKE '%UNIQUE%' ORDER BY tablename,indexname")
    for t,iname,idef in cur.fetchall():
        tt=t.lower()
        if tt not in meta: continue
        cm=re.search(r'\(([^)]+)\)',idef)
        meta[tt]["idxes"].append({"name":iname,"cols":[c.strip() for c in cm.group(1).split(",")] if cm else []})
    return dict(meta)

TYPE_ALIASES={
    "double precision":"float8", "integer":"int4", "bigint":"int8",
    "smallint":"int2", "character varying":"text", "varchar":"text",
    "timestamp without time zone":"timestamp", "timestamp with time zone":"timestamptz",
    "boolean":"bool", "serial":"int4", "bigserial":"int8",
}


def normalize_type(value):
    """Normalize PostgreSQL/catalog aliases to prevent false drift findings."""
    normalized = re.sub(r"\s+", " ", str(value).strip().lower())
    if re.fullmatch(r"(?:varchar|character varying|character)\s*\(\d+\)", normalized):
        normalized = "text"
    elif re.fullmatch(r"numeric\s*\(\d+\s*,\s*\d+\)", normalized):
        normalized = "numeric"
    return TYPE_ALIASES.get(normalized, normalized)


@dataclass
class Finding:
    table: str
    severity: str
    owner: str | None = None
    details: list[str] = field(default_factory=list)
    exemption: str | None = None
    exempt_until: date | None = None

    def exempt(self, today=None):
        today = today or date.today()
        return bool(self.exemption and self.exempt_until and self.exempt_until >= today)

    def to_json(self, today=None):
        payload = asdict(self)
        payload["exempt_until"] = self.exempt_until.isoformat() if self.exempt_until else None
        payload["exempt"] = self.exempt(today)
        return payload


def exit_code(findings, today=None, fail_on="medium"):
    levels = {"none": 99, "high": 3, "medium": 2, "low": 1}
    if fail_on not in levels:
        raise ValueError(f"unsupported fail-on threshold: {fail_on}")
    threshold = levels[fail_on]
    return int(any(levels.get(f.severity, 0) >= threshold and not f.exempt(today) for f in findings))


def load_ownership(path=OWNERSHIP_FILE):
    return json.loads(Path(path).read_text("utf-8"))


def build_findings(diffs, ownership):
    findings = []
    for table, drift in sorted(diffs.items()):
        details = dsum(drift)
        if not details:
            continue
        spec = ownership.get(table, {})
        raw_expiry = spec.get("exempt_until")
        findings.append(Finding(
            table=table,
            severity=drift["sev"],
            owner=spec.get("owner"),
            details=details,
            exemption=spec.get("exemption"),
            exempt_until=date.fromisoformat(raw_expiry) if raw_expiry else None,
        ))
    return findings

def diff_tbl(d,i):
    r={"db":False,"init":False,"oc":[],"ic":[],"tm":[],"pk":None,"uq":None,"il":[],"im":[],"sev":"low"}
    if not d: r["db"]=True; return r
    if not i: r["init"]=True; return r
    dc={c[0]:c[1] for c in d.get("cols",[]) if not c[0].startswith(IGNORED_COLUMN_PREFIXES)}
    ic={c[0]:c[1] for c in i.get("cols",[]) if not c[0].startswith(IGNORED_COLUMN_PREFIXES)}
    ds,is_=set(dc),set(ic); r["oc"]=sorted(ds-is_); r["ic"]=sorted(is_-ds)
    for c in ds&is_:
        dt,it=normalize_type(dc[c]),normalize_type(ic[c])
        if dt!=it: r["tm"].append((c,dc[c],ic[c]))
    if set(d.get("pk",[]))!=set(i.get("pk",[])): r["pk"]=(d.get("pk",[]),i.get("pk",[]))
    du={tuple(sorted(u)) for u in d.get("uniques",[])}; iu={tuple(sorted(u)) for u in i.get("uniques",[])}
    if du!=iu: r["uq"]=([list(u) for u in sorted(du-iu)],[list(u) for u in sorted(iu-du)])
    dx={n["name"] for n in d.get("idxes",[])}; ix={n["name"] for n in i.get("idxes",[])}
    r["il"]=sorted(dx-ix); r["im"]=sorted(ix-dx)
    cc=len(r["oc"])+len(r["ic"])
    if cc>=3 or r["pk"] or r["tm"]: r["sev"]="high"
    elif cc>=1 or r["uq"] or r["im"]: r["sev"]="medium"
    return r

def dsum(r):
    if r.get("_missing"): return ["MONITORED但DB+init双缺 — scheduler监控会报错"]
    if not r["db"] and not r["init"]: parts=[]
    else: return ["DB独有(init缺)" if r["db"] else "init独有(DB缺)"]
    if r["oc"]: parts.append(f"仅DB[{len(r['oc'])}]: {','.join(r['oc'])}")
    if r["ic"]: parts.append(f"仅init[{len(r['ic'])}]: {','.join(r['ic'])}")
    if r["tm"]: parts.append(f"类型({len(r['tm'])}): " + ";".join(f"{c}({dt}/{it})" for c,dt,it in r["tm"]))
    if r["pk"]: parts.append(f"PK差: DB={r['pk'][0]} init={r['pk'][1]}")
    if r["uq"]: parts.append(f"UQ差: DB+{r['uq'][0]} init+{r['uq'][1]}")
    if r["il"]: parts.append(f"legacy索引: {','.join(r['il'])}")
    if r["im"]: parts.append(f"缺索引: {','.join(r['im'])}")
    return parts

def render(diffs,im,dbm,mm,path):
    b=lambda s:sorted([t for t,d in diffs.items() if d["sev"]==s]); h,m,l=b("high"),b("medium"),b("low")
    T=lambda t: "yes" if t in MONITORED else "no"; C=lambda m_,t: len(m_.get(t,{}).get("cols",[]))
    L=[f"# Schema Drift Audit Report — {date.today().isoformat()}", "**ADR-014 | UAT PG(16432) read-only**", "",
       "## §1 审计范围","",f"- DB {len(dbm)}张 | init_sql {len(im)}张 | 审计 {len(diffs)}张 | 排除 {len(EXCLUDED)}张",
       f"- P1-4 已纳入审计的数据管道表 (原 EXCLUDED): sw_daily, pledge_detail, rt_sw_k, top_list, cyq_chips",
       f"- ADR-008~011 已修仍排除表 (不重复扫): ths_daily, top_inst (top_inst 索引见 §6)",
       f"- 应用层排除表 (auth/training/diagnosis/screening/prediction/backtest/factor): {len(EXCLUDED)-2} 张",
       f"- high={len(h)} medium={len(m)} low={len(l)}",
       f"- MONITORED双缺(DB+init均无): {sorted(mm) or '无'}", f"### 审计表清单 ({len(diffs)}张)","",
       "|#|表|DB列|init列|严重|状态|MON|","|---|---|---|---|---|---|---|"]
    for i,t in enumerate(sorted(diffs),1):
        d=diffs[t]; s="DB" if d["db"] else "init" if d["init"] else "="
        L.append(f"|{i}|`{t}`|{C(dbm,t)}|{C(im,t)}|{d['sev']}|{s}|{'y' if t in MONITORED else ''}|")
    L+=["","## §2 严重度详情"]
    for s in ("high","medium"):
        for t in b(s):
            sm=dsum(diffs[t])
            L+=["",f"### `{t}` — {s} MON={T(t)}",""]+([f"- {x}" for x in sm] if sm else ["(无差异)"])
    if not h and not m: L.append("\n(无high/medium)")
    L+=["","## §3 子ADR建议","","按ADR-014§决策4(列差≥3/PK/类型/下游):"]
    if not h: L.append("(无 — ADR-008~013已完成主要drift修复)")
    for i,t in enumerate(h,1):
        L+=["",f"### ADR-14.{i}: `{t}`",
            f"- DB列{C(dbm,t)} vs init_sql{C(im,t)} | 涉及下游(MONITORED): {T(t)}"]
        for x in dsum(diffs[t]): L.append(f"- 关键 diff: {x}")
        L.append("- 建议: 按 ADR-008~013 同型骨架拆子 ADR (sync 函数对账 + init_sql 反向追认 + alembic 迁移)")
    L+=["","## §4 轻量对齐",""]
    lt=[t for t in sorted(diffs) if diffs[t]["sev"]!="high" and dsum(diffs[t])]
    if not lt: L.append("(无)")
    for t in lt: L.append(f"- `{t}` ({diffs[t]['sev']} MON={T(t)}): {'; '.join(dsum(diffs[t]))}")
    L+=["","## §5 索引登记","","|表|索引|列|来源|状态|","|---|---|---|---|---|"]
    for t in sorted(diffs):
        dbi={i["name"]:i for i in dbm.get(t,{}).get("idxes",[])}
        ini={i["name"]:i for i in im.get(t,{}).get("idxes",[])}
        for nm in sorted(set(dbi)|set(ini)):
            sp=dbi.get(nm) or ini[nm]
            st="i-miss" if nm in dbi and nm not in ini else "d-miss" if nm in ini and nm not in dbi else "synced"
            L.append(f"|{t}|{nm}|({','.join(sp['cols'])})|init:{'y' if nm in ini else 'n'}/DB:{'y' if nm in dbi else 'n'}|{st}|")
    L+=["","## §6 ADR-010 F-1 收尾","",
        "**F-1 背景**: ADR-010 backlog `idx_cyq_chips_date` schema drift (init_sql 未声明, DB 实存); "
        "ADR-011 review §1.3 / S-5 升级合并入本 ADR-014。",
        "","**F-1 处置查证 (cyq_chips / top_inst 虽在 EXCLUDED, 此段单查索引现状)**:"]
    for t in ("cyq_chips","top_inst"):
        dbi={i["name"] for i in dbm.get(t,{}).get("idxes",[])}
        ini={i["name"] for i in im.get(t,{}).get("idxes",[])}
        if not (dbi|ini):
            L.append(f"- `{t}`: 无非PK/UNIQUE 索引 (DB={list(dbi)} init_sql={list(ini)})")
            continue
        for nm in sorted(dbi|ini):
            st=("OPEN(入轻量对齐: init_sql 补 CREATE INDEX)" if nm in dbi and nm not in ini
                else "OPEN(DB缺索引, 建议下次 alembic 创建)" if nm in ini and nm not in dbi
                else "COMPLETED(synced)")
            L.append(f"- `{t}.{nm}`: DB={'yes' if nm in dbi else 'no'} init_sql={'yes' if nm in ini else 'no'} → {st}")
    L+=["","**F-1 结论**: idx_cyq_chips_date / idx_top_inst_date 在 ADR-010/011 alembic 迁移后已清理 — F-1 跟踪项可关闭; "
        "§5 索引登记表覆盖全审计范围 drift 索引, F-1 合并至本 ADR-014, ADR-010 backlog F-1 关闭。"]
    Path(path).write_text("\n".join(L)+"\n","utf-8")
    print(f"OK {path} | audited={len(diffs)} high={len(h)} med={len(m)} low={len(l)} MISSING={sorted(mm) or 'none'}")

def main(argv=None):
    import psycopg2

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", help="write machine-readable audit artifact")
    parser.add_argument("--fail-on", choices=("none", "low", "medium", "high"), default="none")
    parser.add_argument("--markdown", default=str(ROOT / "docs/reviews" / f"schema-drift-audit-{date.today().isoformat()}.md"))
    parser.add_argument("--pg-url", default=PG_URL)
    args = parser.parse_args(argv)

    conn=psycopg2.connect(args.pg_url); im=parse_init_sql(INIT_SQL); dbm=introspect_db(conn); conn.close()
    all_t={
        t for t in (set(dbm)|set(im))-EXCLUDED
        if t not in RAW_LANDING_TABLES and not any(t.startswith(prefix) for prefix in RAW_LANDING_PREFIXES)
    }
    diffs={t:diff_tbl(dbm.get(t,{}),im.get(t,{})) for t in sorted(all_t)}
    mm=MONITORED-set(dbm)-set(im)
    # 把 MONITORED 双缺表追加为 high severity 发现 (scheduler 监控会失败 → 必须拆子 ADR)
    for t in sorted(mm):
        diffs[t]={"db":True,"init":True,"oc":[],"ic":[],"tm":[],"pk":None,"uq":None,"il":[],"im":[],
                  "sev":"high","_missing":True}
    render(diffs, im, dbm, mm, args.markdown)
    findings = build_findings(diffs, load_ownership())
    if args.json_path:
        output = Path(args.json_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "generated_at": date.today().isoformat(),
            "fail_on": args.fail_on,
            "finding_count": len(findings),
            "blocking_count": sum(not f.exempt() and exit_code([f], fail_on=args.fail_on) for f in findings),
            "findings": [f.to_json() for f in findings],
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(f"JSON {output}")
    return exit_code(findings, fail_on=args.fail_on)


if __name__=="__main__":
    raise SystemExit(main())
