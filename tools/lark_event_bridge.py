#!/usr/bin/env python3
"""Bridge lark-cli event stream to the local screener-service Lark endpoint.

This is useful for local development where the Feishu console callback URL is
not yet configured or a stable public HTTPS endpoint is unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request


def post_event(endpoint: str, event: dict) -> None:
    token = os.environ.get("LARK_EVENT_VERIFICATION_TOKEN", "").strip()
    if token and "header" not in event:
        event = {**event, "header": {"token": token}}
    body = json.dumps(event, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge lark-cli events to screener-service")
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:18001/api/v1/lark/events",
        help="Local screener-service event endpoint",
    )
    args = parser.parse_args()

    cmd = [
        "lark-cli",
        "event",
        "consume",
        "im.message.receive_v1",
        "--as",
        "bot",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                post_event(args.endpoint, event)
            except Exception as exc:
                print(f"[bridge] failed to forward event: {exc}", file=sys.stderr)
    finally:
        proc.terminate()
    return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
