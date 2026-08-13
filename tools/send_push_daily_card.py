#!/usr/bin/env python3
"""
Daily push-observability summary card → Feishu chat.

Reads today's 4-task metrics from the push_metrics Base, builds an interactive
card (header colored by system health, conclusion-first, KPI, per-task status,
data-update timestamp, button → dashboard) and sends it to the configured chat
(default AI 投研测试). Mirrors the design in card-preview.html.

    python tools/send_push_daily_card.py [--date YYYY-MM-DD] [--chat-id oc_xxx] [--dry-run]
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "push_observability.json"
TASK_LABELS = {
    "research_pipeline": "研究管线", "embodied_refresh": "具身刷新",
    "screener": "screener", "alert": "告警",
}
STATUS_DOT = {"healthy": "🟢", "warning": "🟠", "degraded": "🔴", "down": "⚫"}
HEADER_TEMPLATE = {"healthy": "green", "warning": "orange", "degraded": "red", "down": "grey"}
STATUS_CN = {"healthy": "健康", "warning": "预警", "degraded": "异常", "down": "待补"}


def _cfg():
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    return raw


def _cli(args, timeout=60):
    p = subprocess.run(["lark-cli", *args, "--as", "user", "--format", "json"],
                       capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"non-json: {(p.stdout or '')[:120]}"}


def _today_cst() -> str:
    import datetime
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    return now.strftime("%Y-%m-%d")


def read_rows(base_token: str, table: str, date: str | None) -> list[dict]:
    fields = ["task", "date", "push_count", "success", "failure", "delivery_confirmed",
              "delivery_unconfirmed", "retries", "latency_ms_p95", "health_score", "status",
              "failure_reasons", "data_updated_at"]
    keyword = date or "20"
    d = _cli(["base", "+record-search", "--base-token", base_token, "--table-id", table,
              "--keyword", keyword, "--search-field", "date",
              *[a for f in fields for a in ("--field-id", f)], "--limit", "50"])
    if not d.get("ok"):
        return []
    data = d.get("data") or {}
    rows_raw = data.get("data") or []
    out = []
    for row in rows_raw:
        rec = {n: (row[i] if i < len(row) else None) for i, n in enumerate(fields)}
        if isinstance(rec.get("status"), list):
            rec["status"] = rec["status"][0] if rec["status"] else "down"
        if date and rec.get("date") != date:
            continue
        out.append(rec)
    return out


def summarize(rows: list[dict]) -> dict:
    total_push = sum(int(r.get("push_count") or 0) for r in rows)
    total_success = sum(int(r.get("success") or 0) for r in rows)
    total_failure = sum(int(r.get("failure") or 0) for r in rows)
    success_rate = (total_success / total_push) if total_push else None
    counts = {"healthy": 0, "warning": 0, "degraded": 0, "down": 0}
    for r in rows:
        counts[r.get("status") or "down"] = counts.get(r.get("status") or "down", 0) + 1
    overall = "degraded" if counts["degraded"] + counts["down"] > 0 else ("warning" if counts["warning"] > 0 else "healthy")
    health = round(sum(int(r.get("health_score") or 0) for r in rows) / len(rows)) if rows else 0
    worst = sorted([r for r in rows if r.get("status") not in (None, "healthy")], key=lambda r: int(r.get("health_score") or 0))
    sr_txt = "—" if success_rate is None else f"{success_rate*100:.1f}%"
    if counts["degraded"] + counts["down"] > 0 and worst:
        w = worst[0]
        conclusion = f"系统异常 — {TASK_LABELS.get(w.get('task'),'有任务')}健康度偏低({w.get('health_score')}),成功率 {sr_txt}"
    elif counts["warning"] > 0:
        conclusion = f"整体健康 — {counts['warning']} 个任务预警,成功率 {sr_txt}"
    else:
        conclusion = f"全部健康 — {counts['healthy']} 个任务正常,成功率 {sr_txt}"
    data_updated = sorted([r.get("data_updated_at") for r in rows if r.get("data_updated_at")])[-1] if rows else None
    return {"total_push": total_push, "total_success": total_success, "total_failure": total_failure,
            "success_rate": success_rate, "counts": counts, "overall": overall, "health": health,
            "conclusion": conclusion, "data_updated": data_updated, "worst": worst}


def build_card(date: str, rows: list[dict], s: dict, dashboard_url: str, base_url: str) -> dict:
    overall = s["overall"]
    sr_txt = "—" if s["success_rate"] is None else f"{s['success_rate']*100:.1f}%"
    task_line = "  ".join(f"{STATUS_DOT.get(r.get('status'),'⚫')}{TASK_LABELS.get(r.get('task'),r.get('task'))} {r.get('health_score')}"
                          for r in sorted(rows, key=lambda x: list(TASK_LABELS).index(x.get('task')) if x.get('task') in TASK_LABELS else 99))
    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"**{STATUS_CN[overall]}** — {s['conclusion'].split('—',1)[-1].strip() if '—' in s['conclusion'] else s['conclusion']}\n今日 4 个任务共推送 {s['total_push']} 条"}},
        {"tag": "div", "fields": [
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**总推送**\n{s['total_push']}"}},
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**成功率**\n{sr_txt}"}},
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**健康度**\n{s['health']}/100"}},
        ]},
        {"tag": "div", "text": {"tag": "lark_md", "content": task_line}},
    ]
    if s["worst"]:
        w = s["worst"][0]
        reason = ""
        fr = w.get("failure_reasons")
        if isinstance(fr, str) and fr.strip():
            reason = f":{fr}"
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": f"🟠 **{TASK_LABELS.get(w.get('task'),'任务')}**({w.get('health_score')}分,{STATUS_CN.get(w.get('status'),'预警')}) {w.get('failure') or 0} 条失败{reason}"}})
    elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [
        {"tag": "plain_text", "content": f"⏱ 数据更新时点:{s['data_updated'] or '—'}  ·  来源:result.json/PG delivery/服务日志  ·  不构成投资建议"},
    ]})
    elements.append({"tag": "action", "actions": [
        {"tag": "button", "text": {"tag": "plain_text", "content": "📊 查看仪表盘(含历史)"},
         "type": "primary", "url": f"{dashboard_url}?date={date}"},
        {"tag": "button", "text": {"tag": "plain_text", "content": "📂 推送指标 Base"}, "type": "default",
         "url": base_url},
    ]})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": f"📡 推送系统日报 · {date}"},
                   "template": HEADER_TEMPLATE.get(overall, "grey")},
        "elements": elements,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--chat-id", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = _cfg()
    date = args.date or _today_cst()
    chat_id = args.chat_id or cfg.get("daily_card_chat_id")
    rows = read_rows(cfg["base_token"], cfg.get("table_name", "push_metrics"), date)
    if not rows:
        print(f"[card] 当日({date})无数据,跳过", file=sys.stderr); return 1
    s = summarize(rows)
    card = build_card(date, rows, s, cfg.get("dashboard_url", ""), cfg.get("base_url", ""))
    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2)); return 0
    if not chat_id:
        print("[card] 未配置 chat-id", file=sys.stderr); return 1
    res = _cli(["im", "+messages-send", "--as", "user", "--chat-id", chat_id,
                "--msg-type", "interactive", "--content", json.dumps(card, ensure_ascii=False)])
    ok = bool(res.get("ok"))
    print(f"[card] send to {chat_id}: ok={ok} {(res.get('error') or '')[:120]}")
    if ok:
        msg_id = (res.get("data") or {}).get("message_id")
        print(f"[card] message_id={msg_id}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
