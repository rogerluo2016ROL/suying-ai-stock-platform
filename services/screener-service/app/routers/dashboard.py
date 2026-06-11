"""Dashboard API — 选股看板数据源.

Serves orchestrator output (merged picks, predictions, backtest) and data freshness.
Works standalone — reads JSON files, no DB dependency needed for core endpoints.
"""

import glob, json, os, subprocess
from datetime import date, datetime
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# ── Path resolution ──
_FILE = os.path.abspath(__file__)
# Navigate up:  dashboard.py → routers → app → screener-service → services → project_root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_FILE)))))
KRONOS_ROOT = os.path.join(_PROJECT_ROOT, "Kronos")
OUTPUTS_DIR = os.path.join(KRONOS_ROOT, "outputs")
TOOLS_DIR = os.path.join(KRONOS_ROOT, "tools")


def _find_latest_orchestrator(date_str: str = None) -> dict | None:
    """Find the latest orchestrator output for a date."""
    if date_str:
        pattern = os.path.join(OUTPUTS_DIR, f"orchestrator_{date_str.replace('-','')}", "merged_picks.json")
    else:
        # Find latest
        dirs = sorted(glob.glob(os.path.join(OUTPUTS_DIR, "orchestrator_*")), reverse=True)
        if not dirs:
            return None
        pattern = os.path.join(dirs[0], "merged_picks.json")

    if os.path.exists(pattern):
        with open(pattern) as f:
            return json.load(f)

    # Try glob
    matches = sorted(glob.glob(pattern.replace(".json", "*.json") if "*" not in pattern else pattern))
    if matches:
        with open(matches[-1]) as f:
            return json.load(f)
    return None


def _find_daily_report(date_str: str = None) -> str | None:
    """Find latest daily report markdown."""
    if date_str:
        path = os.path.join(OUTPUTS_DIR, f"daily_report_{date_str}.md")
    else:
        files = sorted(glob.glob(os.path.join(OUTPUTS_DIR, "daily_report_*.md")), reverse=True)
        path = files[0] if files else None

    if path and os.path.exists(path):
        with open(path) as f:
            return f.read()
    return None


def _find_backtest(date_str: str = None) -> dict | None:
    """Find backtest data from daily report."""
    if date_str is None:
        date_str = date.today().strftime("%Y-%m-%d")
    # Try to extract from daily report
    report = _find_daily_report(date_str)
    if not report:
        return None

    # Parse key metrics from markdown report
    result = {"date": date_str, "metrics": {}}
    for line in report.split("\n"):
        line = line.strip()
        if line.startswith("- **平均收益**:"):
            result["metrics"]["avg_return"] = line.split(":")[-1].strip()
        elif line.startswith("- **胜率**:"):
            result["metrics"]["win_rate"] = line.split(":")[-1].strip()
        elif line.startswith("- **最佳**:"):
            result["metrics"]["best"] = line.split(":")[-1].strip()
        elif line.startswith("- **最差**:"):
            result["metrics"]["worst"] = line.split(":")[-1].strip()
    return result


@router.get("/summary")
async def dashboard_summary(date_param: str = Query(None, alias="date", description="YYYY-MM-DD, 默认最新")):
    """Get full dashboard summary: screening + backtest + predictions."""
    target = date_param or date.today().strftime("%Y-%m-%d")

    # 1. Orchestrator output
    orch = _find_latest_orchestrator(target)
    if orch is None:
        return {"status": "no_data", "date": target, "message": "尚无选股数据, 请先运行 orchestrator.py"}

    # 2. Count by consensus
    merged = orch.get("merged", [])
    dual = [m for m in merged if m.get("consensus", 0) >= 2]
    single = [m for m in merged if m.get("consensus", 0) == 1]

    # 3. Predictions
    predictions = orch.get("predictions", [])
    pred_up = sum(1 for p in predictions if p.get("pred_return_pct", 0) > 0)
    pred_down = sum(1 for p in predictions if p.get("pred_return_pct", 0) <= 0)

    # 4. Strategy status
    strategies = orch.get("strategies", {})

    # 5. Backtest
    backtest = _find_backtest(target)

    return {
        "date": orch.get("date", target),
        "elapsed": orch.get("elapsed", 0),
        "summary": {
            "total_picks": len(merged),
            "consensus_dual": len(dual),
            "consensus_single": len(single),
            "strategies_run": len(strategies),
            "predictions_total": len(predictions),
            "predictions_up": pred_up,
            "predictions_down": pred_down,
        },
        "strategies": strategies,
        "dual_consensus": dual[:10],
        "predictions": predictions[:10],
        "backtest": backtest,
    }


@router.get("/picks")
async def dashboard_picks(
    date_param: str = Query(None, alias="date"),
    sort_by: str = Query("consensus", description="consensus|score"),
    limit: int = Query(50),
):
    """Get merged picks with detail."""
    orch = _find_latest_orchestrator(date_param)
    if orch is None:
        return {"picks": [], "total": 0}

    merged = orch.get("merged", [])
    if sort_by == "score":
        merged = sorted(merged, key=lambda m: -m.get("best_score", 0))

    return {
        "picks": merged[:limit],
        "total": len(merged),
        "date": orch.get("date", ""),
    }


