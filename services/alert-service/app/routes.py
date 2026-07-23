"""Alert API routes — real notification system."""

from fastapi import APIRouter, Query
from app.alert_store import get_store
from app import feishu_notifier

router = APIRouter(prefix="/api/v1/alert", tags=["alert"])
store = get_store()


@router.get("/alerts")
async def list_alerts(limit: int = Query(50, ge=10, le=200)):
    """Get recent alerts."""
    alerts = store.list_all(limit)
    return {
        "alerts": [{
            "id": a.id, "level": a.level, "title": a.title,
            "message": a.message, "code": a.code,
            "read": a.read, "created_at": a.created_at,
        } for a in alerts],
        "unread": store.unread_count(),
        "total": len(alerts),
    }


@router.get("/unread-count")
async def unread_count():
    return {"unread": store.unread_count()}


@router.post("/alerts/{alert_id}/read")
async def mark_read(alert_id: str):
    store.mark_read(alert_id)
    return {"status": "ok"}


@router.post("/alerts/read-all")
async def mark_all_read():
    store.mark_all_read()
    return {"status": "ok"}


@router.post("/trigger")
async def trigger_alert(
    level: str = Query("info", description="urgent/important/info"),
    title: str = Query(..., description="Alert title"),
    message: str = Query(..., description="Alert message"),
    code: str = Query("", description="Stock code"),
    channel: str = Query("app", description="app/wecom/dingtalk/feishu/email，逗号分隔多渠道"),
    score: float = Query(None, description="评分（可选，飞书卡片展示）"),
):
    """Manually trigger an alert (for testing/hooks). 支持飞书推送。"""
    alert = store.create(level=level, title=title, message=message, code=code, channel=channel)
    if not alert:
        return {"status": "cooled_down", "message": "Similar alert within 5 min, skipped"}
    # 多渠道推送：channel 逗号分隔，含 feishu 则发飞书交互卡片
    channels = [c.strip() for c in channel.split(",") if c.strip()]
    feishu_result = None
    if "feishu" in channels:
        ok, msg = feishu_notifier.notify(level=level, title=title, message=message, code=code, score=score)
        feishu_result = {"success": ok, "msg": msg, "enabled": feishu_notifier.is_enabled()}
    return {
        "alert": {"id": alert.id, "level": alert.level, "title": alert.title},
        "status": "created",
        "feishu": feishu_result,
    }


@router.post("/crowding-scan")
async def crowding_scan(
    trade_date: str = Query(None, description="YYYY-MM-DD, 默认 daily_kline 最近交易日"),
    level: str = Query("high", description="过滤阈值: high 只推 high; medium 推 medium+high"),
    board: str = Query("688", description="688 科创板 | all 全市场"),
    channel: str = Query("app,feishu", description="推送渠道, 逗号分隔"),
    top_n: int = Query(30, description="最多推送条数 (防刷屏)"),
):
    """扫描高拥挤标的并推送 alert (科创板⭐标注). 盘后批量调用.

    复用 kronos_factors.scorer.crowding_drawdown.scan_crowding 做批量计算,
    命中后逐个 store.create + feishu_notifier.notify.
    """
    import os
    from kronos_factors.scorer._db_stub import _get_db, set_db_adapter
    from kronos_factors.scorer.crowding_drawdown import scan_crowding

    # alert-service 默认不注入 kronos adapter; 走 KRONOS_PG_URL 自动建连
    pg_url = os.environ.get("KRONOS_PG_URL", "")
    if pg_url:
        try:
            from kronos_factors.pg_adapter import create_pg_adapter
            _a = create_pg_adapter(pg_url)
            if _a:
                set_db_adapter(_a)
        except Exception:
            pass

    with _get_db() as db:
        if not trade_date:
            r = db.execute("SELECT MAX(trade_date) m FROM daily_kline").fetchone()
            trade_date = r["m"] if r else None
        if not trade_date:
            return {"status": "error", "message": "无法确定 trade_date (KRONOS_PG_URL 未配或无数据)"}
        warnings = scan_crowding(db, trade_date, board=board, min_level=level)

    lvl_cn = {"high": "高", "medium": "中"}
    pushed = 0
    for w in warnings[:top_n]:
        star = "⭐" if w["is_kechuang"] else ""
        title = f"拥挤度{lvl_cn.get(w['level'], '')}预警 {star}{w['code']}"
        msg = f"CI={w['ci_score']} 板块={'科创板' if w['is_kechuang'] else '其他'} 成分={w['factor_pctl']}"
        alert = store.create(level="important", title=title, message=msg, code=w["code"], channel=channel)
        if alert and "feishu" in channel.split(","):
            feishu_notifier.notify(level="important", title=title, message=msg,
                                   code=w["code"], score=w["ci_score"])
            pushed += 1
    return {
        "trade_date": trade_date, "board": board, "scanned_level": level,
        "n_warnings": len(warnings), "n_pushed_feishu": pushed,
        "top5": [{"code": w["code"], "level": w["level"], "ci_score": w["ci_score"],
                  "is_kechuang": w["is_kechuang"]} for w in warnings[:5]],
    }


@router.get("/channels")
async def list_channels():
    return {"channels": [
        {"id": "app", "name": "平台弹窗", "enabled": True},
        {"id": "feishu", "name": "飞书", "enabled": feishu_notifier.is_enabled(), "note": "需配 FEISHU_APP_ID/APP_SECRET/CHAT_ID"},
        {"id": "wecom", "name": "企业微信", "enabled": False, "note": "需配置webhook"},
        {"id": "dingtalk", "name": "钉钉", "enabled": False, "note": "需配置webhook"},
        {"id": "email", "name": "邮件", "enabled": False, "note": "需配置SMTP"},
    ]}


@router.get("/config")
async def get_config():
    return {
        "levels": {
            "urgent": {"icon": "🔴", "cooldown_sec": 0, "channels": ["app", "feishu"]},
            "important": {"icon": "🟠", "cooldown_sec": 300, "channels": ["app", "feishu"]},
            "info": {"icon": "🔵", "cooldown_sec": 1800, "channels": ["app"]},
        },
        "feishu_enabled": feishu_notifier.is_enabled(),
    }
