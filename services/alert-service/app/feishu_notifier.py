"""飞书（Lark）消息推送 — alert-service 多渠道通知之一。

配置 env（.env / docker env，gitignored）:
  FEISHU_APP_ID        飞书自建应用 app_id (cli_xxx)
  FEISHU_APP_SECRET    飞书自建应用 app_secret
  FEISHU_CHAT_ID       推送目标群 chat_id (oc_xxx)
  FEISHU_ENABLED       显式开关 "true"/"false"（默认: 配齐 APP_ID+APP_SECRET+CHAT_ID 即启用）

依赖: lark-oapi（pyproject.toml）
文档: https://open.feishu.cn/document/home/index
"""
import os
import json
import logging
from typing import Optional

logger = logging.getLogger("alert-service.feishu")

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
    _LARK_AVAILABLE = True
except ImportError:  # lark-oapi 未装时降级，不阻断 alert-service 启动
    _LARK_AVAILABLE = False
    lark = None

_client = None  # 单例 lark client


def get_client():
    """单例 lark client（env 配齐 APP_ID+APP_SECRET 才建）。未配返回 None。"""
    global _client
    if not _LARK_AVAILABLE:
        return None
    if _client is not None:
        return _client
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return None
    _client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
    logger.info("feishu lark client initialized (app_id=%s)", app_id[:8] + "...")
    return _client


def is_enabled() -> bool:
    """飞书推送是否启用：依赖装好 + env 配齐 + 未显式关闭。"""
    explicit = os.environ.get("FEISHU_ENABLED", "").strip().lower()
    if explicit == "false":
        return False
    return get_client() is not None and bool(os.environ.get("FEISHU_CHAT_ID", "").strip())


def _send(receive_id: str, msg_type: str, content: str) -> tuple[bool, str]:
    """底层发消息。返回 (success, msg)。"""
    client = get_client()
    if not client or not receive_id:
        return False, "feishu not enabled (FEISHU_APP_ID/APP_SECRET/CHAT_ID 未配或 lark-oapi 未装)"
    body = CreateMessageRequestBody.builder() \
        .receive_id(receive_id) \
        .msg_type(msg_type) \
        .content(content) \
        .build()
    req = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(body).build()
    resp = client.im.v1.message.create(req)
    if not resp.success():
        logger.error("feishu send failed: code=%s msg=%s", resp.code, resp.msg)
        return False, f"{resp.code}: {resp.msg}"
    return True, resp.msg


def send_text(text: str, chat_id: Optional[str] = None) -> tuple[bool, str]:
    """发文本消息到飞书群。返回 (success, msg)。"""
    cid = chat_id or os.environ.get("FEISHU_CHAT_ID", "").strip()
    return _send(cid, "text", json.dumps({"text": text}))


# 级别 → 卡片 header template 配色
_LEVEL_TEMPLATE = {"urgent": "red", "important": "orange", "info": "blue"}
_LEVEL_ICON = {"urgent": "🔴", "important": "🟠", "info": "🔵"}


def send_alert_card(
    level: str,
    title: str,
    message: str,
    code: str = "",
    score: Optional[float] = None,
    extra: Optional[dict] = None,
    chat_id: Optional[str] = None,
) -> tuple[bool, str]:
    """发预警交互卡片到飞书群。

    level: urgent/important/info
    title: 预警标题
    message: 预警正文
    code: 标的代码（可选）
    score: 评分（可选）
    extra: 额外字段 dict（可选，如 {"模式": "leader_scalp", "涨幅": "+9.8%"}）
    """
    cid = chat_id or os.environ.get("FEISHU_CHAT_ID", "").strip()
    template = _LEVEL_TEMPLATE.get(level, "blue")
    icon = _LEVEL_ICON.get(level, "🔵")

    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"{icon} **{title}**\n{message}"}}
    ]
    fields = []
    if code:
        fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**标的**\n{code}"}})
    if score is not None:
        fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**分数**\n{score}"}})
    fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**级别**\n{level}"}})
    if extra:
        for k, v in extra.items():
            fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**{k}**\n{v}"}})
    if fields:
        elements.append({"tag": "div", "fields": fields})

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"速赢AI 预警 · {title}"},
            "template": template,
        },
        "elements": elements,
    }
    return _send(cid, "interactive", json.dumps(card))


def notify(level: str, title: str, message: str, code: str = "",
           score: Optional[float] = None, extra: Optional[dict] = None,
           chat_id: Optional[str] = None) -> tuple[bool, str]:
    """统一入口：预警触发时调用。启用则发卡片，未启用返回 (False, 原因) 不抛异常。"""
    if not is_enabled():
        return False, "feishu disabled"
    try:
        return send_alert_card(level=level, title=title, message=message, code=code,
                               score=score, extra=extra, chat_id=chat_id)
    except Exception as e:
        logger.exception("feishu notify error")
        return False, f"exception: {e}"
