"""Lark/Feishu 客户端 I/O 原语 — 从 lark_bot.py 抽出的自包含发送层。

仅依赖 stdlib (json/os/time/urllib/subprocess/pathlib)，无 lark_bot 内部依赖。
lark_bot.py 通过 `from .lark_client import ...` 复用，保持原调用不变。
"""
import json
import os
import re
import time
import urllib.request
import subprocess
from pathlib import Path
from typing import Any

_TENANT_TOKEN: dict[str, Any] = {"token": None, "expires_at": 0.0}


def send_card_to_chat(chat_id: str, card: Any, *, idempotency_key: str | None = None) -> dict[str, Any]:
    """发送交互卡片到群。card 可为 dict 或 JSON 字符串。返回飞书响应(含 message_id)。"""
    if isinstance(card, dict):
        card = json.dumps(card, ensure_ascii=False)
    if not os.environ.get("LARK_APP_ID", "").strip() or not os.environ.get("LARK_APP_SECRET", "").strip():
        return _send_card_via_lark_cli(chat_id, card, idempotency_key=idempotency_key)
    token = get_tenant_access_token()
    body = json.dumps({"receive_id": chat_id, "msg_type": "interactive", "content": card},
                      ensure_ascii=False).encode("utf-8")
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id" + (f"&uuid={urllib.parse.quote(idempotency_key)}" if idempotency_key else "")
    req = urllib.request.Request(url, data=body,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"send card failed: {exc.code} {exc.read().decode('utf-8', errors='replace')}") from exc
    if data.get("code") != 0:
        raise RuntimeError(f"send card failed: {data}")
    return data

def _send_card_via_lark_cli(chat_id: str, card: str, *, idempotency_key: str | None = None) -> dict[str, Any]:
    """lark-cli 兜底发送交互卡片(无 app 凭证时)。"""
    import subprocess
    cmd = ["lark-cli", "im", "+messages-send", "--as", "user", "--chat-id", chat_id,
           "--msg-type", "interactive", "--content", card, "--format", "json"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(p.stdout or "{}")
    except Exception as exc:
        raise RuntimeError(f"send card via lark-cli failed: {exc}") from exc
    if not data.get("ok"):
        raise RuntimeError(f"send card via lark-cli failed: {data.get('error')}")
    return data

def get_tenant_access_token() -> str:
    """Get and cache Feishu tenant access token for bot sending."""
    now = time.time()
    if _TENANT_TOKEN["token"] and now < float(_TENANT_TOKEN["expires_at"]):
        return str(_TENANT_TOKEN["token"])

    app_id = os.environ.get("LARK_APP_ID", "").strip()
    app_secret = os.environ.get("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("missing LARK_APP_ID or LARK_APP_SECRET")

    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"tenant token failed: {data}")
    _TENANT_TOKEN["token"] = data["tenant_access_token"]
    _TENANT_TOKEN["expires_at"] = now + int(data.get("expire", 7200)) - 120
    return str(_TENANT_TOKEN["token"])

def _send_text_to_chat_via_lark_cli(chat_id: str, text: str, *, idempotency_key: str | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    cmd = [
        "lark-cli",
        "im",
        "+messages-send",
        "--as",
        "bot",
        "--chat-id",
        chat_id,
        "--text",
        text,
        "--json",
    ]
    if idempotency_key:
        cmd.extend(["--idempotency-key", idempotency_key])
    proc = subprocess.run(
        cmd,
        cwd=root,
        text=True,
        capture_output=True,
        timeout=int(os.environ.get("LARK_CLI_SEND_TIMEOUT_SEC", "30")),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-1200:]
        raise RuntimeError(f"send message via lark-cli failed: {detail or proc.returncode}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"code": 0, "raw": proc.stdout.strip()}

def _split_streaming_text(text: str, max_chars: int = 700) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    for paragraph in re.split(r"(\n+)", text):
        if not paragraph:
            continue
        candidate = current + paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current.strip():
            chunks.append(current.strip())
        current = paragraph
        while len(current) > max_chars:
            chunks.append(current[:max_chars].strip())
            current = current[max_chars:]
    if current.strip():
        chunks.append(current.strip())
    return chunks

def _multipart_body(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f"----suying-lark-{int(time.time() * 1000)}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, (filename, content, content_type) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

def upload_lark_image(path: Path) -> str:
    token = get_tenant_access_token()
    content = path.read_bytes()
    body, content_type = _multipart_body(
        {"image_type": "message"},
        {"image": (path.name, content, "image/png")},
    )
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/images",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"upload image failed: {exc.code} {detail}") from exc
    if data.get("code") != 0:
        raise RuntimeError(f"upload image failed: {data}")
    image_key = ((data.get("data") or {}).get("image_key")) or ""
    if not image_key:
        raise RuntimeError(f"upload image missing image_key: {data}")
    return str(image_key)

def send_image_to_chat(chat_id: str, path: Path) -> dict[str, Any]:
    token = get_tenant_access_token()
    image_key = upload_lark_image(path)
    body = json.dumps(
        {
            "receive_id": chat_id,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key}, ensure_ascii=False),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"send image failed: {exc.code} {detail}") from exc
    if data.get("code") != 0:
        raise RuntimeError(f"send image failed: {data}")
    return data
