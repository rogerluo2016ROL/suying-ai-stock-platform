"""Feishu/Lark event callbacks for screener group bot."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.lark_bot import handle_lark_message


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/lark", tags=["lark"])


def _verify_event_token(payload: dict[str, Any]) -> None:
    expected = os.environ.get("LARK_EVENT_VERIFICATION_TOKEN", "").strip()
    if not expected:
        return
    token = str(payload.get("token") or (payload.get("header") or {}).get("token") or "")
    if token != expected:
        raise HTTPException(status_code=403, detail="invalid lark event token")


def _run_event_task(payload: dict[str, Any]) -> None:
    try:
        result = handle_lark_message(payload)
        logger.info("Lark event handled: %s", result)
    except Exception:
        logger.exception("Lark event handling failed")


def _log_event_summary(payload: dict[str, Any], event_type: str | None) -> None:
    """Log non-secret Feishu callback metadata for operations debugging."""
    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    flat_summary = {
        "type": payload.get("type"),
        "event_type": event_type,
        "keys": sorted(payload.keys()),
        "chat_id": payload.get("chat_id") or message.get("chat_id"),
        "sender_id": payload.get("sender_id") or (sender.get("sender_id") or {}).get("open_id"),
        "message_type": payload.get("message_type") or message.get("message_type"),
        "has_encrypt": bool(payload.get("encrypt")),
        "has_challenge": bool(payload.get("challenge")),
    }
    logger.info("Lark callback summary: %s", flat_summary)


@router.post("/events")
async def lark_events(request: Request, background_tasks: BackgroundTasks):
    """Receive Feishu event callbacks.

    Supports:
    - URL verification challenge.
    - im.message.receive_v1 events for fixed screener commands.
    """
    payload = await request.json()

    if payload.get("type") == "url_verification":
        _verify_event_token(payload)
        return {"challenge": payload.get("challenge")}

    _verify_event_token(payload)
    header = payload.get("header") or {}
    event_type = header.get("event_type") or payload.get("event_type") or payload.get("type")
    _log_event_summary(payload, event_type)
    if event_type != "im.message.receive_v1":
        return {"code": 0, "ignored": True, "reason": "unsupported_event_type"}

    background_tasks.add_task(_run_event_task, payload)
    return {"code": 0}


@router.get("/bot/config")
async def lark_bot_config():
    """Return non-secret bot configuration status for operations checks."""
    return {
        "has_app_id": bool(os.environ.get("LARK_APP_ID", "").strip()),
        "has_app_secret": bool(os.environ.get("LARK_APP_SECRET", "").strip()),
        "has_event_token": bool(os.environ.get("LARK_EVENT_VERIFICATION_TOKEN", "").strip()),
        "allowed_chat_ids": [x for x in os.environ.get("LARK_ALLOWED_CHAT_IDS", "").split(",") if x],
        "allowed_user_open_ids": [x for x in os.environ.get("LARK_ALLOWED_USER_OPEN_IDS", "").split(",") if x],
        "commands": [
            "/秋神盘中",
            "/秋神午后",
            "/秋神尾盘",
            "/大葱产业链",
            "/产业链预期差",
            "/毕师傅硬核科技",
            "/竞价选债",
            "/竞价选债V1",
            "/竞价选债V2",
            "/竞价选债V21",
        ],
    }
