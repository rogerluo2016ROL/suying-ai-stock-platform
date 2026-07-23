"""选股模式执行器与结果持久化（从 service.py 拆出，零行为变化）。

注意：`_run_cb_mode` 与 `_CB_AUCTION_T0*` 引擎覆盖全局变量仍留在 service.py ——
测试通过 monkeypatch 直接替换 service 模块属性，`_run_cb_mode` 必须在
service 模块全局命名空间内读取这些变量。
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Optional

from app import candidate_pool_store
from app.database import AsyncSession

# service 模块 facade：交易日解析与因子库连接保留在 service.py（monkeypatch 兼容），
# 运行时经模块属性访问，避免循环导入。
from app.domains.screening import service as _screening_service
from app.domains.screening.contract import (
    _normalize_picks,
    _sanitize_picks,
    _snapshot_rows,
)
from app.domains.screening.data_access import (
    _pg_connect,
    _pg_table_exists,
    _to_float,
)

logger = logging.getLogger("screener.routes")


# Shared thread pool for offloading synchronous screening engines.
# Each /run call is serialized behind a max_workers=3 pool to limit
# concurrent heavy computation (Kronos factor engine + PG queries).
_executor = ThreadPoolExecutor(max_workers=3)


def _auto_save_snapshot(result: dict, mode: str):
    """Auto-save screening results to JSON file and PG (fire-and-forget).

    Called after every successful screening run. Saves to:
      - outputs/snapshots/{mode}/{date}_{time_slot}.json
      - PG screening_snapshots table via recorder.record_picks()
    """
    import json, os
    from datetime import datetime

    picks = result.get("picks", [])
    snapshot_rows = _snapshot_rows(result)
    if not snapshot_rows:
        return

    trade_date = result.get("trade_date") or datetime.now().strftime("%Y-%m-%d")
    time_slot = result.get("time_slot") or datetime.now().strftime("%H:%M")

    # 1) JSON file snapshot
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        snap_dir = os.path.join(repo_root, "outputs", "snapshots", mode)
        os.makedirs(snap_dir, exist_ok=True)

        snap_path = os.path.join(snap_dir, f"{trade_date}_{time_slot.replace(':', '')}.json")
        with open(snap_path, "w") as f:
            json.dump({
                "mode": mode,
                "trade_date": trade_date,
                "time_slot": time_slot,
                "saved_at": datetime.now().isoformat(),
                "total_picks": len(picks),
                "factor_observations": len(snapshot_rows),
                "picks": picks,
            }, f, ensure_ascii=False, indent=2, default=str)
        logger.info("Snapshot saved: %s (%d picks)", snap_path, len(picks))
    except Exception as e:
        logger.warning("Snapshot file save failed: %s", e)

    # 2) PG screening_snapshots via recorder
    try:
        model_key = mode  # e.g. 'leader_afternoon', 'bi_trend_launch'
        from kronos_factors.recorder import record_picks
        n = record_picks(model_key, trade_date, time_slot, snapshot_rows)
        if n:
            logger.info("Recorder: %s %s — %d picks", model_key, trade_date, n)
    except Exception as e:
        logger.warning("Recorder save failed (PG may not be available): %s", e)


async def _candidate_pool_record_safe(
    db: AsyncSession | None,
    *,
    result: dict,
    mode: str,
    top_n: int,
    tenant_id: str | None,
    owner_user_id: str | None,
    account_id: str | None,
    data_scope: str | None,
) -> None:
    if db is None:
        return

    picks = result.get("picks") or []
    if not picks:
        return

    resolved_tenant = tenant_id or "tenant-default"
    resolved_scope = data_scope or ("account" if account_id or owner_user_id else "public")
    visibility = "public" if resolved_scope == "public" else "private"
    trade_date = result.get("trade_date") or datetime.now().strftime("%Y-%m-%d")
    time_slot = result.get("time_slot") or datetime.now().strftime("%H:%M")
    pool_id = f"POOL-{mode}-{trade_date}-{time_slot.replace(':', '')}-{account_id or owner_user_id or 'public'}"

    try:
        await candidate_pool_store.record(
            db,
            pool_id=pool_id,
            tenant_id=resolved_tenant,
            owner_user_id=owner_user_id,
            account_id=account_id,
            source_module="screener",
            source_mode=mode,
            name=f"{mode} 候选池",
            candidates=picks,
            metadata={
                "trade_date": trade_date,
                "time_slot": time_slot,
                "top_n": top_n,
                "elapsed": result.get("elapsed"),
            },
            visibility=visibility,
            data_scope=resolved_scope,
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning("CandidatePool save failed (PG may not be available): %s", e)


def _run_leader_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run Leader Scalp strategy (daily or intraday)."""
    from kronos_factors.engine import (
        run_leader_screening, run_intraday_screening,
        generate_execution_plan, generate_intraday_plan,
    )
    td = _screening_service._resolve_intraday_trade_date(trade_date) if mode in {"leader_intraday", "leader_closing"} else _screening_service._resolve_trade_date(trade_date)

    if mode == "leader_auction":
        from kronos_factors.engine.leader_auction import AuctionScalpEngine
        engine = AuctionScalpEngine()
        picks_data = engine.run(trade_date=td, top_n=top_n)
        engine.close()
        plans = generate_execution_plan(picks_data) if picks_data else []
    elif mode == "leader_intraday":
        result = run_intraday_screening(td or "latest", top_n=top_n)
        picks_data = result[0] if isinstance(result, tuple) else result
        plans = generate_intraday_plan(picks_data) if picks_data else []
    elif mode == "leader_closing":
        from kronos_factors.engine.leader_closing import run_intraday_screening as run_closing
        result = run_closing(td or "latest", time_slot="14:40", top_n=top_n)
        picks_data = result[0] if isinstance(result, tuple) else result
        plans = generate_intraday_plan(picks_data) if picks_data else []
    else:
        result = run_leader_screening(td or "latest", top_n=top_n)
        picks_data = result[0] if isinstance(result, tuple) else result
        plans = generate_execution_plan(picks_data) if picks_data else []

    picks_out = _sanitize_picks(picks_data) if picks_data else []
    picks_out = _normalize_picks(picks_out, mode)

    return {
        "mode": mode,
        "trade_date": td,
        "total_picks": len(picks_out),
        "picks": picks_out,
        "execution_plans": plans,
    }


