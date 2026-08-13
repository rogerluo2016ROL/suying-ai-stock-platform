#!/usr/bin/env python3
"""
Mirror a research-pipeline run (result.json) → 妙搭 content dashboard app DB.

Reads outputs/pipeline_runs/<date>/<ts>_<model>/result.json, writes one
research_run row + N research_pick rows (upsert). The 妙搭 content dashboard
reads these. Run after each pipeline run (or scan latest per model).

    python tools/sync_research_run_to_dashboard.py --result outputs/pipeline_runs/2026-08-05/20260805_143019_qishen_afternoon/result.json
    python tools/sync_research_run_to_dashboard.py --scan-latest   # 每个模型最新一条
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "push_observability.json"


def _cfg():
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    return raw


def _cli(args, timeout=90):
    p = subprocess.run(["lark-cli", *args, "--as", "user", "--format", "json"],
                       capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"non-json: {(p.stdout or '')[:120]}"}


def _q(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def _qjson(v) -> str:
    return _q(json.dumps(v, ensure_ascii=False) if v is not None else None)


def extract(result: dict) -> dict:
    """Pull run + picks from a result.json (stock/bond/brief aware)."""
    pipeline = result.get("pipeline") or {}
    mode = result.get("mode") or pipeline.get("model_key") or ""
    is_cb = bool(mode in ("cb_auction_t0",)) or bool(result.get("bonds"))
    picks_in = result.get("picks") or []
    picks = []
    for i, p in enumerate(picks_in, 1):
        price = p.get("close_14") or p.get("price") or p.get("close")
        sec = (p.get("sector_resonance") or {}).get("sector") or p.get("industry") or p.get("sector")
        subscores = {k: p[k] for k in p if k.endswith("_score") and k not in ("total_score", "score")}
        extra = {k: p[k] for k in ("seal_weakness", "crowding_level", "market_env", "dist_to_limit",
                                    "atr_pct", "peer_count", "is_at_limit", "amount_yi_est") if k in p}
        picks.append({
            "rank": i, "code": p.get("code") or p.get("ts_code") or "",
            "name": p.get("name") or "", "industry": p.get("industry") or "",
            "sector": sec, "price": price, "gain_pct": p.get("gain_pct"),
            "score": p.get("total_score") or p.get("score"),
            "grade": p.get("grade") or p.get("quality_tier"),
            "is_cb": is_cb,
            "stk_code": p.get("stk_code"), "stk_name": p.get("stk_name"),
            "quality_tier": p.get("quality_tier"), "theme_score": p.get("theme_score"),
            "subscores": subscores, "extra": extra,
        })
    return {
        "run_id": pipeline.get("run_id") or "",
        "model": pipeline.get("model_key") or mode,
        "mode": mode,
        "trade_date": result.get("trade_date") or "",
        "time_slot": result.get("time_slot") or pipeline.get("planned_time_slot") or "",
        "started_at": pipeline.get("started_at"),
        "market_snapshot_time": pipeline.get("market_snapshot_time") or (result.get("market_strength") or {}).get("snapshot_time"),
        "total_picks": result.get("total_picks") or len(picks),
        "market_strength": result.get("market_strength"),
        "brief_data": {k: result.get(k) for k in ("global_indices", "indices", "picks_down", "news", "hot_news") if k in result} or None,
        "sector_resonance": result.get("sector_resonance"),
        "doc_url": (result.get("pipeline") or {}).get("lark_doc", {}).get("url") if isinstance((result.get("pipeline") or {}).get("lark_doc"), dict) else (result.get("pipeline") or {}).get("lark_doc"),
        "doc_title": None,
        "no_result_reason": result.get("no_result_reason") or result.get("candidate_reason"),
        "picks": picks,
    }


def build_sql(r: dict) -> str:
    if not r["run_id"]:
        return "-- no run_id"
    run_json = {"market_strength", "brief_data", "sector_resonance"}
    run_cols = ["run_id", "model", "mode", "trade_date", "time_slot", "started_at", "market_snapshot_time",
                "total_picks", "market_strength", "brief_data", "sector_resonance", "doc_url", "no_result_reason", "data_updated_at"]
    run_vals = [(_qjson(r.get(c)) if c in run_json else _q(r.get(c))) for c in run_cols[:-1]] + ["now()"]
    set_clause = ",".join(f"{c}=EXCLUDED.{c}" for c in run_cols if c != "run_id")
    sql = [f"INSERT INTO research_run ({','.join(run_cols)}) VALUES ({','.join(run_vals)}) ON CONFLICT (run_id) DO UPDATE SET {set_clause};"]
    if r["picks"]:
        pick_json = {"subscores", "extra"}
        pcols = ["run_id", "rank", "code", "name", "industry", "sector", "price", "gain_pct", "score",
                 "grade", "is_cb", "stk_code", "stk_name", "quality_tier", "theme_score", "subscores", "extra"]
        vals = []
        for p in r["picks"]:
            if not p["code"]:
                continue
            row = [_q(r["run_id"])] + [(_qjson(p.get(c)) if c in pick_json else _q(p.get(c))) for c in pcols[1:]]
            vals.append("(" + ",".join(row) + ")")
        if vals:
            pset = ",".join(f"{c}=EXCLUDED.{c}" for c in pcols if c not in ("run_id", "code"))
            sql.append(f"INSERT INTO research_pick ({','.join(pcols)}) VALUES {','.join(vals)} ON CONFLICT (run_id,code) DO UPDATE SET {pset};")
    return "\n".join(sql)


def write_db(app_id: str, env: str, sql: str) -> dict:
    f = Path("./_sync_research_run.sql")
    f.write_text(sql, encoding="utf-8")
    try:
        return _cli(["apps", "+db-execute", "--app-id", app_id, "--environment", env, "--yes", "--file", "./_sync_research_run.sql"])
    finally:
        try: f.unlink()
        except Exception: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", help="path to a result.json")
    ap.add_argument("--scan-latest", action="store_true", help="sync latest run per model under outputs/pipeline_runs")
    ap.add_argument("--environment", default=None)
    args = ap.parse_args()
    cfg = _cfg()
    app_id = cfg.get("dashboard_app_id", "")
    env = args.environment or cfg.get("dashboard_environment", "online")
    if not app_id:
        print("[sync-run] missing dashboard_app_id", file=sys.stderr); return 1

    targets = []
    if args.result:
        targets = [Path(args.result)]
    elif args.scan_latest:
        root = Path("outputs/pipeline_runs")
        latest = {}
        for p in root.rglob("result.json"):
            model = p.parent.name.split("_", 2)[-1] if "_" in p.parent.name else p.parent.name
            # 路径含日期+时间戳(YYYY-MM-DD/YYYYMMDD_HHMMSS_*),按字符串取最大=时间最新
            if model not in latest or str(p) > str(latest[model]):
                latest[model] = p
        targets = list(latest.values())
    else:
        ap.error("provide --result or --scan-latest")

    for rf in targets:
        try:
            result = json.loads(rf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[sync-run] skip {rf}: {e}", file=sys.stderr); continue
        r = extract(result)
        sql = build_sql(r)
        res = write_db(app_id, env, sql)
        print(f"[sync-run] {r['model']} {r['trade_date']} run={r['run_id']} picks={len(r['picks'])} → {env}: {res.get('ok')} {(res.get('error') or '')[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
