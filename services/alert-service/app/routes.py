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
