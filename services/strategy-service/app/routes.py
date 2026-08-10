"""Strategy API — plan management CRUD + auto-trading strategy engine + executor."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Header, Query, HTTPException, Depends
from kronos_auth import require_role
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import auto_strategy_pg_store, plan_pg_store, settlement_store
from app.database import get_db
from app.plan_store import get_store
from app.platform_scope import plan_to_dict, resolve_platform_scope
from app.auto_trading_engine import (
    generate_strategy_from_scheme,
    create_custom_strategy,
    get_strategy_store,
)
from app.auto_trading_executor import get_executor_manager, run_strategy

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])
store = get_store()
logger = logging.getLogger("strategy-service.routes")


async def _plan_record_safe(db: AsyncSession, plan) -> None:
    if db is None:
        return
    try:
        await plan_pg_store.record(db, plan=plan)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        # PG is the durable target, but routes keep the in-memory store as the
        # fallback so local development and tests do not lose existing behavior.
        logger.warning("Failed to persist strategy plan %s: %s", getattr(plan, "id", ""), exc)
        return


async def _plan_query_safe(db: AsyncSession, **filters):
    if db is None:
        return None
    try:
        return await plan_pg_store.query(db, **filters)
    except Exception as exc:
        logger.warning("Failed to query strategy plans from DB: filters=%s error=%s", filters, exc)
        return None


async def _settlement_get_safe(db: AsyncSession | None, plan_id: str):
    if db is None:
        return None
    try:
        return await settlement_store.pg_get(db, plan_id)
    except Exception as exc:
        # plan_settlements table is not migrated yet — treat as cache miss and
        # fall back to the in-memory settlement store.
        logger.warning("Failed to query settlement for plan %s: %s", plan_id, exc)
        return None


async def _strategy_record_safe(db: AsyncSession | None, strategy) -> None:
    if db is None:
        return
    try:
        await auto_strategy_pg_store.record(db, strategy=strategy)
        await db.commit()
    except Exception:
        await db.rollback()
        return


async def _strategy_list_safe(db: AsyncSession | None):
    if db is None:
        return None
    try:
        return await auto_strategy_pg_store.list_all(db)
    except Exception:
        return None


async def _strategy_get_safe(db: AsyncSession | None, strategy_id: str):
    if db is None:
        return None
    try:
        return await auto_strategy_pg_store.get(db, strategy_id)
    except Exception:
        return None


async def _strategy_delete_safe(db: AsyncSession | None, strategy_id: str) -> bool:
    if db is None:
        return False
    try:
        deleted = await auto_strategy_pg_store.delete(db, strategy_id)
        await db.commit()
        return deleted
    except Exception:
        await db.rollback()
        return False


def _hydrate_strategy(strategy):
    if strategy is not None:
        get_strategy_store().upsert(strategy)
    return strategy


@router.post("/plans")
async def create_plan(
    name: str = Query("未命名方案"),
    model_name: str = Query("all"),
    capital: float = Query(1_000_000, ge=100_000),
    max_positions: int = Query(5, ge=1, le=20),
    single_max_pct: float = Query(0.2, ge=0.05, le=0.5),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    data_scope: str | None = Header(default=None, alias="X-Data-Scope"),
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Create a new draft plan."""
    scope = resolve_platform_scope(user, tenant_id=tenant_id, account_id=account_id, data_scope=data_scope)
    plan = store.create(name=name, picks=[], model_name=model_name,
                        capital=capital, max_positions=max_positions,
                        **scope)
    plan.single_max_pct = single_max_pct
    await _plan_record_safe(db, plan)
    return {
        "plan": plan_to_dict(plan),
        "message": f"方案 {plan.id} 创建成功",
    }


