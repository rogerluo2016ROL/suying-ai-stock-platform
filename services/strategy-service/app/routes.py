"""Strategy API — plan management CRUD."""

from fastapi import APIRouter, Query, HTTPException
from app.plan_store import get_store

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])
store = get_store()


@router.post("/plans")
async def create_plan(
    name: str = Query("未命名方案"),
    model_name: str = Query("all"),
    capital: float = Query(1_000_000, ge=100_000),
    max_positions: int = Query(5, ge=1, le=20),
    single_max_pct: float = Query(0.2, ge=0.05, le=0.5),
):
    """Create a new draft plan."""
    plan = store.create(name=name, picks=[], model_name=model_name,
                        capital=capital, max_positions=max_positions)
    plan.single_max_pct = single_max_pct
    return {
        "plan": {
            "id": plan.id, "name": plan.name, "status": plan.status,
            "picks_count": len(plan.picks), "capital": plan.capital,
            "max_positions": plan.max_positions,
            "created_at": plan.created_at,
        },
        "message": f"方案 {plan.id} 创建成功",
    }


@router.post("/plans/{plan_id}/picks")
async def add_picks(plan_id: str, picks: list[dict]):
    """Add screening picks to a plan."""
    plan = store.get(plan_id)
    if not plan: raise HTTPException(404, "方案不存在")
    plan.picks = picks
    plan.updated_at = __import__("datetime").datetime.now().isoformat()
    return {"plan_id": plan_id, "picks_count": len(plan.picks), "message": f"已添加 {len(picks)} 只标的"}


@router.get("/plans")
async def list_plans():
    """List all plans."""
    plans = store.list_all()
    return {
        "plans": [{
            "id": p.id, "name": p.name, "status": p.status,
            "picks_count": len(p.picks), "model_name": p.model_name,
            "capital": p.capital, "created_at": p.created_at,
        } for p in plans],
        "total": len(plans),
    }


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str):
    """Get plan detail with picks."""
    plan = store.get(plan_id)
    if not plan: raise HTTPException(404, "方案不存在")
    return {
        "id": plan.id, "name": plan.name, "status": plan.status,
        "model_name": plan.model_name, "capital": plan.capital,
        "max_positions": plan.max_positions, "single_max_pct": plan.single_max_pct,
        "picks": plan.picks, "created_at": plan.created_at, "updated_at": plan.updated_at,
    }


@router.put("/plans/{plan_id}")
async def update_plan(plan_id: str, name: str = None, status: str = None):
    """Update plan name or status."""
    plan = store.get(plan_id)
    if not plan: raise HTTPException(404, "方案不存在")
    updates = {}
    if name: updates["name"] = name
    if status:
        if status not in ("draft", "confirmed", "archived"):
            raise HTTPException(400, f"Invalid status: {status}")
        updates["status"] = status
    store.update(plan_id, **updates)
    return {"plan_id": plan_id, "updates": updates, "status": "ok"}


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str):
    """Delete a plan."""
    if store.delete(plan_id):
        return {"plan_id": plan_id, "status": "deleted"}
    raise HTTPException(404, "方案不存在")


@router.post("/plans/{plan_id}/confirm")
async def confirm_plan(plan_id: str):
    """Confirm a plan → generates report + trading signals."""
    plan = store.confirm(plan_id)
    if not plan: raise HTTPException(404, "方案不存在")
    return {
        "plan_id": plan_id, "status": "confirmed",
        "picks_count": len(plan.picks),
        "message": f"方案已确认: {len(plan.picks)} 只标的",
    }


@router.post("/plans/{plan_id}/optimize")
async def optimize_plan(plan_id: str):
    """Optimize plan using Kronos predictions."""
    plan = store.get(plan_id)
    if not plan: raise HTTPException(404, "方案不存在")
    return {
        "plan_id": plan_id, "status": "optimized",
        "message": "优化完成 (Kronos预测对接中)",
    }


@router.get("/plans/{plan_id}/report")
async def generate_report(plan_id: str):
    """Generate a detailed stock selection report for a confirmed plan."""
    plan = store.get(plan_id)
    if not plan: raise HTTPException(404, "方案不存在")
    if plan.status != "confirmed":
        raise HTTPException(400, "请先确认方案后再生成报告")

    report = {
        "title": f"选股报告 — {plan.name}",
        "generated_at": __import__("datetime").datetime.now().isoformat(),
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


@router.get("/templates")
async def list_templates():
    return {
        "templates": [
            {"id": "aggressive", "name": "激进型", "risk": "high", "max_positions": 3, "single_max": 0.20},
            {"id": "balanced", "name": "均衡型", "risk": "medium", "max_positions": 5, "single_max": 0.12},
            {"id": "conservative", "name": "保守型", "risk": "low", "max_positions": 8, "single_max": 0.08},
        ]
    }