def _load_supply_chain_expectation_gap_snapshot(top_n: int, trade_date: Optional[str]) -> Optional[dict]:
    model_key = "supply_chain_expectation_gap_v1"
    time_slot = "close"
    try:
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                if not _pg_table_exists(cur, "screening_snapshots"):
                    return None
                resolved_trade_date = trade_date
                if not resolved_trade_date:
                    cur.execute(
                        """
                        SELECT max(trade_date)
                        FROM screening_snapshots
                        WHERE model_key = %s AND time_slot = %s
                        """,
                        (model_key, time_slot),
                    )
                    row = cur.fetchone()
                    resolved_trade_date = str(row[0]) if row and row[0] else None
                if not resolved_trade_date:
                    return None
                cur.execute(
                    """
                    SELECT
                        ss.stock_code,
                        coalesce(s.name, split_part(ss.stock_code, '.', 1)) AS name,
                        ss.total_score,
                        ss.grade,
                        ss.rank_in_day,
                        ss.factors,
                        ss.trade_date
                    FROM screening_snapshots ss
                    LEFT JOIN stocks s ON s.code = split_part(ss.stock_code, '.', 1)
                    WHERE ss.model_key = %s
                      AND ss.time_slot = %s
                      AND ss.trade_date = %s
                    ORDER BY ss.rank_in_day ASC
                    LIMIT %s
                    """,
                    (model_key, time_slot, resolved_trade_date, top_n),
                )
                rows = cur.fetchall()
        if not rows:
            return None
        picks = []
        for stock_code, name, total_score, grade, rank, factors, row_trade_date in rows:
            if isinstance(factors, str):
                factors = json.loads(factors)
            if not isinstance(factors, dict):
                factors = {}
            pick = {
                "rank": int(rank or len(picks) + 1),
                "code": str(stock_code),
                "name": str(name),
                "score": _to_float(total_score, 0.0),
                "total_score": _to_float(total_score, 0.0),
                "grade": str(grade or ""),
                "signal": factors.get("signal_tier"),
                "industry": factors.get("chain_id") or "产业链预期差",
                "chain_id": factors.get("chain_id"),
                "tag_name": factors.get("tag_name"),
                "source_mode": "supply_chain",
                "trade_date": str(row_trade_date),
            }
            for key in (
                "expectation_gap_score",
                "reliability_adjusted_gap_score",
                "evidence_quality_score",
                "label_fit_score",
                "reassessment_status",
                "gap_momentum_score",
                "three_high_total",
                "growth_score",
                "profit_score",
                "moat_score",
            ):
                if key in factors:
                    pick[key] = factors.get(key)
            picks.append(pick)
        return {
            "mode": "supply_chain",
            "model_key": model_key,
            "trade_date": str(rows[0][6]),
            "total_picks": len(picks),
            "picks": picks,
            "source": "screening_snapshots",
            "score_contract": "reassessment_adjusted",
        }
    except Exception as exc:
        logger.warning("Load supply-chain expectation-gap snapshot failed: %s", exc)
        return None


