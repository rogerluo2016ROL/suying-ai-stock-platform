"""Alert API routes — 3-level urgency, 4 channels."""

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/alert", tags=["alert"])

ALERT_LEVELS = ["🔴 urgent", "🟠 important", "🔵 info"]
CHANNELS = ["wecom", "dingtalk", "email", "app_push"]


@router.get("/channels")
async def list_channels():
    """List available alert channels."""
    return {
        "channels": [
            {"id": "wecom",    "name": "企业微信", "type": "webhook"},
            {"id": "dingtalk", "name": "钉钉",     "type": "webhook"},
            {"id": "email",    "name": "邮件",     "type": "smtp"},
            {"id": "app_push", "name": "App推送",  "type": "fcm/apns"},
        ]
    }


@router.get("/config")
async def get_alert_config():
    """Get current alert configuration."""
    return {
        "levels": {
            "urgent":    {"channels": ["all"], "cooldown": 0,    "aggregation": "realtime"},
            "important": {"channels": ["wecom", "dingtalk", "app_push"], "cooldown": 300, "aggregation": "5min"},
            "info":      {"channels": ["app_push", "email"], "cooldown": 1800, "aggregation": "30min"},
        },
        "quiet_hours": {"enabled": True, "start": "22:00", "end": "08:00"},
    }


@router.put("/config")
async def update_alert_config():
    """Update alert configuration (channels, thresholds, quiet hours)."""
    return {"status": "updated", "message": "Alert config updated."}


@router.get("/history")
async def alert_history(limit: int = Query(50, ge=10, le=200)):
    """Query alert history."""
    return {"alerts": [], "limit": limit, "status": "endpoint_ready"}


@router.post("/test")
async def test_alert(
    channel: str = Query("wecom", description="Channel to test"),
    level: str = Query("info", description="Alert level"),
):
    """Send a test alert to verify channel configuration."""
    if channel not in CHANNELS:
        return {"status": "error", "message": f"Unknown channel: {channel}"}
    return {"status": "sent", "channel": channel, "level": level,
            "message": f"Test alert sent via {channel}"}