@router.get("/report")
async def dashboard_report(date_param: str = Query(None, alias="date")):
    """Get daily markdown report."""
    report = _find_daily_report(date_param)
    if report is None:
        return {"status": "no_data", "message": "尚无日报"}

    return {
        "date": date_param or date.today().strftime("%Y-%m-%d"),
        "format": "markdown",
        "content": report,
    }


@router.get("/freshness")
async def dashboard_freshness():
    """Run monitor_freshness.py and return JSON result."""
    script = os.path.join(TOOLS_DIR, "monitor_freshness.py")
    if not os.path.exists(script):
        return {"status": "error", "message": "monitor_freshness.py not found"}

    try:
        result = subprocess.run(
            ["python3", script, "--json"],
            cwd=KRONOS_ROOT, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return {"status": "error", "stderr": result.stderr[:500]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/sync/trigger")
async def trigger_sync(sync_type: str = "rt_min"):
    """手动触发数据同步 (代理到 data-service :8010).

    sync_type: rt_min | auction | post_market
    """
    import urllib.request
    DATA_SERVICE = "http://localhost:8010/api/v1/data"
    url = f"{DATA_SERVICE}/sync/{sync_type}"
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/sync/status")
async def sync_status():
    """查询数据同步状态."""
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:8010/api/v1/data/status", timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"status": "error", "message": "data-service not reachable"}


@router.get("/auction")
async def auction_picks(date_param: str = Query(None, alias="date")):
    """竞价分析: 快速 SQL 预取 (1-2s)."""
    target = date_param or date.today().strftime("%Y-%m-%d")
    try:
        import sqlite3, os
        from collections import defaultdict
        db_path = os.path.join(KRONOS_ROOT, "webui", "stock_screening.db")
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row

        snap = {}
        for r in db.execute(f"SELECT ts_code, open, high, low, close, volume, amount FROM stk_mins WHERE trade_time LIKE '{target} 09:35%' AND freq='5min'").fetchall():
            snap[r['ts_code'].split('.')[0]] = dict(r)

        pc = {}
        for r in db.execute(f"SELECT a.code, a.close FROM daily_kline a JOIN (SELECT code, MAX(trade_date) as pd FROM daily_kline WHERE trade_date < '{target}' GROUP BY code) b ON a.code=b.code AND a.trade_date=b.pd").fetchall():
            pc[r['code']] = r['close']

        mv = {}; ind_map = {}
        for r in db.execute('SELECT code, float_mv, industry FROM stocks').fetchall():
            mv[r['code']] = (r['float_mv'] or 0)
            ind_map[r['code']] = (r['industry'] or '其他')

        sector_cnt = defaultdict(int)
        results = []
        for code, s in snap.items():
            if code not in pc or code.startswith(('92','83','87','4')): continue
            pre = pc[code]; o = s['open']
            if o <= 0 or pre <= 0: continue
            gap = (o/pre-1)*100
            if gap >= 2:
                industry = ind_map.get(code,'其他')
                if gap >= 5: sector_cnt[industry] += 1
                fmv = mv.get(code,0)
                score = gap*8 + (8 if fmv>500 else 0) + (10 if sector_cnt.get(industry,0)>=3 else 0)
                results.append({"code":code,"gap_pct":round(gap,1),"score":round(score,0),
                               "industry":industry,"price":round(o,2),"float_mv":round(fmv,0),
                               "sector_count":sector_cnt.get(industry,0)})
        results.sort(key=lambda x:-x['score'])
        db.close()

        sectors = [{"name":k,"count":v} for k,v in sorted(sector_cnt.items(),key=lambda x:-x[1])[:8]]
        return {"date":target,"total":len(results),"picks":results[:20],"sectors":sectors}
    except Exception as e:
        return {"status":"error","message":str(e)}


@router.get("/intraday")
async def intraday_picks(date_param: str = Query(None, alias="date")):
    """盘中选股: 读取最新 intraday JSON 输出."""
    target = date_param or date.today().strftime("%Y-%m-%d")
    import glob
    pattern = os.path.join(OUTPUTS_DIR, "orchestrator_*", "report.md")
    files = sorted(glob.glob(pattern), reverse=True)
    # 简单返回最近报告摘要
    if files:
        with open(files[0]) as f:
            content = f.read()[:3000]
        return {"date": target, "report": content, "source": files[0]}
    return {"date": target, "picks": [], "message": "暂无盘中数据"}


@router.post("/run-pipeline")
async def trigger_pipeline():
    """Trigger daily pipeline (non-blocking fire-and-forget)."""
    script = os.path.join(TOOLS_DIR, "pipeline_daily.py")
    if not os.path.exists(script):
        return {"status": "error", "message": "pipeline_daily.py not found"}

    try:
        subprocess.Popen(
            ["python3", script, "--date", date.today().strftime("%Y-%m-%d")],
            cwd=KRONOS_ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return {"status": "started", "message": "流水线已触发, 请稍后刷新查看结果"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
