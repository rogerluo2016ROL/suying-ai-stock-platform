"""Alert API routes — real notification system."""

from fastapi import APIRouter, Query
from app.alert_store import get_store

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
    channel: str = Query("app", description="app/wecom/dingtalk/email"),
):
    """Manually trigger an alert (for testing/hooks)."""
    alert = store.create(level=level, title=title, message=message, code=code, channel=channel)
    if alert:
        return {"alert": {"id": alert.id, "level": alert.level, "title": alert.title}, "status": "created"}
    return {"status": "cooled_down", "message": "Similar alert within 5 min, skipped"}


@router.get("/channels")
async def list_channels():
    return {"channels": [
        {"id": "app", "name": "平台弹窗", "enabled": True},
        {"id": "wecom", "name": "企业微信", "enabled": False, "note": "需配置webhook"},
        {"id": "dingtalk", "name": "钉钉", "enabled": False, "note": "需配置webhook"},
        {"id": "email", "name": "邮件", "enabled": False, "note": "需配置SMTP"},
    ]}


@router.get("/config")
async def get_config():
    return {
        "levels": {
            "urgent": {"icon": "🔴", "cooldown_sec": 0, "channels": ["app"]},
            "important": {"icon": "🟠", "cooldown_sec": 300, "channels": ["app"]},
            "info": {"icon": "🔵", "cooldown_sec": 1800, "channels": ["app"]},
        },
    }
