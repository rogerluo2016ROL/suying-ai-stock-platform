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
import time
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
        default=os.environ.get("LARK_EVENT_BRIDGE_ENDPOINT", "http://127.0.0.1:18001/api/v1/lark/events"),
        help="Local screener-service event endpoint",
    )
    parser.add_argument(
        "--consume-timeout",
        default=os.environ.get("LARK_EVENT_CONSUME_TIMEOUT", "24h"),
        help="Restart lark-cli after this bounded consume duration; bounded mode survives stdin EOF.",
    )
    parser.add_argument(
        "--restart-delay",
        type=float,
        default=float(os.environ.get("LARK_EVENT_RESTART_DELAY_SEC", "5")),
        help="Seconds to wait before restarting lark-cli after it exits.",
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("LARK_CLI_PROFILE", ""),
        help="lark-cli profile to consume events as (must match the bot app the screener replies with).",
    )
    args = parser.parse_args()

    cmd = ["lark-cli"]
    if args.profile:
        cmd += ["--profile", args.profile]
    cmd += [
        "event",
        "consume",
        "im.message.receive_v1",
        "--as",
        "bot",
        "--timeout",
        args.consume_timeout,
    ]
    try:
        while True:
            print(f"[bridge] starting: {' '.join(cmd)}", file=sys.stderr, flush=True)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    post_event(args.endpoint, event)
                    payload = event.get("event") or event
                    message = payload.get("message") or {}
                    print(
                        "[bridge] forwarded event"
                        f" type={event.get('type') or (event.get('header') or {}).get('event_type')}"
                        f" chat_id={event.get('chat_id') or message.get('chat_id') or '-'}"
                        f" message_type={event.get('message_type') or message.get('message_type') or '-'}",
                        file=sys.stderr,
                        flush=True,
                    )
                except Exception as exc:
                    print(f"[bridge] failed to forward event: {exc}", file=sys.stderr, flush=True)

            code = proc.wait()
            print(
                f"[bridge] lark-cli exited code={code}; restarting in {args.restart_delay}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(args.restart_delay)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