def _run_supply_chain_trend_launch_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 产业链趋势启动选股 vFinal."""
    from kronos_factors.engine.supply_chain_trend import TrendLaunchEngine

    resolved_trade_date = _screening_service._resolve_trade_date(trade_date)
    engine = TrendLaunchEngine()
    result = engine.run(top_n=top_n, trade_date=resolved_trade_date)

    picks = result.picks
    picks = _sanitize_picks(picks)
    for p in picks:
        sc = p.get("total_score", 0)
        if sc >= 75: p["grade"] = "S"
        elif sc >= 60: p["grade"] = "A"
        elif sc >= 45: p["grade"] = "B"
        else: p["grade"] = "C"

    return {
        "mode": mode,
        "trade_date": resolved_trade_date,
        "total_picks": len(picks),
        "picks": picks,
        "metadata": result.metadata,
    }


def _run_multifactor_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run multi-factor mode (short/chokepoint)."""
    from kronos_factors.engine.modes import (
        ShortModeEngine, ChokepointEngine,
    )

    engine_map = {
        "short": ShortModeEngine,
        "chokepoint": ChokepointEngine,
    }
    engine = engine_map[mode]()
    result = engine.run(top_n=top_n)

    picks = _sanitize_picks(result.picks)
    picks = _normalize_picks(picks, mode)

    return {
        "mode": result.mode,
        "market_env": result.market_env,
        "total_scored": result.total_scored,
        "total_excluded": result.total_excluded,
        "picks": picks,
        "factor_weights": engine.get_factor_weights(),
    }


def _run_bi_trend_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 毕师傅趋势启动战法 V13 (OBV+WR trend launch screening + 黑天鹅防护 + 止损降权分散 + 智能卖出决策树)."""
    from kronos_factors.engine.bi_trend_launch import BiTrendLaunchEngine, generate_bi_plan

    resolved_trade_date = _screening_service._resolve_trade_date(trade_date)
    engine = BiTrendLaunchEngine()
    picks, factor_observations, market_info = engine.run_with_scores(
        top_n=top_n, trade_date=resolved_trade_date
    )

    picks = _sanitize_picks(picks)
    factor_observations = _sanitize_picks(factor_observations)
    picks = _normalize_picks(picks, mode)

    # Generate execution plans with market regime awareness
    regime = "neutral"
    plans = generate_bi_plan(picks, market_regime=regime) if picks else []

    return {
        "mode": mode,
        "trade_date": resolved_trade_date,
        "total_picks": len(picks),
        "picks": picks,
        "factor_observations": factor_observations,
        "market_info": market_info,
        "execution_plans": plans,
    }


def _run_bi_full_market_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 毕师傅全市场趋势启动战法 V1.0 (全市场 + VR过滤)."""
    from kronos_factors.engine.bi_trend_full_market import BiTrendFullMarketEngine, generate_bi_plan

    engine = BiTrendFullMarketEngine()
    picks = engine.run(top_n=top_n, trade_date=trade_date, hard_tech_only=False)

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    regime = "neutral"
    plans = generate_bi_plan(picks, market_regime=regime) if picks else []

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
        "execution_plans": plans,
    }


def _run_bi_shifu_trend_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 毕师傅趋势战法正式版或候选 V2.3。"""
    from kronos_factors.engine.bi_shifu_trend import BiShifuTrendEngine, BiShifuTrendV23Engine

    resolved_trade_date = _screening_service._resolve_trade_date(trade_date)
    engine = BiShifuTrendV23Engine() if mode == "bi_shifu_trend_v23" else BiShifuTrendEngine()
    if hasattr(engine, "run_with_metadata"):
        picks, data_quality = engine.run_with_metadata(top_n=top_n, trade_date=resolved_trade_date)
    else:
        picks = engine.run(top_n=top_n, trade_date=resolved_trade_date)
        data_quality = {}

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    return {
        "mode": mode,
        "trade_date": resolved_trade_date,
        "total_picks": len(picks),
        "picks": picks,
        "data_quality": data_quality,
    }


def _run_afternoon_mode(
    mode: str,
    top_n: int,
    trade_date: Optional[str],
    time_slot: str = "14:30",
) -> dict:
    """Run 秋神龙头战法-午后选股 V1.0 at the requested time slot."""
    from kronos_factors.engine.leader_afternoon import (
        AfternoonLeaderEngine,
        AfternoonTrendFullEngine,
        build_sector_resonance_summary,
        resolve_afternoon_trade_date,
    )

    is_full = mode == "leader_afternoon_trend_full"
    engine = AfternoonTrendFullEngine() if is_full else AfternoonLeaderEngine()
    run_top_n = max(top_n, 30) if is_full else top_n
    if trade_date is None:
        with _screening_service._get_factor_db() as db:
            trade_date = resolve_afternoon_trade_date(db)
    picks = engine.run(top_n=run_top_n, trade_date=trade_date, time_slot=time_slot)

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)
    sector_resonance = build_sector_resonance_summary(picks) if is_full else []

    result = {
        "mode": mode,
        "trade_date": trade_date,
        "time_slot": time_slot,
        "total_picks": len(picks),
        "picks": picks,
    }
    if is_full:
        result["sector_resonance"] = sector_resonance
    return result