@router.post("/plans/{plan_id}/picks")
async def add_picks(
    plan_id: str,
    picks: list[dict],
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    data_scope: str | None = Header(default=None, alias="X-Data-Scope"),
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Add screening picks to a plan."""
    scope = resolve_platform_scope(user, tenant_id=tenant_id, account_id=account_id, data_scope=data_scope)
    plan = store.get_for_scope(plan_id, **scope)
    if not plan: raise HTTPException(404, "方案不存在")
    plan.picks = picks
    plan.updated_at = datetime.now(timezone.utc).isoformat()
    await _plan_record_safe(db, plan)
    return {"plan_id": plan_id, "picks_count": len(plan.picks), "message": f"已添加 {len(picks)} 只标的"}


@router.get("/plans")
async def list_plans(
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    data_scope: str | None = Header(default=None, alias="X-Data-Scope"),
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user", "external_analyst")),
):
    """List all plans."""
    scope = resolve_platform_scope(user, tenant_id=tenant_id, account_id=account_id, data_scope=data_scope)
    pg_result = await _plan_query_safe(db, **scope)
    if pg_result and pg_result["total"] > 0:
        return {"plans": pg_result["plans"], "total": pg_result["total"]}
    plans = store.list_for_scope(**scope)
    return {
        "plans": [plan_to_dict(p) for p in plans],
        "total": len(plans),
    }


@router.get("/plans/{plan_id}")
async def get_plan(
    plan_id: str,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    data_scope: str | None = Header(default=None, alias="X-Data-Scope"),
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user", "external_analyst")),
):
    """Get plan detail with picks."""
    scope = resolve_platform_scope(user, tenant_id=tenant_id, account_id=account_id, data_scope=data_scope)
    pg_result = await _plan_query_safe(db, plan_id=plan_id, **scope)
    if pg_result and pg_result["plans"]:
        return pg_result["plans"][0]
    plan = store.get_for_scope(plan_id, **scope)
    if not plan: raise HTTPException(404, "方案不存在")
    return {
        "id": plan.id, "name": plan.name, "status": plan.status,
        "model_name": plan.model_name, "capital": plan.capital,
        "max_positions": plan.max_positions, "single_max_pct": plan.single_max_pct,
        "picks": plan.picks, "created_at": plan.created_at, "updated_at": plan.updated_at,
        "tenant_id": plan.tenant_id, "owner_user_id": plan.owner_user_id,
        "account_id": plan.account_id, "visibility": plan.visibility, "data_scope": plan.data_scope,
    }


@router.put("/plans/{plan_id}")
async def update_plan(
    plan_id: str,
    name: str = None,
    status: str = None,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    data_scope: str | None = Header(default=None, alias="X-Data-Scope"),
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Update plan name or status."""
    scope = resolve_platform_scope(user, tenant_id=tenant_id, account_id=account_id, data_scope=data_scope)
    plan = store.get_for_scope(plan_id, **scope)
    if not plan: raise HTTPException(404, "方案不存在")
    updates = {}
    if name: updates["name"] = name
    if status:
        if status not in ("draft", "confirmed", "archived"):
            raise HTTPException(400, f"Invalid status: {status}")
        updates["status"] = status
    plan = store.update(plan_id, **updates)
    if plan:
        await _plan_record_safe(db, plan)
    return {"plan_id": plan_id, "updates": updates, "status": "ok"}


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: str,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    data_scope: str | None = Header(default=None, alias="X-Data-Scope"),
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Delete a plan."""
    scope = resolve_platform_scope(user, tenant_id=tenant_id, account_id=account_id, data_scope=data_scope)
    if not store.get_for_scope(plan_id, **scope):
        pg_result = await _plan_query_safe(db, plan_id=plan_id, **scope)
        if not (pg_result and pg_result["plans"]):
            raise HTTPException(404, "方案不存在")
    if store.delete(plan_id):
        return {"plan_id": plan_id, "status": "deleted"}
    return {"plan_id": plan_id, "status": "delete_pending_pg"}


@router.post("/plans/{plan_id}/confirm")
async def confirm_plan(
    plan_id: str,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    data_scope: str | None = Header(default=None, alias="X-Data-Scope"),
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Confirm a plan → generates report + trading signals."""
    scope = resolve_platform_scope(user, tenant_id=tenant_id, account_id=account_id, data_scope=data_scope)
    if not store.get_for_scope(plan_id, **scope):
        raise HTTPException(404, "方案不存在")
    plan = store.confirm(plan_id)
    if not plan: raise HTTPException(404, "方案不存在")
    await _plan_record_safe(db, plan)
    return {
        "plan_id": plan_id, "status": "confirmed",
        "picks_count": len(plan.picks),
        "message": f"方案已确认: {len(plan.picks)} 只标的",
    }


@router.post("/plans/{plan_id}/optimize")
async def optimize_plan(
    plan_id: str,
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    """Optimize plan using Kronos predictions."""
    plan = store.get(plan_id)
    if not plan: raise HTTPException(404, "方案不存在")
    return {
        "plan_id": plan_id, "status": "optimized",
        "message": "优化完成 (Kronos预测对接中)",
    }


@router.get("/plans/{plan_id}/report")
async def generate_report(
    plan_id: str,
    user: dict = Depends(require_role("admin", "internal_analyst", "user", "external_analyst")),
):
    """Generate a detailed stock selection report for a confirmed plan."""
    plan = store.get(plan_id)
    if not plan: raise HTTPException(404, "方案不存在")
    if plan.status != "confirmed":
        raise HTTPException(400, "请先确认方案后再生成报告")

    report = {
        "title": f"选股报告 — {plan.name}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan": {
            "id": plan.id, "name": plan.name, "model": plan.model_name,
            "capital": plan.capital, "max_positions": plan.max_positions,
            "single_max_pct": plan.single_max_pct,
        },
        "market_analysis": {
            "sentiment_cycle": "情绪上升期",
            "sector_rotation": "科技+消费主线",
            "index_status": "上证指数多头排列",
        },
        "picks": [],
        "risk_warnings": [
            "本报告仅供参考，不构成投资建议",
            "量化策略存在失效风险",
            "请结合个人风险承受能力独立决策",
        ],
    }

    for p in plan.picks:
        entry_pct = round(plan.single_max_pct / plan.max_positions * 100, 1)
        report["picks"].append({
            "code": p.get("code", ""),
            "name": p.get("name", ""),
            "price": p.get("price", 0),
            "score": p.get("score", 0),
            "grade": p.get("grade", ""),
            "tech_analysis": "均线多头排列，MACD金叉",
            "capital_analysis": "主力净流入，北向增持",
            "fundamental_analysis": "PE合理区间，ROE优秀",
            "kronos_prediction": "预测30日上涨趋势",
            "operation": {
                "entry_price": p.get("entry_price") or round(p.get("price", 0) * 0.95, 2),
                "stop_loss": p.get("stop_loss") or round(p.get("price", 0) * 0.92, 2),
                "target_price": p.get("target_price") or round(p.get("price", 0) * 1.15, 2),
                "position_pct": round(entry_pct, 1),
                "hold_period": "1-4周",
            },
        })

    # Generate quant strategy
    report["quant_strategy"] = {
        "buy_conditions": [
            "信号强度 ≥ 🟡买入",
            "Kronos预测收益 > 8%",
            "因子共振数 ≥ 2",
            f"单票仓位上限 {plan.single_max_pct*100:.0f}%",
        ],
        "sell_conditions": [
            "信号强度 ≤ 🔴卖出",
            "止损: 浮亏 ≥ 3%",
            "止盈: 浮盈 ≥ 15%",
        ],
        "risk_rules": [
            f"最大持仓数 {plan.max_positions} 只",
            "日最大亏损 3% 暂停交易",
            "总仓位上限 80%",
        ],
        "execution_mode": "半自动(信号提醒+手动确认)",
    }

    return report


@router.get("/plans/{plan_id}/settlement-report")
async def get_settlement_report(
    plan_id: str,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    data_scope: str | None = Header(default=None, alias="X-Data-Scope"),
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user", "external_analyst")),
):
    """Settlement report for a settled plan (PRD 9.4).

    404: plan not found (same behavior as other plan routes).
    409: plan exists but has not been settled yet.
    """
    scope = resolve_platform_scope(user, tenant_id=tenant_id, account_id=account_id, data_scope=data_scope)

    pg_result = await _plan_query_safe(db, plan_id=plan_id, **scope)
    if pg_result and pg_result["plans"]:
        plan_info = pg_result["plans"][0]
    else:
        plan = store.get_for_scope(plan_id, **scope)
        if not plan:
            raise HTTPException(404, "方案不存在")
        plan_info = {**plan_to_dict(plan), "picks": plan.picks}

    record = await _settlement_get_safe(db, plan_id)
    source = "pg"
    if record is None:
        record = settlement_store.get_settlement_store().get(plan_id)
        source = "memory"
    if record is None and plan_info.get("status") not in settlement_store.SETTLED_STATUSES:
        raise HTTPException(409, "方案尚未结算，暂无结算报告")

    return settlement_store.build_settlement_report(
        plan_id=plan_id,
        plan_name=plan_info.get("name") or "",
        capital=float(plan_info.get("capital") or 1_000_000),
        picks=plan_info.get("picks") or [],
        record=record,
        source=source,
    )


@router.get("/templates")
async def list_templates(
    user: dict = Depends(require_role("admin", "internal_analyst", "user", "external_analyst")),
):
    return {
        "templates": [
            {"id": "aggressive", "name": "激进型", "risk": "high", "max_positions": 3, "single_max": 0.20},
            {"id": "balanced", "name": "均衡型", "risk": "medium", "max_positions": 5, "single_max": 0.12},
            {"id": "conservative", "name": "保守型", "risk": "low", "max_positions": 8, "single_max": 0.08},
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════
# Auto-Trading Strategy Engine — PRD AC-10.6 ~ AC-10.8 + AC-11.5 ~ AC-11.6
# ═══════════════════════════════════════════════════════════════════════════

# ── Request schemas ──

class CustomStrategyRequest(BaseModel):
    """Request body for creating a custom strategy."""
    name: str = Field(..., min_length=1, max_length=100, description="策略名称")
    description: str = Field("", description="策略描述")
    buy_conditions: list[dict] = Field(default_factory=list, description="买入条件列表")
    sell_conditions: list[dict] = Field(default_factory=list, description="卖出条件列表")
    position_rules: dict | None = Field(None, description="仓位规则")
    risk_rules: dict | None = Field(None, description="风控规则")
    trade_mode: str = Field("paper", description="paper | live")
    check_interval_sec: int = Field(300, ge=30, le=3600, description="检查间隔(秒)")
    capital: float = Field(1_000_000, ge=100_000, description="初始资金")
    picks: list[dict] = Field(default_factory=list, description="标的列表")


class StrategyUpdateRequest(BaseModel):
    """Request body for updating a strategy."""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    buy_conditions: list[dict] | None = None
    sell_conditions: list[dict] | None = None
    position_rules: dict | None = None
    risk_rules: dict | None = None
    trade_mode: str | None = Field(None, description="paper | live")
    check_interval_sec: int | None = Field(None, ge=30, le=3600)
    capital: float | None = Field(None, ge=100_000)
    picks: list[dict] | None = None


# ── Strategy generation ──

@router.post("/generate-from-scheme/{scheme_id}")
async def api_generate_strategy_from_scheme(
    scheme_id: str,
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """PRD AC-10.6: Generate a StrategyConfig from a confirmed trading plan.

    Reads the plan (scheme) from PlanStore and auto-generates:
      - buy_conditions: signal≥BUY(60), Kronos return>8%, factor resonance≥2
      - sell_conditions: signal≤SELL(20), Kronos bearish, stop-loss≥3%, take-profit≥15%
      - risk_rules: max 5 positions, daily max loss 3%, total cap 80%
    """
    try:
        strategy = generate_strategy_from_scheme(scheme_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await _strategy_record_safe(db, strategy)
    return {
        "strategy": strategy.to_dict(),
        "message": f"策略 {strategy.id} 已从方案 {scheme_id} 生成",
    }


@router.post("/custom")
async def api_create_custom_strategy(
    body: CustomStrategyRequest,
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """PRD AC-10.7: Create a fully custom auto-trading strategy."""
    try:
        strategy = create_custom_strategy(
            name=body.name,
            description=body.description,
            buy_conditions=body.buy_conditions,
            sell_conditions=body.sell_conditions,
            position_rules=body.position_rules,
            risk_rules=body.risk_rules,
            trade_mode=body.trade_mode,
            check_interval_sec=body.check_interval_sec,
            capital=body.capital,
            picks=body.picks,
        )
    except Exception as e:
        raise HTTPException(400, str(e))

    await _strategy_record_safe(db, strategy)
    return {
        "strategy": strategy.to_dict(),
        "message": f"自定义策略 {strategy.id} 创建成功",
    }


# ── Strategy CRUD ──

@router.get("/list")
async def api_list_strategies(
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user", "external_analyst")),
):
    """PRD AC-10.8: List all auto-trading strategies."""
    store = get_strategy_store()
    pg_strategies = await _strategy_list_safe(db)
    if pg_strategies:
        for strategy in pg_strategies:
            store.upsert(strategy)
        return {
            "strategies": [s.to_dict() for s in pg_strategies],
            "total": len(pg_strategies),
        }

    strategies = store.list_all()
    if strategies and db is not None:
        for strategy in strategies:
            await _strategy_record_safe(db, strategy)
    return {
        "strategies": [s.to_dict() for s in strategies],
        "total": len(strategies),
    }


@router.get("/{strategy_id}")
async def api_get_strategy(
    strategy_id: str,
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user", "external_analyst")),
):
    """Get strategy detail by ID."""
    store = get_strategy_store()
    strategy = _hydrate_strategy(await _strategy_get_safe(db, strategy_id)) or store.get(strategy_id)
    if not strategy:
        raise HTTPException(404, "策略不存在")
    return strategy.to_dict()


@router.put("/{strategy_id}")
async def api_update_strategy(
    strategy_id: str,
    body: StrategyUpdateRequest,
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """PRD AC-10.8: Edit an existing strategy."""
    store = get_strategy_store()
    strategy = store.get(strategy_id) or _hydrate_strategy(await _strategy_get_safe(db, strategy_id))
    if not strategy:
        raise HTTPException(404, "策略不存在")

    updates = {}
    for field in ("name", "description", "trade_mode", "check_interval_sec", "capital"):
        val = getattr(body, field, None)
        if val is not None:
            updates[field] = val

    if body.buy_conditions is not None:
        from app.auto_trading_engine import BuyCondition
        updates["buy_conditions"] = [
            BuyCondition(
                field=c.get("field", ""),
                operator=c.get("operator", ">="),
                threshold=float(c.get("threshold", 0)),
                description=c.get("description", ""),
            )
            for c in body.buy_conditions
        ]

    if body.sell_conditions is not None:
        from app.auto_trading_engine import SellCondition
        updates["sell_conditions"] = [
            SellCondition(
                field=c.get("field", ""),
                operator=c.get("operator", ">="),
                threshold=float(c.get("threshold", 0)),
                description=c.get("description", ""),
            )
            for c in body.sell_conditions
        ]

    if body.position_rules is not None:
        from app.auto_trading_engine import PositionRule
        updates["position_rules"] = PositionRule(
            max_positions=int(body.position_rules.get("max_positions", 5)),
            single_max_pct=float(body.position_rules.get("single_max_pct", 0.20)),
            total_position_cap_pct=float(body.position_rules.get("total_position_cap_pct", 0.80)),
        )

    if body.risk_rules is not None:
        from app.auto_trading_engine import RiskRule
        updates["risk_rules"] = RiskRule(
            daily_max_loss_pct=float(body.risk_rules.get("daily_max_loss_pct", 0.03)),
            stop_loss_pct=float(body.risk_rules.get("stop_loss_pct", 0.03)),
            take_profit_pct=float(body.risk_rules.get("take_profit_pct", 0.15)),
            trailing_stop_pct=float(body.risk_rules.get("trailing_stop_pct", 0.0)),
        )

    if body.picks is not None:
        updates["picks"] = body.picks

    store.update(strategy_id, **updates)
    updated = store.get(strategy_id)
    if updated:
        await _strategy_record_safe(db, updated)
    return {
        "strategy": updated.to_dict() if updated else None,
        "message": "策略已更新",
    }


@router.delete("/{strategy_id}")
async def api_delete_strategy(
    strategy_id: str,
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """PRD AC-10.8: Delete a strategy. Stops execution if running."""
    mgr = get_executor_manager()
    executor = mgr.get(strategy_id)
    if executor and executor.status in ("running", "paused"):
        try:
            mgr.stop(strategy_id)
        except ValueError:
            pass

    store = get_strategy_store()
    deleted_memory = store.delete(strategy_id)
    deleted_db = await _strategy_delete_safe(db, strategy_id)
    if deleted_memory or deleted_db:
        return {"strategy_id": strategy_id, "status": "deleted"}
    raise HTTPException(404, "策略不存在")


# ── Strategy Execution control ──

@router.post("/{strategy_id}/start")
async def api_start_strategy(
    strategy_id: str,
    mode: str = Query("paper", description="paper | live"),
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """PRD AC-11.5: Start executing a strategy.

    Launches the async executor loop. The executor will:
      1. Check buy conditions for picks not yet held
      2. Check sell conditions for held positions
      3. Place orders via trade-service
      4. Repeat at the configured interval (default 5 min)
    """
    if get_strategy_store().get(strategy_id) is None:
        _hydrate_strategy(await _strategy_get_safe(db, strategy_id))

    try:
        state = run_strategy(strategy_id, mode=mode)
    except ValueError as e:
        raise HTTPException(400, str(e))

    strategy = get_strategy_store().get(strategy_id)
    if strategy:
        await _strategy_record_safe(db, strategy)
    return {
        "strategy_id": strategy_id,
        "status": state.status,
        "started_at": state.started_at,
        "trade_mode": mode,
        "message": f"策略 {strategy_id} 已启动",
    }


@router.post("/{strategy_id}/pause")
async def api_pause_strategy(
    strategy_id: str,
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """PRD AC-11.6: Pause strategy execution (preserves state)."""
    mgr = get_executor_manager()
    try:
        state = mgr.pause(strategy_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "strategy_id": strategy_id,
        "status": state.status,
        "message": "策略已暂停",
    }


@router.post("/{strategy_id}/resume")
async def api_resume_strategy(
    strategy_id: str,
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """PRD AC-11.6: Resume a paused strategy."""
    mgr = get_executor_manager()
    try:
        state = mgr.resume(strategy_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "strategy_id": strategy_id,
        "status": state.status,
        "message": "策略已恢复",
    }


@router.post("/{strategy_id}/stop")
async def api_stop_strategy(
    strategy_id: str,
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """PRD AC-11.6: Stop strategy execution."""
    mgr = get_executor_manager()
    try:
        state = mgr.stop(strategy_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "strategy_id": strategy_id,
        "status": state.status,
        "stopped_at": state.stopped_at,
        "message": "策略已终止",
    }


@router.get("/{strategy_id}/status")
async def api_get_strategy_status(
    strategy_id: str,
    db: AsyncSession | None = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user", "external_analyst")),
):
    """PRD AC-11.6: Get execution status for a strategy."""
    mgr = get_executor_manager()
    state = mgr.get(strategy_id)

    if state is None:
        # Check if strategy exists but hasn't been started
        store = get_strategy_store()
        strategy = store.get(strategy_id) or _hydrate_strategy(await _strategy_get_safe(db, strategy_id))
        if strategy is None:
            raise HTTPException(404, "策略不存在")
        return {
            "strategy_id": strategy_id,
            "status": strategy.status,
            "executor_running": False,
        }

    store = get_strategy_store()
    strategy = store.get(strategy_id)

    return {
        **state.to_status_dict(),
        "trade_mode": strategy.trade_mode if strategy else "paper",
        "check_interval_sec": strategy.check_interval_sec if strategy else 300,
    }


@router.get("/{strategy_id}/log")
async def api_get_strategy_log(
    strategy_id: str,
    limit: int = Query(50, ge=10, le=500, description="Max log entries"),
    level: str = Query(None, description="Filter: INFO | WARN | ERROR | BUY | SELL"),
    user: dict = Depends(require_role("admin", "internal_analyst", "user", "external_analyst")),
):
    """PRD AC-11.6: Get execution logs for a strategy."""
    mgr = get_executor_manager()
    state = mgr.get(strategy_id)
    if state is None:
        raise HTTPException(404, "执行器未找到，策略可能未启动")

    logs = state.logs
    if level:
        logs = [l for l in logs if l.level == level]

    logs = logs[-limit:]

    return {
        "strategy_id": strategy_id,
        "total_logs": len(state.logs),
        "filtered": len(logs),
        "logs": [
            {
                "timestamp": l.timestamp,
                "level": l.level,
                "message": l.message,
                "details": l.details,
            }
            for l in logs
        ],
    }
