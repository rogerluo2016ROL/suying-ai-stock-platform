"""Feishu/Lark group bot integration for screener commands.

This module intentionally keeps the bot surface narrow: fixed commands only,
fixed chat/user allowlists, and no shell execution.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


_TENANT_TOKEN: dict[str, Any] = {"token": None, "expires_at": 0.0}
MODEL_TITLES = {
    "leader_intraday": "秋神盘中选股分析报告",
    "leader_afternoon": "秋神午后选股分析报告",
    "leader_closing": "秋神尾盘选股分析报告",
    "supply_chain": "大葱产业链解构选股分析报告",
    "bi_trend_launch": "毕师傅硬核科技趋势启动选股分析报告",
    "cb_auction_t0": "竞价 T+0 选债 V1 分析报告",
    "cb_auction_t0_v2": "竞价 T+0 选债 V2 分析报告",
    "cb_auction_t0_v2_1": "竞价 T+0 选债 V2.1 稳健版分析报告",
}
CB_AUCTION_MODES = {"cb_auction_t0", "cb_auction_t0_v2", "cb_auction_t0_v2_1"}
DEFAULT_LARK_REPORT_FOLDER_TOKEN = "GDlmf7ZIKltfRIdrGn7cyPKJnCg"


@dataclass(frozen=True)
class LarkCommand:
    command: str
    mode: str
    top_n: int = 20
    trade_date: str | None = None


def _csv_env(name: str) -> set[str]:
    return {x.strip() for x in os.environ.get(name, "").split(",") if x.strip()}


def extract_text_message(payload: dict[str, Any]) -> dict[str, str]:
    """Extract chat_id, sender open_id, and plain text from a Feishu event."""
    # lark-cli event consume emits a flattened shape:
    # {type, chat_id, sender_id, message_type, content, ...}
    if payload.get("type") == "im.message.receive_v1" and "chat_id" in payload:
        return {
            "chat_id": str(payload.get("chat_id") or ""),
            "sender_open_id": str(payload.get("sender_id") or ""),
            "message_type": str(payload.get("message_type") or ""),
            "text": str(payload.get("content") or "").strip(),
        }

    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}

    content_raw = message.get("content") or "{}"
    try:
        content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
    except json.JSONDecodeError:
        content = {}

    return {
        "chat_id": str(message.get("chat_id") or ""),
        "sender_open_id": str(sender_id.get("open_id") or ""),
        "message_type": str(message.get("message_type") or ""),
        "text": str(content.get("text") or "").strip(),
    }


def is_allowed_event(chat_id: str, sender_open_id: str) -> bool:
    """Check optional allowlists. Empty allowlist means the dimension is not restricted."""
    allowed_chats = _csv_env("LARK_ALLOWED_CHAT_IDS")
    allowed_users = _csv_env("LARK_ALLOWED_USER_OPEN_IDS")
    if allowed_chats and chat_id not in allowed_chats:
        return False
    if allowed_users and sender_open_id not in allowed_users:
        return False
    return True


def users_are_restricted() -> bool:
    return bool(_csv_env("LARK_ALLOWED_USER_OPEN_IDS"))


def parse_command(text: str) -> LarkCommand | None:
    """Parse supported bot commands.

    Supported examples:
      /秋神午后
      /毕师傅硬核科技
      /秋神午后 2026-07-03 top=10
    """
    text = (text or "").strip()
    slash_index = text.find("/")
    if slash_index > 0:
        text = text[slash_index:].strip()
    if not text.startswith("/"):
        return None

    parts = text.split()
    head = parts[0].strip()
    trade_date = None
    top_n = 20
    for part in parts[1:]:
        if part.startswith("top="):
            try:
                top_n = max(5, min(30, int(part.split("=", 1)[1])))
            except ValueError:
                pass
        elif part.startswith("date="):
            value = part.split("=", 1)[1]
            if len(value) == 10 and value[4] == "-" and value[7] == "-":
                trade_date = value
        elif len(part) == 10 and part[4] == "-" and part[7] == "-":
            trade_date = part

    if head in {"/秋神盘中", "/秋神盘中选股", "/盘中"}:
        return LarkCommand(command=head, mode="leader_intraday", top_n=top_n, trade_date=trade_date)
    if head in {"/秋神午后", "/秋神午后选股", "/秋神", "/午后"}:
        return LarkCommand(command=head, mode="leader_afternoon", top_n=top_n, trade_date=trade_date)
    if head in {"/秋神尾盘", "/秋神尾盘选股", "/尾盘"}:
        return LarkCommand(command=head, mode="leader_closing", top_n=top_n, trade_date=trade_date)
    if head in {"/大葱产业链", "/产业链", "/大葱"}:
        return LarkCommand(command=head, mode="supply_chain", top_n=top_n, trade_date=trade_date)
    if head in {"/毕师傅硬核科技", "/毕师傅", "/硬核科技"}:
        return LarkCommand(command=head, mode="bi_trend_launch", top_n=top_n, trade_date=trade_date)
    if head in {"/竞价选债", "/竞价T0选债", "/竞价T+0选债", "/秋神竞价选债", "/竞价选债V21", "/竞价选债V2.1"}:
        return LarkCommand(command=head, mode="cb_auction_t0_v2_1", top_n=top_n, trade_date=trade_date)
    if head in {"/竞价选债V2", "/竞价T0选债V2", "/竞价T+0选债V2"}:
        return LarkCommand(command=head, mode="cb_auction_t0_v2", top_n=top_n, trade_date=trade_date)
    if head in {"/竞价选债V1", "/竞价T0选债V1", "/竞价T+0选债V1"}:
        return LarkCommand(command=head, mode="cb_auction_t0", top_n=top_n, trade_date=trade_date)
    return None


def run_command(command: LarkCommand) -> dict[str, Any]:
    """Run a whitelisted screener command through the existing engine path."""
    from app.routers.screener import (
        _run_afternoon_mode,
        _run_bi_trend_mode,
        _run_cb_mode,
        _run_leader_mode,
        _run_supply_chain_mode,
    )

    if command.mode in {"leader_intraday", "leader_closing"}:
        result = _run_leader_mode(command.mode, command.top_n, command.trade_date)
    elif command.mode == "leader_afternoon":
        result = _run_afternoon_mode(command.mode, command.top_n, command.trade_date)
    elif command.mode == "supply_chain":
        result = _run_supply_chain_mode(command.mode, command.top_n, command.trade_date)
    elif command.mode == "bi_trend_launch":
        result = _run_bi_trend_mode(command.mode, command.top_n, command.trade_date)
    elif command.mode in CB_AUCTION_MODES:
        result = _run_cb_mode(command.mode, command.top_n, command.trade_date)
    else:
        raise ValueError(f"unsupported command mode: {command.mode}")
    return result


def refresh_before_run(command: LarkCommand) -> dict[str, Any]:
    """Best-effort latest data refresh before running a model."""
    if os.environ.get("LARK_REFRESH_BEFORE_RUN", "1").strip().lower() in {"0", "false", "no"}:
        return {"status": "skipped", "reason": "disabled"}

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    script = os.path.join(root, "tools", "lark_refresh_before_screen.py")
    timeout = int(os.environ.get("LARK_REFRESH_TIMEOUT_SEC", "240") or "240")
    env = os.environ.copy()
    env.setdefault("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    cmd = [
        sys.executable,
        script,
        "--mode",
        command.mode,
        "--trade-date",
        command.trade_date or "",
    ]
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "elapsed": round(time.time() - started, 1)}

    stdout = (proc.stdout or "").strip().splitlines()
    payload = None
    if stdout:
        try:
            payload = json.loads(stdout[-1])
        except json.JSONDecodeError:
            payload = {"stdout_tail": stdout[-1][:300]}
    result = payload or {}
    result["status"] = "ok" if proc.returncode == 0 else "error"
    result["returncode"] = proc.returncode
    result["elapsed"] = round(time.time() - started, 1)
    if proc.stderr:
        result["stderr_tail"] = proc.stderr.strip()[-300:]
    return result


def format_report(result: dict[str, Any]) -> str:
    mode = result.get("mode", "")
    if mode in MODEL_TITLES:
        if mode in CB_AUCTION_MODES:
            return _format_cb_report(result)
        return _format_stock_report(result)
    return f"未知模型结果: {mode}"


def _fmt_price(v: Any) -> str:
    try:
        val = float(v)
        if val <= 0:
            return "-"
        return f"{val:.2f}"
    except (TypeError, ValueError):
        return "-"


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _row_value(row: Any, *keys: str) -> Any:
    if not row:
        return None
    if isinstance(row, dict):
        for key in keys:
            if key in row and row[key] is not None:
                return row[key]
        return None
    try:
        return row[0]
    except Exception:
        return None


def _fmt_pct(v: Any) -> str:
    try:
        return f"{float(v):.2f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_score(v: Any) -> str:
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "-"


def _markdown_cell(value: Any) -> str:
    text = "-" if value in (None, "") else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _display_width(text: str) -> int:
    width = 0
    for ch in str(text):
        width += 2 if ord(ch) > 127 else 1
    return width


def _clip_text(text: Any, max_width: int) -> str:
    raw = "-" if text in (None, "") else str(text)
    width = 0
    out = []
    for ch in raw:
        ch_width = 2 if ord(ch) > 127 else 1
        if width + ch_width > max_width:
            return "".join(out) + "..."
        out.append(ch)
        width += ch_width
    return "".join(out)


def _format_data_update(mode: str) -> str:
    sources = {
        "leader_intraday": [("stk_mins", "SELECT MAX(trade_time) FROM stk_mins"), ("daily_kline", "SELECT MAX(trade_date) FROM daily_kline")],
        "leader_afternoon": [("stk_mins", "SELECT MAX(trade_time) FROM stk_mins"), ("daily_kline", "SELECT MAX(trade_date) FROM daily_kline")],
        "leader_closing": [("stk_mins", "SELECT MAX(trade_time) FROM stk_mins"), ("daily_kline", "SELECT MAX(trade_date) FROM daily_kline")],
        "supply_chain": [("daily_kline", "SELECT MAX(trade_date) FROM daily_kline")],
        "bi_trend_launch": [("daily_kline", "SELECT MAX(trade_date) FROM daily_kline")],
        "cb_auction_t0": [
            ("limit_list_d", "SELECT MAX(trade_date) FROM limit_list_d"),
            ("stk_auction_o", "SELECT MAX(trade_date) FROM stk_auction_o"),
            ("stk_limit", "SELECT MAX(trade_date) FROM stk_limit"),
        ],
        "cb_auction_t0_v2": [
            ("limit_list_d", "SELECT MAX(trade_date) FROM limit_list_d"),
            ("stk_auction_o", "SELECT MAX(trade_date) FROM stk_auction_o"),
            ("stk_limit", "SELECT MAX(trade_date) FROM stk_limit"),
        ],
        "cb_auction_t0_v2_1": [
            ("limit_list_d", "SELECT MAX(trade_date) FROM limit_list_d"),
            ("stk_auction_o", "SELECT MAX(trade_date) FROM stk_auction_o"),
            ("stk_limit", "SELECT MAX(trade_date) FROM stk_limit"),
        ],
    }.get(mode, [("daily_kline", "SELECT MAX(trade_date) FROM daily_kline")])
    try:
        from app.routers.screener import _get_factor_db

        parts = []
        with _get_factor_db() as db:
            for name, sql in sources:
                row = db.execute(sql).fetchone()
                value = _row_value(row, "max")
                parts.append(f"{name}={str(value)[:19] if value else '-'}")
        return "；".join(parts)
    except Exception:
        return "-"


def _format_refresh_summary(refresh: dict[str, Any] | None) -> str:
    if not refresh:
        return "-"
    status = refresh.get("status", "-")
    if status == "skipped":
        return f"跳过 ({refresh.get('reason', '-')})"
    if status == "timeout":
        return f"超时 ({refresh.get('elapsed', '-')}s)"
    parts = [f"状态 {status}", f"耗时 {refresh.get('elapsed', '-')}s"]
    stk = refresh.get("stk_mins")
    if isinstance(stk, dict):
        parts.append(f"分钟线 {stk.get('status', '-')}/PG {stk.get('pg_written', '-')}")
    core = refresh.get("post_market_core")
    if isinstance(core, dict):
        daily = core.get("daily_kline")
        index = core.get("index_daily")
        limit = core.get("stk_limit")
        if isinstance(daily, dict):
            parts.append(f"日线PG {daily.get('pg_written', daily.get('written', '-'))}")
        if isinstance(index, dict):
            parts.append(f"指数PG {index.get('pg_written', index.get('written', '-'))}")
        if isinstance(limit, dict):
            parts.append(f"涨停价PG {limit.get('pg_written', limit.get('written', '-'))}")
    elif isinstance(core, dict) and core.get("message"):
        parts.append(f"盘后核心 {core.get('message')}")
    return "；".join(parts)


def _format_data_fetch_time(refresh: dict[str, Any] | None) -> str:
    """Report when this run finished refreshing/fetching data."""
    if isinstance(refresh, dict):
        value = refresh.get("finished_at") or refresh.get("started_at")
        if value:
            return str(value).replace("T", " ")[:19]
    return _generated_at()


def _pick_price(p: dict[str, Any]) -> Any:
    return _first_value(p.get("current_price"), p.get("price"), p.get("close_14"), p.get("close"))


def _pick_gain(p: dict[str, Any]) -> Any:
    return _first_value(p.get("gain_pct"), p.get("gain_14"), p.get("daily_gain"), p.get("pct_chg"))


def _cb_reason(p: dict[str, Any]) -> str:
    pieces = []
    reason = _first_value(p.get("entry_reason"), p.get("relation_reason"), p.get("observation_reason"), p.get("quality_tier_reason"))
    if reason:
        pieces.append(str(reason))
    if p.get("quality_tier"):
        pieces.append(f"质量档{p.get('quality_tier')}")
    if p.get("theme_score") is not None:
        pieces.append(f"题材分{_fmt_score(p.get('theme_score'))}")
    if p.get("matched_concept_strength") is not None:
        pieces.append(f"概念竞价强度{_fmt_pct(p.get('matched_concept_strength'))}")
    if p.get("matched_concepts"):
        concepts = p.get("matched_concepts")
        if isinstance(concepts, list):
            concepts = "、".join(map(str, concepts[:5]))
        pieces.append(f"匹配概念: {concepts}")
    if p.get("trigger_sources"):
        sources = p.get("trigger_sources")
        if isinstance(sources, list):
            sources = "、".join(map(str, sources[:5]))
        pieces.append(f"触发来源: {sources}")
    risks = p.get("risk_flags") or p.get("risk_notes") or []
    if risks:
        pieces.append("风险: " + "、".join(map(str, risks[:3])))
    return "；".join(pieces) if pieces else "-"


def _pick_reason(p: dict[str, Any]) -> str:
    reason = _first_value(p.get("entry_reason"), p.get("reason"))
    if reason:
        return str(reason)
    leader_reason = _leader_factor_reason(p)
    if leader_reason:
        return leader_reason
    pieces = []
    if p.get("chain"):
        pieces.append(f"产业链: {p.get('chain')}")
    if p.get("layer"):
        pieces.append(f"环节: {p.get('layer')}")
    if p.get("node_name"):
        pieces.append(f"节点: {p.get('node_name')}")
    if p.get("policy_theme"):
        pieces.append(f"政策主题: {p.get('policy_theme')}")
    if p.get("moat_signals"):
        moat = p.get("moat_signals")
        if isinstance(moat, list):
            moat = "、".join(map(str, moat[:5]))
        pieces.append(f"壁垒: {moat}")
    if p.get("trade_signal"):
        pieces.append(f"信号: {p.get('trade_signal')}")
    flags = p.get("power_flags") or p.get("quality_flags") or []
    if flags:
        pieces.append("信号: " + "、".join(map(str, flags[:3])))
    risk_flags = p.get("risk_flags") or []
    if risk_flags:
        pieces.append("风险: " + "、".join(map(str, risk_flags[:3])))
    return "；".join(pieces) if pieces else "-"


def _leader_factor_reason(p: dict[str, Any]) -> str:
    """Convert leader-model factor fields into a readable reason without inventing data."""
    factor_labels = [
        ("resonance_score", "板块共振"),
        ("sector_momentum_score", "板块动量"),
        ("sector_leader_score", "板块龙头强度"),
        ("capital_score", "资金确认"),
        ("volume_score", "量能放大"),
        ("turnover_score", "换手活跃"),
        ("ma_score", "均线趋势"),
        ("seal_score", "涨停接近度"),
        ("resilience_score", "分歧承接"),
        ("gain_score", "涨幅强度"),
    ]
    scored: list[tuple[float, str]] = []
    for key, label in factor_labels:
        value = p.get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            scored.append((number, f"{label}{number:.1f}"))

    pieces = []
    gain = _pick_gain(p)
    if gain is not None:
        pieces.append(f"个股涨幅{_fmt_pct(gain)}")
    sector = _first_value(p.get("industry"), p.get("sector"))
    if sector:
        sector_text = f"板块{sector}"
        if p.get("sector_change") is not None:
            sector_text += f"涨幅{_fmt_pct(p.get('sector_change'))}"
        pieces.append(sector_text)

    if scored:
        scored.sort(reverse=True, key=lambda item: item[0])
        pieces.append("主要因子: " + "、".join(text for _, text in scored[:4]))

    if p.get("peer_count") not in (None, ""):
        pieces.append(f"同板块跟随{p.get('peer_count')}只")
    if p.get("dist_to_limit") not in (None, ""):
        pieces.append(f"距涨停{_fmt_pct(p.get('dist_to_limit'))}")
    flags = p.get("optimization_flags") or []
    if flags:
        pieces.append("校准信号: " + "、".join(map(str, flags[:3])))
    weakness = p.get("seal_weakness")
    if weakness:
        pieces.append(f"风险提示: {weakness}")
    return "；".join(pieces)


def _sector_resonance_lines(picks: list[dict[str, Any]], result: dict[str, Any]) -> list[str]:
    if result.get("mode") in CB_AUCTION_MODES:
        return _cb_resonance_lines(picks, result)

    explicit = result.get("sector_resonance") or []
    if explicit:
        lines = []
        for item in explicit[:5]:
            sector = item.get("sector") or item.get("industry") or "-"
            count = item.get("count") or item.get("stock_count") or item.get("peer_count") or "-"
            score = item.get("score") or item.get("avg_score") or item.get("resonance_score") or "-"
            lines.append(f"- {sector}: {count} 只，强度 {score}")
        return lines

    grouped: dict[str, dict[str, Any]] = {}
    for p in picks:
        sector = str(_first_value(p.get("industry"), p.get("sector"), p.get("chain"), p.get("node_name"), "-"))
        row = grouped.setdefault(sector, {"count": 0, "scores": [], "changes": []})
        row["count"] += 1
        for key in ("resonance_score", "sector_momentum_score", "sector_leader_score"):
            if p.get(key) is not None:
                row["scores"].append(float(p[key]))
        if p.get("sector_change") is not None:
            row["changes"].append(float(p["sector_change"]))
    if not grouped:
        return ["- 暂无可统计的板块共振数据"]
    ranked = sorted(
        grouped.items(),
        key=lambda item: (item[1]["count"], sum(item[1]["scores"]) / max(1, len(item[1]["scores"]))),
        reverse=True,
    )
    lines = []
    for sector, data in ranked[:5]:
        avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else None
        avg_change = sum(data["changes"]) / len(data["changes"]) if data["changes"] else None
        desc = f"- {sector}: 入选 {data['count']} 只"
        if avg_change is not None:
            desc += f"，板块涨幅 {avg_change:.2f}%"
        if avg_score is not None:
            desc += f"，共振均分 {avg_score:.1f}"
        lines.append(desc)
    return lines


def _cb_resonance_lines(picks: list[dict[str, Any]], result: dict[str, Any]) -> list[str]:
    process = result.get("process_summary") or {}
    lines = []
    if process:
        lines.append(
            "- 筛选过程: "
            f"触发股 {process.get('trigger_stock_count', '-')} 只，"
            f"概念 {process.get('concept_count', '-')} 个，"
            f"主买 {process.get('main_pick_count', len(picks))} 只，"
            f"观察 {process.get('observation_pick_count', result.get('total_observation_picks', 0))} 只，"
            f"剔除 {process.get('rejection_count', '-')} 条"
        )
    grouped: dict[str, dict[str, Any]] = {}
    for p in picks + (result.get("observation_picks") or []):
        concepts = p.get("matched_concepts")
        if isinstance(concepts, list) and concepts:
            keys = [str(x) for x in concepts[:3]]
        else:
            keys = [str(_first_value(p.get("concept_name"), p.get("sector"), p.get("industry"), "未标注概念"))]
        for concept in keys:
            row = grouped.setdefault(concept, {"count": 0, "scores": []})
            row["count"] += 1
            if p.get("theme_score") is not None:
                row["scores"].append(float(p["theme_score"]))
    if grouped:
        ranked = sorted(
            grouped.items(),
            key=lambda item: (item[1]["count"], sum(item[1]["scores"]) / max(1, len(item[1]["scores"]))),
            reverse=True,
        )
        for concept, data in ranked[:5]:
            avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else None
            desc = f"- {concept}: 关联转债 {data['count']} 只"
            if avg_score is not None:
                desc += f"，题材均分 {avg_score:.1f}"
            lines.append(desc)
    if result.get("no_result_reason"):
        lines.append(f"- 无主买原因: {result.get('no_result_reason')}")
    return lines or ["- 暂无可统计的竞价选债共振数据"]


def _plans_by_code(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(p.get("code")): p for p in result.get("execution_plans") or [] if p.get("code")}


def _generated_at() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _numeric_values(rows: list[dict[str, Any]], *keys: str) -> list[float]:
    values = []
    for row in rows:
        for key in keys:
            value = row.get(key)
            if value is None:
                continue
            try:
                values.append(float(value))
                break
            except (TypeError, ValueError):
                continue
    return values


def _top_stock_sector(picks: list[dict[str, Any]]) -> tuple[str, int, float | None]:
    grouped: dict[str, dict[str, Any]] = {}
    for p in picks:
        sector = str(_first_value(p.get("industry"), p.get("sector"), p.get("chain"), p.get("node_name"), "-"))
        row = grouped.setdefault(sector, {"count": 0, "scores": []})
        row["count"] += 1
        score = _first_value(p.get("total_score"), p.get("score"), p.get("resonance_score"))
        if score is not None:
            try:
                row["scores"].append(float(score))
            except (TypeError, ValueError):
                pass
    if not grouped:
        return "-", 0, None
    sector, data = max(
        grouped.items(),
        key=lambda item: (item[1]["count"], sum(item[1]["scores"]) / max(1, len(item[1]["scores"]))),
    )
    avg = sum(data["scores"]) / len(data["scores"]) if data["scores"] else None
    return sector, int(data["count"]), avg


def _stock_market_diagnosis(result: dict[str, Any]) -> tuple[list[tuple[str, str, str]], str]:
    picks = result.get("picks") or []
    count = len(picks)
    scores = _numeric_values(picks, "total_score", "score")
    avg_score = sum(scores) / len(scores) if scores else None
    sector, sector_count, sector_avg = _top_stock_sector(picks)
    refresh = result.get("data_refresh") or {}
    refresh_status = refresh.get("status", "-") if isinstance(refresh, dict) else "-"

    if count == 0:
        count_judgement = "未通过模型门槛"
        conclusion = "本次模型没有给出可执行清单，先观察，不强行出手。"
    elif count <= 3:
        count_judgement = "机会稀缺，适合小仓位精选"
        conclusion = "本次机会较少，重点看高分个股和是否有明确板块共振。"
    elif count <= 10:
        count_judgement = "结构性机会，需按评分和板块二次筛选"
        conclusion = "本次存在结构性机会，优先选择评分高且处于强共振板块的标的。"
    else:
        count_judgement = "候选较多，需控制仓位和去弱留强"
        conclusion = "本次候选较多，不能平均买入，应按评分、板块和风险标签二次过滤。"

    if avg_score is None:
        score_judgement = "无评分字段，无法评价强弱"
        score_text = "-"
    elif avg_score >= 85:
        score_judgement = "模型均分强"
        score_text = f"{avg_score:.1f}"
    elif avg_score >= 75:
        score_judgement = "模型均分中强"
        score_text = f"{avg_score:.1f}"
    elif avg_score >= 65:
        score_judgement = "模型均分中性"
        score_text = f"{avg_score:.1f}"
    else:
        score_judgement = "模型均分偏弱"
        score_text = f"{avg_score:.1f}"

    if sector_count >= 3:
        sector_judgement = "板块共振较明显"
    elif sector_count >= 2:
        sector_judgement = "有轻度板块聚集"
    elif sector_count == 1:
        sector_judgement = "标的较分散"
    else:
        sector_judgement = "无入选板块"
    sector_text = f"{sector} {sector_count}只"
    if sector_avg is not None:
        sector_text += f"，均分{sector_avg:.1f}"

    refresh_judgement = "数据刷新正常" if refresh_status == "ok" else f"刷新状态 {refresh_status}"
    rows = [
        ("数据刷新", str(refresh_status), refresh_judgement),
        ("入选数量", f"{count}只", count_judgement),
        ("平均评分", score_text, score_judgement),
        ("最强板块", sector_text, sector_judgement),
    ]
    return rows, conclusion


def _cb_market_diagnosis(result: dict[str, Any]) -> tuple[list[tuple[str, str, str]], str]:
    picks = result.get("picks") or []
    observation = result.get("observation_picks") or []
    process = result.get("process_summary") or {}
    refresh = result.get("data_refresh") or {}
    refresh_status = refresh.get("status", "-") if isinstance(refresh, dict) else "-"
    scores = _numeric_values(picks, "theme_score", "score")
    avg_score = sum(scores) / len(scores) if scores else None
    trigger_count = process.get("trigger_stock_count", "-")
    concept_count = process.get("concept_count", "-")
    rejection_count = process.get("rejection_count", "-")

    if picks:
        conclusion = "本次竞价选债有主买标的，优先看质量档、题材分和触发概念是否一致。"
        pick_judgement = "有主买候选"
    elif observation:
        conclusion = "本次没有主买标的，但有观察池，说明严格规则未放行，适合只观察不追买。"
        pick_judgement = "无主买，有观察池"
    else:
        conclusion = result.get("no_result_reason") or "本次没有转债通过模型门槛。"
        pick_judgement = "无主买候选"

    rows = [
        ("数据刷新", str(refresh_status), "数据刷新正常" if refresh_status == "ok" else f"刷新状态 {refresh_status}"),
        ("触发股", f"{trigger_count}只", "竞价触发源数量"),
        ("触发概念", f"{concept_count}个", "概念映射强度参考"),
        ("主买/观察", f"{len(picks)}只 / {len(observation)}只", pick_judgement),
        ("题材均分", f"{avg_score:.1f}" if avg_score is not None else "-", "主买题材强度" if avg_score is not None else "无主买评分"),
        ("剔除记录", f"{rejection_count}条", "用于解释未入选原因"),
    ]
    return rows, conclusion


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(_markdown_cell(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_cell(cell) for cell in row) + " |")
    return lines


def _xml_escape(value: Any) -> str:
    text = "-" if value in (None, "") else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _xml_table(headers: list[str], rows: list[list[Any]]) -> str:
    header = "".join(f'<th background-color="light-gray">{_xml_escape(h)}</th>' for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_xml_escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def build_lark_doc_xml_report(result: dict[str, Any]) -> str:
    mode = result.get("mode", "")
    is_cb = mode in CB_AUCTION_MODES
    title = MODEL_TITLES.get(mode, "模型分析报告")
    trade_date = result.get("trade_date") or "latest"
    picks = result.get("picks") or []
    diagnosis_rows, conclusion = _cb_market_diagnosis(result) if is_cb else _stock_market_diagnosis(result)
    data_label = "选债日期" if is_cb else "选股日期"
    list_title = "选债清单" if is_cb else "选股清单"
    resonance_title = "板块/概念共振" if is_cb else "板块共振"
    update_rows = [
        [data_label, trade_date],
        ["报告生成时间", _generated_at()],
        ["本次取数时间", _format_data_fetch_time(result.get("data_refresh"))],
        ["数据更新时点", _format_data_update(mode)],
        ["本次刷新", _format_refresh_summary(result.get("data_refresh"))],
        ["主买数量" if is_cb else "入选数量", f"{len(picks)}只"],
    ]
    if is_cb:
        update_rows.append(["观察数量", f"{len(result.get('observation_picks') or [])}只"])

    parts = [
        f"<h1>{_xml_escape(title)}（{_xml_escape(trade_date)} {_xml_escape(datetime.now().strftime('%H:%M'))}）</h1>",
        build_whiteboard_svg_block(result),
        "<h2>一、数据更新时间和日期</h2>",
        _xml_table(["项目", "内容"], update_rows),
        "<h2>二、市场状态诊断</h2>",
        _xml_table(["指标", "数据", "判断"], [[a, b, c] for a, b, c in diagnosis_rows]),
        f"<p><b>市场结论：</b>{_xml_escape(conclusion)}</p>",
        f"<h2>三、{_xml_escape(list_title)}</h2>",
    ]
    if is_cb:
        parts.extend(_cb_xml_sections(result))
    else:
        parts.append(_stock_xml_table(result))

    resonance = _cb_resonance_lines(picks, result) if is_cb else _sector_resonance_lines(picks, result)
    parts.append(f"<h2>四、{_xml_escape(resonance_title)}</h2>")
    parts.append("<ul>" + "".join(f"<li>{_xml_escape(str(line).lstrip('- '))}</li>" for line in resonance) + "</ul>")
    trace = result.get("screening_trace") or []
    if is_cb and trace:
        parts.append("<h3>筛选过程</h3>")
        parts.append(
            "<ul>"
            + "".join(
                "<li>"
                + _xml_escape(
                    f"{step.get('step', '-')}: {step.get('status', '-')}；输入 {step.get('input_count', '-')}；输出 {step.get('output_count', '-')}；说明 {step.get('message') or step.get('reason') or '-'}"
                )
                + "</li>"
                for step in trace
            )
            + "</ul>"
        )
    parts.extend(
        [
            "<h2>五、风险提示</h2>",
            '<callout emoji="❗" background-color="light-yellow" border-color="yellow">',
            "<ul>",
            "<li>本报告是模型筛选结果，不是自动买入指令。</li>",
            "<li>盘中数据会变化，后续重新运行可能得到不同结果。</li>",
            "<li>缺失字段统一显示为 -，不会补造价格、目标价、封单金额或原因。</li>",
            "</ul>",
            "</callout>",
        ]
    )
    return "\n".join(parts)


def _stock_xml_table(result: dict[str, Any]) -> str:
    picks = result.get("picks") or []
    plans = _plans_by_code(result)
    if not picks:
        return "<p>本次没有股票通过模型门槛。</p>"
    rows = []
    for i, p in enumerate(picks[:20], 1):
        plan = plans.get(str(p.get("code")), {})
        target = _first_value(plan.get("take_profit_full"), plan.get("take_profit"), p.get("target_price"), p.get("take_profit"))
        stop = _first_value(plan.get("stop_loss_normal"), plan.get("stop_loss"), p.get("stop_loss"))
        rows.append(
            [
                i,
                p.get("code"),
                p.get("name"),
                _fmt_price(_pick_price(p)),
                _fmt_pct(_pick_gain(p)),
                _fmt_price(target),
                _fmt_price(stop),
                _first_value(p.get("industry"), p.get("sector"), p.get("chain"), p.get("node_name"), "-"),
                _fmt_score(p.get("total_score") or p.get("score")),
                _pick_reason(p),
            ]
        )
    return _xml_table(["序号", "代码", "名称", "现价", "涨幅", "目标价", "止损价", "板块", "评分", "选股原因"], rows)


def _cb_xml_sections(result: dict[str, Any]) -> list[str]:
    picks = result.get("picks") or []
    observation = result.get("observation_picks") or []
    parts = ["<h3>主买清单</h3>"]
    if picks:
        parts.append(_xml_table(["序号", "转债代码", "转债名称", "正股代码", "正股名称", "质量档", "题材分", "封单金额", "匹配概念", "选债原因"], [_cb_row_values(i, p) for i, p in enumerate(picks[:20], 1)]))
    else:
        parts.append(f"<p>{_xml_escape(result.get('no_result_reason') or '本次没有转债通过主买门槛。')}</p>")
    if observation:
        parts.append("<h3>观察池</h3>")
        parts.append(_xml_table(["序号", "转债代码", "转债名称", "正股代码", "正股名称", "质量档", "题材分", "封单金额", "匹配概念", "观察原因"], [_cb_row_values(i, p) for i, p in enumerate(observation[:20], 1)]))
    return parts


def _cb_row_values(index: int, p: dict[str, Any]) -> list[Any]:
    concepts = p.get("matched_concepts")
    if isinstance(concepts, list):
        concepts = "、".join(map(str, concepts[:5]))
    return [
        index,
        p.get("code") or p.get("cb_code"),
        p.get("name") or p.get("cb_name"),
        p.get("stk_code"),
        p.get("stk_name"),
        p.get("quality_tier"),
        _fmt_score(p.get("theme_score") or p.get("score")),
        _fmt_amount_yi(p.get("matched_fd_amount") or p.get("fd_amount")),
        concepts or p.get("concept_name"),
        _cb_reason(p),
    ]


def build_whiteboard_svg_block(result: dict[str, Any]) -> str:
    return f'<whiteboard type="svg">{build_poster_svg(result)}</whiteboard>'


def build_poster_svg(result: dict[str, Any]) -> str:
    mode = result.get("mode", "")
    is_cb = mode in CB_AUCTION_MODES
    title = MODEL_TITLES.get(mode, "模型分析报告")
    trade_date = result.get("trade_date") or "latest"
    picks = result.get("picks") or []
    observation = result.get("observation_picks") or []
    diagnosis_rows, conclusion = _cb_market_diagnosis(result) if is_cb else _stock_market_diagnosis(result)
    subject = "选债" if is_cb else "选股"
    width, height = 900, 1400
    metric_rows = _poster_metrics(result, diagnosis_rows, is_cb)
    top_items = _poster_top_items(result, is_cb)
    resonance = _cb_resonance_lines(picks, result) if is_cb else _sector_resonance_lines(picks, result)
    status = _poster_status_text(result, is_cb)
    no_result = result.get("no_result_reason") or f"本次没有{subject}通过模型门槛。"
    gold = "#ead89b"
    gold_dark = "#caa85a"
    ink = "#f7efd4"
    muted = "#c9bd95"
    panel = "#15130f"
    border = "#6d5931"
    table_headers = ["序号", "转债", "名称", "正股/概念", "评分", "档位"] if is_cb else ["序号", "代码", "名称", "板块", "评分", "涨幅"]
    table_rows = _poster_table_rows(top_items, is_cb)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<radialGradient id="glow" cx="82%" cy="12%" r="62%"><stop offset="0%" stop-color="#83662c" stop-opacity="0.95"/><stop offset="42%" stop-color="#251b0c" stop-opacity="0.76"/><stop offset="100%" stop-color="#050403" stop-opacity="1"/></radialGradient>',
        '<linearGradient id="panel" x1="0" x2="1" y1="0" y2="1"><stop offset="0%" stop-color="#1e1a13"/><stop offset="100%" stop-color="#0b0a08"/></linearGradient>',
        '<filter id="shadow" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#000000" flood-opacity="0.45"/></filter>',
        "</defs>",
        '<rect width="900" height="1400" fill="#050403"/>',
        '<rect width="900" height="1400" fill="url(#glow)" opacity="0.92"/>',
        '<circle cx="780" cy="150" r="210" fill="#d8ad4f" opacity="0.18"/>',
        '<circle cx="86" cy="1190" r="240" fill="#d8ad4f" opacity="0.10"/>',
        '<path d="M675 0 C710 120 836 154 900 180 L900 0 Z" fill="#c59b3b" opacity="0.28"/>',
        '<path d="M0 1260 C168 1222 262 1320 400 1400 L0 1400 Z" fill="#d4aa4e" opacity="0.12"/>',
        '<text x="62" y="76" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="23" font-weight="700" fill="#f5e6b1">SUYING AI 投研分析</text>',
        f'<text x="62" y="132" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="42" font-weight="800" fill="{gold}">{_xml_escape(_clip_text(title, 22))}</text>',
        f'<text x="62" y="176" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="22" fill="{muted}">数据日期 { _xml_escape(str(trade_date)) }  ·  更新时间 {_xml_escape(_generated_at()[11:])}  ·  {subject}</text>',
        f'<text x="62" y="224" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="26" font-weight="800" fill="{ink}">市场状态：{_xml_escape(_clip_text(status, 16))}</text>',
    ]

    for idx, metric in enumerate(metric_rows[:4]):
        x = 62 + (idx % 2) * 392
        y = 266 + (idx // 2) * 124
        lines.append(_svg_dark_metric_card(x, y, 352, 102, metric[0], metric[1], metric[2], gold, muted, border))

    lines.append(f'<rect x="56" y="532" width="788" height="126" rx="18" fill="{panel}" stroke="{border}" stroke-width="1.5" filter="url(#shadow)"/>')
    lines.append(f'<text x="84" y="568" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="24" font-weight="800" fill="{gold}">市场诊断</text>')
    for i, line in enumerate(_wrap_for_poster(conclusion, 34)[:2]):
        lines.append(f'<text x="84" y="{602 + i * 28}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="19" fill="{ink}">{_xml_escape(line)}</text>')

    lines.append(f'<text x="62" y="704" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="28" font-weight="800" fill="{gold}">{subject}清单 Top {min(8, len(top_items))}</text>')
    if top_items:
        lines.append(_svg_poster_pick_table(56, 732, table_headers, table_rows, [58, 118, 146, 204, 104, 112], border, ink, muted, gold_dark))
    else:
        lines.append(f'<rect x="56" y="732" width="742" height="116" rx="18" fill="{panel}" stroke="{border}" stroke-width="1.5"/>')
        lines.append(f'<text x="86" y="780" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="24" font-weight="800" fill="{gold}">暂无主买标的</text>')
        lines.append(f'<text x="86" y="818" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" fill="{ink}">{_xml_escape(_clip_text(no_result, 30))}</text>')

    lines.append(f'<text x="62" y="1220" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="27" font-weight="800" fill="{gold}">板块共振</text>')
    for i, line in enumerate(resonance[:3]):
        y = 1260 + i * 32
        lines.append(f'<rect x="64" y="{y - 19}" width="10" height="10" fill="{gold}"/>')
        lines.append(f'<text x="88" y="{y}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" fill="{ink}">{_xml_escape(_clip_text(str(line).lstrip("- "), 34))}</text>')
    risk = "非买入指令 · 盘中数据会变化 · 缺失字段不补造"
    if is_cb and observation:
        risk = f"观察池 {len(observation)} 只 · " + risk
    lines.append(f'<line x1="62" y1="1350" x2="838" y2="1350" stroke="{border}" stroke-width="1.5"/>')
    lines.append(f'<text x="62" y="1380" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18" fill="{muted}">{_xml_escape(risk)}</text>')
    lines.append(f'<text x="735" y="1380" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18" fill="{muted}">Suying AI</text>')
    lines.append("</svg>")
    return "\n".join(lines)


def _poster_status_text(result: dict[str, Any], is_cb: bool) -> str:
    picks = result.get("picks") or []
    observation = result.get("observation_picks") or []
    if is_cb:
        if picks:
            return "有主买候选"
        if observation:
            return "仅观察池"
        return "无主买候选"
    if not picks:
        return "无入选标的"
    if len(picks) <= 3:
        return "机会稀缺"
    if len(picks) <= 10:
        return "结构性机会"
    return "候选较多"


def _poster_metrics(result: dict[str, Any], diagnosis_rows: list[tuple[str, str, str]], is_cb: bool) -> list[tuple[str, str, str]]:
    row_map = {name: (data, judgement) for name, data, judgement in diagnosis_rows}
    if is_cb:
        return [
            ("主买/观察", row_map.get("主买/观察", ("-", "-"))[0], row_map.get("主买/观察", ("-", "-"))[1]),
            ("触发股", row_map.get("触发股", ("-", "-"))[0], row_map.get("触发股", ("-", "-"))[1]),
            ("题材均分", row_map.get("题材均分", ("-", "-"))[0], row_map.get("题材均分", ("-", "-"))[1]),
            ("触发概念", row_map.get("触发概念", ("-", "-"))[0], row_map.get("触发概念", ("-", "-"))[1]),
        ]
    return [
        ("入选数量", row_map.get("入选数量", ("-", "-"))[0], row_map.get("入选数量", ("-", "-"))[1]),
        ("平均评分", row_map.get("平均评分", ("-", "-"))[0], row_map.get("平均评分", ("-", "-"))[1]),
        ("最强板块", row_map.get("最强板块", ("-", "-"))[0], row_map.get("最强板块", ("-", "-"))[1]),
        ("数据刷新", row_map.get("数据刷新", ("-", "-"))[0], row_map.get("数据刷新", ("-", "-"))[1]),
    ]


def _poster_top_items(result: dict[str, Any], is_cb: bool) -> list[dict[str, str]]:
    items = []
    for p in (result.get("picks") or [])[:8]:
        if is_cb:
            concepts = p.get("matched_concepts")
            if isinstance(concepts, list):
                concepts = "、".join(map(str, concepts[:2]))
            items.append(
                {
                    "code": str(p.get("code") or p.get("cb_code") or "-"),
                    "name": str(p.get("name") or p.get("cb_name") or "-"),
                    "meta": f"正股 {p.get('stk_code') or '-'} {p.get('stk_name') or '-'}",
                    "score": _fmt_score(p.get("theme_score") or p.get("score")),
                    "tag": str(p.get("quality_tier") or concepts or "-"),
                    "sector": str(concepts or p.get("stk_name") or p.get("concept_name") or "-"),
                    "reason": _cb_reason(p),
                }
            )
        else:
            items.append(
                {
                    "code": str(p.get("code") or "-"),
                    "name": str(p.get("name") or "-"),
                    "meta": str(_first_value(p.get("industry"), p.get("sector"), p.get("chain"), p.get("node_name"), "-")),
                    "score": _fmt_score(p.get("total_score") or p.get("score")),
                    "tag": _fmt_pct(_pick_gain(p)),
                    "sector": str(_first_value(p.get("industry"), p.get("sector"), p.get("chain"), p.get("node_name"), "-")),
                    "reason": _pick_reason(p),
                }
            )
    return items


def _poster_table_rows(items: list[dict[str, str]], is_cb: bool) -> list[list[Any]]:
    rows = []
    for idx, item in enumerate(items[:8], 1):
        rows.append(
            [
                idx,
                item.get("code", "-"),
                item.get("name", "-"),
                item.get("sector" if is_cb else "meta", "-"),
                item.get("score", "-"),
                item.get("tag", "-"),
            ]
        )
    return rows


def _svg_metric_card(x: int, y: int, w: int, h: int, label: str, value: str, note: str, accent: str) -> str:
    return "\n".join(
        [
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="#ffffff" stroke="#e1e6ef" stroke-width="2" filter="url(#shadow)"/>',
            f'<text x="{x + 22}" y="{y + 34}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="19" fill="#64748b">{_xml_escape(_clip_text(label, 14))}</text>',
            f'<text x="{x + 22}" y="{y + 76}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="32" font-weight="800" fill="{accent}">{_xml_escape(_clip_text(value, 14))}</text>',
            f'<text x="{x + 22}" y="{y + 108}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18" fill="#475569">{_xml_escape(_clip_text(note, 18))}</text>',
        ]
    )


def _svg_dark_metric_card(x: int, y: int, w: int, h: int, label: str, value: str, note: str, gold: str, muted: str, border: str) -> str:
    return "\n".join(
        [
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="#15130f" stroke="{border}" stroke-width="1.5"/>',
            f'<text x="{x + 20}" y="{y + 31}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18" fill="{muted}">{_xml_escape(_clip_text(label, 12))}</text>',
            f'<text x="{x + 20}" y="{y + 63}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="25" font-weight="800" fill="{gold}">{_xml_escape(_clip_text(value, 14))}</text>',
            f'<text x="{x + 20}" y="{y + 88}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="15" fill="{muted}">{_xml_escape(_clip_text(note, 24))}</text>',
        ]
    )


def _svg_pick_card(x: int, y: int, w: int, h: int, rank: int, item: dict[str, str], accent: str) -> str:
    return "\n".join(
        [
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="26" fill="#ffffff" stroke="#e1e6ef" stroke-width="2" filter="url(#shadow)"/>',
            f'<circle cx="{x + 36}" cy="{y + 38}" r="20" fill="{accent}"/>',
            f'<text x="{x + 29}" y="{y + 46}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" font-weight="800" fill="#ffffff">{rank}</text>',
            f'<text x="{x + 72}" y="{y + 35}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="24" font-weight="800" fill="#111827">{_xml_escape(_clip_text(item["name"], 13))}</text>',
            f'<text x="{x + 72}" y="{y + 67}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" fill="#64748b">{_xml_escape(_clip_text(item["code"], 18))}</text>',
            f'<rect x="{x + 224}" y="{y + 28}" width="84" height="36" rx="18" fill="#eef6ff"/>',
            f'<text x="{x + 242}" y="{y + 52}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="19" font-weight="800" fill="{accent}">{_xml_escape(_clip_text(item["score"], 6))}</text>',
            f'<text x="{x + 26}" y="{y + 104}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" fill="#334155">{_xml_escape(_clip_text(item["meta"], 23))}</text>',
            f'<text x="{x + 26}" y="{y + 136}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="19" fill="#64748b">{_xml_escape(_clip_text(item["tag"], 18))}</text>',
            f'<text x="{x + 26}" y="{y + 162}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="17" fill="#64748b">{_xml_escape(_clip_text(item["reason"], 28))}</text>',
        ]
    )


def _svg_poster_pick_table(
    x: int,
    y: int,
    headers: list[str],
    rows: list[list[Any]],
    widths: list[int],
    border: str,
    ink: str,
    muted: str,
    header_fill: str,
) -> str:
    row_h = 52
    header_h = 48
    total_w = sum(widths)
    out = [
        f'<rect x="{x}" y="{y}" width="{total_w}" height="{header_h + row_h * len(rows)}" rx="16" fill="#11100d" stroke="{border}" stroke-width="1.5" filter="url(#shadow)"/>',
        f'<rect x="{x}" y="{y}" width="{total_w}" height="{header_h}" rx="16" fill="{header_fill}" opacity="0.72"/>',
        f'<rect x="{x}" y="{y + 24}" width="{total_w}" height="{header_h - 24}" fill="{header_fill}" opacity="0.72"/>',
    ]
    cx = x
    for header, width in zip(headers, widths):
        out.append(f'<text x="{cx + 12}" y="{y + 31}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18" font-weight="700" fill="#fff4c8">{_xml_escape(header)}</text>')
        cx += width
    y += header_h
    for idx, row in enumerate(rows):
        fill = "#17140f" if idx % 2 == 0 else "#0f0d0a"
        out.append(f'<rect x="{x}" y="{y}" width="{total_w}" height="{row_h}" fill="{fill}" opacity="0.96"/>')
        cx = x
        for col_idx, (cell, width) in enumerate(zip(row, widths)):
            max_chars = max(3, int((width - 18) / 15))
            fill_color = ink if col_idx in {1, 2} else muted
            out.append(f'<text x="{cx + 12}" y="{y + 33}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18" font-weight="500" fill="{fill_color}">{_xml_escape(_clip_text(cell, max_chars))}</text>')
            cx += width
        out.append(f'<line x1="{x}" y1="{y + row_h}" x2="{x + total_w}" y2="{y + row_h}" stroke="{border}" stroke-width="1" opacity="0.72"/>')
        y += row_h
    return "\n".join(out)


def _svg_table(x: int, y: int, headers: list[str], rows: list[list[Any]], widths: list[int]) -> str:
    row_h = 54
    total_w = sum(widths)
    out = [f'<rect x="{x}" y="{y}" width="{total_w}" height="{row_h}" fill="#eef2f7" stroke="#d7dbe3" stroke-width="2"/>']
    cx = x
    for header, width in zip(headers, widths):
        out.append(f'<text x="{cx + 12}" y="{y + 35}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="22" font-weight="700" fill="#15181d">{_xml_escape(header)}</text>')
        out.append(f'<line x1="{cx}" y1="{y}" x2="{cx}" y2="{y + row_h}" stroke="#d7dbe3" stroke-width="1"/>')
        cx += width
    out.append(f'<line x1="{x + total_w}" y1="{y}" x2="{x + total_w}" y2="{y + row_h}" stroke="#d7dbe3" stroke-width="1"/>')
    y += row_h
    for idx, row in enumerate(rows):
        fill = "#ffffff" if idx % 2 == 0 else "#fbfcff"
        out.append(f'<rect x="{x}" y="{y}" width="{total_w}" height="{row_h}" fill="{fill}" stroke="#d7dbe3" stroke-width="1"/>')
        cx = x
        for cell, width in zip(row, widths):
            out.append(f'<text x="{cx + 12}" y="{y + 35}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="21" fill="#15181d">{_xml_escape(_clip_text(cell, max(4, int(width / 14))))}</text>')
            out.append(f'<line x1="{cx}" y1="{y}" x2="{cx}" y2="{y + row_h}" stroke="#d7dbe3" stroke-width="1"/>')
            cx += width
        out.append(f'<line x1="{x + total_w}" y1="{y}" x2="{x + total_w}" y2="{y + row_h}" stroke="#d7dbe3" stroke-width="1"/>')
        y += row_h
    return "\n".join(out)



def _format_stock_report(result: dict[str, Any]) -> str:
    mode = result.get("mode", "")
    trade_date = result.get("trade_date") or "latest"
    picks = result.get("picks") or []
    plans = _plans_by_code(result)
    lines = [
        MODEL_TITLES.get(mode, "选股分析报告"),
        f"选股日期: {trade_date}",
        f"本次取数时间: {_format_data_fetch_time(result.get('data_refresh'))}",
        f"数据更新时点: {_format_data_update(mode)}",
        f"本次刷新: {_format_refresh_summary(result.get('data_refresh'))}",
        f"入选: {len(picks)} 只",
        "",
        "选股清单:",
    ]
    for i, p in enumerate(picks[:20], 1):
        plan = plans.get(str(p.get("code")), {})
        score = p.get("total_score") or p.get("score")
        price = _pick_price(p)
        gain = _pick_gain(p)
        target = _first_value(plan.get("take_profit_full"), plan.get("take_profit"), p.get("target_price"), p.get("take_profit"))
        stop = _first_value(plan.get("stop_loss_normal"), plan.get("stop_loss"), p.get("stop_loss"))
        sector = _first_value(p.get("industry"), p.get("sector"), p.get("chain"), p.get("node_name"), "-")
        reason = _pick_reason(p)
        lines.append(
            f"{i}. {p.get('code')} {p.get('name')}"
            f" | 现价 {_fmt_price(price)} | 涨幅 {_fmt_pct(gain)}"
            f" | 目标 {_fmt_price(target)} | 止损 {_fmt_price(stop)}"
            f" | 板块 {sector} | 评分 {score if score is not None else '-'}"
            f" | 原因 {reason}"
        )
    lines.append("")
    lines.append("板块共振情况说明:")
    lines.extend(_sector_resonance_lines(picks, result))
    lines.append("")
    lines.append("说明: 结果不是自动买入指令；缺失字段用 - 表示，不补造价格。")
    return "\n".join(lines)


def _format_cb_report(result: dict[str, Any]) -> str:
    mode = result.get("mode", "")
    trade_date = result.get("trade_date") or "latest"
    picks = result.get("picks") or []
    observation = result.get("observation_picks") or []
    lines = [
        MODEL_TITLES.get(mode, "竞价 T+0 选债分析报告"),
        f"选债日期: {trade_date}",
        f"本次取数时间: {_format_data_fetch_time(result.get('data_refresh'))}",
        f"数据更新时点: {_format_data_update(mode)}",
        f"本次刷新: {_format_refresh_summary(result.get('data_refresh'))}",
        f"主买: {len(picks)} 只；观察: {len(observation)} 只",
        "",
        "主买清单:",
    ]
    for i, p in enumerate(picks[:20], 1):
        concepts = p.get("matched_concepts")
        if isinstance(concepts, list):
            concepts = "、".join(map(str, concepts[:4]))
        lines.append(
            f"{i}. {p.get('code')} {p.get('name')}"
            f" | 正股 {p.get('stk_code') or '-'} {p.get('stk_name') or '-'}"
            f" | 质量档 {p.get('quality_tier') or '-'} | 题材分 {_fmt_score(p.get('theme_score') or p.get('score'))}"
            f" | 封单 {_fmt_amount_yi(p.get('matched_fd_amount') or p.get('fd_amount'))}"
            f" | 概念 {concepts or '-'} | 原因 {_cb_reason(p)}"
        )
    if not picks:
        lines.append(result.get("no_result_reason") or "本次没有转债通过主买门槛。")
    if observation:
        lines.extend(["", "观察池:"])
        for i, p in enumerate(observation[:10], 1):
            lines.append(
                f"{i}. {p.get('code')} {p.get('name')}"
                f" | 正股 {p.get('stk_code') or '-'} {p.get('stk_name') or '-'}"
                f" | 质量档 {p.get('quality_tier') or '-'} | 题材分 {_fmt_score(p.get('theme_score') or p.get('score'))}"
                f" | 原因 {_cb_reason(p)}"
            )
    lines.append("")
    lines.append("板块/概念共振情况说明:")
    lines.extend(_cb_resonance_lines(picks, result))
    lines.append("")
    lines.append("说明: 竞价 T+0 选债依赖涨停触发股、竞价封单和概念映射；缺失字段用 - 表示，不补造数据。")
    return "\n".join(lines)


def _fmt_amount_yi(v: Any) -> str:
    try:
        value = float(v)
    except (TypeError, ValueError):
        return "-"
    if value <= 0:
        return "-"
    if value >= 10_000_000:
        value = value / 100_000_000
    return f"{value:.2f}亿"


def build_markdown_report(result: dict[str, Any]) -> str:
    if result.get("mode") in CB_AUCTION_MODES:
        return build_cb_markdown_report(result)

    mode = result.get("mode", "")
    title = MODEL_TITLES.get(mode, "选股分析报告")
    trade_date = result.get("trade_date") or "latest"
    picks = result.get("picks") or []
    plans = _plans_by_code(result)
    diagnosis_rows, conclusion = _stock_market_diagnosis(result)
    data_update = _format_data_update(mode)
    refresh_summary = _format_refresh_summary(result.get("data_refresh"))
    lines = [
        f"# {title}（{trade_date} {datetime.now().strftime('%H:%M')}）",
        "",
        "## 一、数据更新时间和日期",
        "",
        *_markdown_table(
            ["项目", "内容"],
            [
                ["选股日期", trade_date],
                ["报告生成时间", _generated_at()],
                ["本次取数时间", _format_data_fetch_time(result.get("data_refresh"))],
                ["数据更新时点", data_update],
                ["本次刷新", refresh_summary],
                ["入选数量", f"{len(picks)}只"],
            ],
        ),
        "",
        "## 二、市场状态诊断",
        "",
        *_markdown_table(["指标", "数据", "判断"], [[a, b, c] for a, b, c in diagnosis_rows]),
        "",
        f"市场结论：{conclusion}",
        "",
        "## 三、选股清单",
        "",
    ]
    if picks:
        lines.extend(
            [
                "| 序号 | 代码 | 名称 | 现价 | 涨幅 | 目标价 | 止损价 | 板块 | 评分 | 选股原因 |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |",
            ]
        )
        for i, p in enumerate(picks[:20], 1):
            plan = plans.get(str(p.get("code")), {})
            score = p.get("total_score") or p.get("score")
            price = _pick_price(p)
            gain = _pick_gain(p)
            target = _first_value(plan.get("take_profit_full"), plan.get("take_profit"), p.get("target_price"), p.get("take_profit"))
            stop = _first_value(plan.get("stop_loss_normal"), plan.get("stop_loss"), p.get("stop_loss"))
            sector = _first_value(p.get("industry"), p.get("sector"), p.get("chain"), p.get("node_name"), "-")
            cells = [
                i,
                p.get("code"),
                p.get("name"),
                _fmt_price(price),
                _fmt_pct(gain),
                _fmt_price(target),
                _fmt_price(stop),
                sector,
                _fmt_score(score),
                _pick_reason(p),
            ]
            lines.append("| " + " | ".join(_markdown_cell(cell) for cell in cells) + " |")
    else:
        lines.append("本次没有股票通过模型门槛。")

    lines.extend(["", "## 四、板块共振", ""])
    lines.extend(_sector_resonance_lines(picks, result))
    lines.extend(
        [
            "",
            "## 五、风险提示",
            "",
            "- 本报告是模型筛选结果，不是自动买入指令。",
            "- 缺失字段统一显示为 `-`，不会补造价格、目标价或原因。",
            "- 盘中数据随时间变化，后续重新运行可能得到不同结果。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_cb_markdown_report(result: dict[str, Any]) -> str:
    mode = result.get("mode", "")
    title = MODEL_TITLES.get(mode, "竞价 T+0 选债分析报告")
    trade_date = result.get("trade_date") or "latest"
    picks = result.get("picks") or []
    observation = result.get("observation_picks") or []
    diagnosis_rows, conclusion = _cb_market_diagnosis(result)
    data_update = _format_data_update(mode)
    refresh_summary = _format_refresh_summary(result.get("data_refresh"))
    lines = [
        f"# {title}（{trade_date} {datetime.now().strftime('%H:%M')}）",
        "",
        "## 一、数据更新时间和日期",
        "",
        *_markdown_table(
            ["项目", "内容"],
            [
                ["选债日期", trade_date],
                ["报告生成时间", _generated_at()],
                ["本次取数时间", _format_data_fetch_time(result.get("data_refresh"))],
                ["数据更新时点", data_update],
                ["本次刷新", refresh_summary],
                ["主买数量", f"{len(picks)}只"],
                ["观察数量", f"{len(observation)}只"],
            ],
        ),
        "",
        "## 二、市场状态诊断",
        "",
        *_markdown_table(["指标", "数据", "判断"], [[a, b, c] for a, b, c in diagnosis_rows]),
        "",
        f"市场结论：{conclusion}",
        "",
        "## 三、选债清单",
        "",
        "### 主买清单",
        "",
    ]
    if picks:
        lines.extend(
            [
                "| 序号 | 转债代码 | 转债名称 | 正股代码 | 正股名称 | 质量档 | 题材分 | 封单金额 | 匹配概念 | 选债原因 |",
                "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for i, p in enumerate(picks[:20], 1):
            lines.append(_cb_markdown_row(i, p))
    else:
        lines.append(result.get("no_result_reason") or "本次没有转债通过主买门槛。")

    if observation:
        lines.extend(["", "### 观察池", ""])
        lines.extend(
            [
                "| 序号 | 转债代码 | 转债名称 | 正股代码 | 正股名称 | 质量档 | 题材分 | 封单金额 | 匹配概念 | 观察原因 |",
                "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for i, p in enumerate(observation[:20], 1):
            lines.append(_cb_markdown_row(i, p))

    lines.extend(["", "## 四、板块/概念共振", ""])
    lines.extend(_cb_resonance_lines(picks, result))
    trace = result.get("screening_trace") or []
    if trace:
        lines.extend(["", "## 筛选过程", ""])
        for step in trace:
            lines.append(
                f"- {step.get('step', '-')}: {step.get('status', '-')}"
                f"；输入 {step.get('input_count', '-')}"
                f"；输出 {step.get('output_count', '-')}"
                f"；说明 {step.get('message') or step.get('reason') or '-'}"
            )
    lines.extend(
        [
            "",
            "## 五、风险提示",
            "",
            "- 本报告是模型筛选结果，不是自动买入指令。",
            "- 竞价 T+0 选债依赖涨停触发股、竞价封单和概念映射；缺失字段统一显示为 `-`。",
            "- 若 `limit_list_d` 当日为空，模型会按现有逻辑使用已接入的备用触发数据；报告不补造封单金额。",
        ]
    )
    return "\n".join(lines) + "\n"


def _cb_markdown_row(index: int, p: dict[str, Any]) -> str:
    concepts = p.get("matched_concepts")
    if isinstance(concepts, list):
        concepts = "、".join(map(str, concepts[:5]))
    cells = [
        index,
        p.get("code") or p.get("cb_code"),
        p.get("name") or p.get("cb_name"),
        p.get("stk_code"),
        p.get("stk_name"),
        p.get("quality_tier"),
        _fmt_score(p.get("theme_score") or p.get("score")),
        _fmt_amount_yi(p.get("matched_fd_amount") or p.get("fd_amount")),
        concepts or p.get("concept_name"),
        _cb_reason(p),
    ]
    return "| " + " | ".join(_markdown_cell(cell) for cell in cells) + " |"


def generate_poster_image(result: dict[str, Any]) -> Path | None:
    if os.environ.get("LARK_POSTER_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return None

    root = Path(__file__).resolve().parents[3]
    mode = str(result.get("mode") or "unknown")
    trade_date = str(result.get("trade_date") or datetime.now().strftime("%Y-%m-%d"))
    poster_dir = root / "outputs" / "lark_posters" / trade_date
    poster_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    path = poster_dir / (re.sub(r"[^0-9A-Za-z_-]+", "_", f"{stamp}_{mode}")[:80] + ".png")
    svg_path = path.with_suffix(".svg")
    svg_path.write_text(build_poster_svg(result), encoding="utf-8")
    chrome = _chrome_binary()
    if not chrome:
        raise RuntimeError("未找到 Chrome，无法把海报 SVG 渲染成可发送 PNG")
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--window-size=900,1400",
        f"--screenshot={path}",
        "file://" + str(svg_path),
    ]
    proc = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=int(os.environ.get("LARK_POSTER_RENDER_TIMEOUT_SEC", "30")))
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "").strip()[-800:] or f"chrome exited {proc.returncode}")
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError("海报 PNG 生成失败")
    return path


def _chrome_binary() -> str | None:
    candidates = [
        os.environ.get("CHROME_BIN", "").strip(),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome",
        "chromium",
        "chromium-browser",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if "/" in candidate:
            if Path(candidate).exists():
                return candidate
            continue
        try:
            proc = subprocess.run(["/usr/bin/env", "which", candidate], text=True, capture_output=True, timeout=3)
        except Exception:
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().splitlines()[0]
    return None


def _wrap_for_poster(text: str, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in str(text):
        candidate = current + ch
        if _display_width(candidate) > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or ["-"]


def _draw_poster_table(draw, x: int, y: int, headers: list[str], rows: list[list[Any]], col_widths: list[int], font, border: str, ink: str, muted: str) -> int:
    row_h = 58
    table_w = sum(col_widths)
    draw.rectangle((x, y, x + table_w, y + row_h), fill="#eef2f7", outline=border, width=2)
    col_x = x
    for header, col_w in zip(headers, col_widths):
        draw.text((col_x + 12, y + 15), str(header), fill=ink, font=font)
        draw.line((col_x, y, col_x, y + row_h), fill=border, width=1)
        col_x += col_w
    draw.line((x + table_w, y, x + table_w, y + row_h), fill=border, width=1)
    y += row_h
    for idx, row in enumerate(rows):
        fill = "#ffffff" if idx % 2 == 0 else "#fbfcff"
        draw.rectangle((x, y, x + table_w, y + row_h), fill=fill, outline=border, width=1)
        col_x = x
        for value, col_w in zip(row, col_widths):
            max_chars = max(4, int(col_w / 15))
            draw.text((col_x + 12, y + 15), _clip_text(value, max_chars), fill=ink if col_x == x else muted, font=font)
            draw.line((col_x, y, col_x, y + row_h), fill=border, width=1)
            col_x += col_w
        draw.line((x + table_w, y, x + table_w, y + row_h), fill=border, width=1)
        y += row_h
    return y


def write_markdown_report(result: dict[str, Any], markdown: str) -> Path:
    root = Path(__file__).resolve().parents[3]
    trade_date = str(result.get("trade_date") or datetime.now().strftime("%Y-%m-%d"))
    mode = str(result.get("mode") or "unknown")
    report_dir = root / "outputs" / "lark_reports" / trade_date
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    name = re.sub(r"[^0-9A-Za-z_-]+", "_", f"{stamp}_{mode}")[:80] + ".md"
    path = report_dir / name
    path.write_text(markdown, encoding="utf-8")
    return path


def sync_markdown_to_lark_doc(path: Path, result: dict[str, Any]) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    title = f"{MODEL_TITLES.get(result.get('mode', ''), '选股分析报告')} {result.get('trade_date') or 'latest'}"
    xml_path = path.with_suffix(".doc.xml")
    xml_path.write_text(build_lark_doc_xml_report(result), encoding="utf-8")
    rel_path = xml_path.relative_to(root)
    parent_token = os.environ.get("LARK_REPORT_FOLDER_TOKEN", DEFAULT_LARK_REPORT_FOLDER_TOKEN).strip()
    cmd = [
        "lark-cli",
        "docs",
        "+create",
        "--as",
        os.environ.get("LARK_DOC_CREATE_AS", "user"),
        "--title",
        title,
        "--content",
        f"@{rel_path.as_posix()}",
        "--json",
    ]
    if parent_token:
        cmd.extend(["--parent-token", parent_token])
    proc = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=int(os.environ.get("LARK_DOC_SYNC_TIMEOUT_SEC", "60")))
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "").strip()[-800:] or f"lark-cli exited {proc.returncode}")
    data = json.loads(proc.stdout)
    document = ((data.get("data") or {}).get("document") or {})
    return {
        "title": title,
        "url": document.get("url"),
        "document_id": document.get("document_id"),
        "xml_path": str(xml_path),
        "raw": data,
    }


def _format_group_reply(result: dict[str, Any], doc: dict[str, Any]) -> str:
    picks = result.get("picks") or []
    lines = [
        f"已生成飞书文档：{doc.get('title') or MODEL_TITLES.get(result.get('mode', ''), '选股分析报告')}",
        f"选股日期: {result.get('trade_date') or 'latest'}",
        f"入选: {len(picks)} 只",
        f"文档: {doc.get('url') or '-'}",
    ]
    if picks:
        lines.append("摘要:")
        for i, p in enumerate(picks[:5], 1):
            if result.get("mode") in CB_AUCTION_MODES:
                lines.append(
                    f"{i}. {p.get('code')} {p.get('name')}"
                    f" | 正股 {p.get('stk_code') or '-'} {p.get('stk_name') or '-'}"
                    f" | 质量档 {p.get('quality_tier') or '-'}"
                    f" | 题材分 {_fmt_score(p.get('theme_score') or p.get('score'))}"
                )
            else:
                lines.append(
                    f"{i}. {p.get('code')} {p.get('name')} | 现价 {_fmt_price(_pick_price(p))}"
                    f" | 涨幅 {_fmt_pct(_pick_gain(p))} | 评分 {_fmt_score(p.get('total_score') or p.get('score'))}"
                )
    else:
        if result.get("mode") in CB_AUCTION_MODES:
            observation_count = len(result.get("observation_picks") or [])
            lines.append(result.get("no_result_reason") or "本次没有转债通过主买门槛。")
            if observation_count:
                lines.append(f"观察池: {observation_count} 只，详见文档。")
        else:
            lines.append("本次没有股票通过模型门槛。")
    return "\n".join(lines)


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


def send_text_to_chat(chat_id: str, text: str) -> dict[str, Any]:
    token = get_tenant_access_token()
    body = json.dumps(
        {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
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
        raise RuntimeError(f"send message failed: {exc.code} {detail}") from exc
    if data.get("code") != 0:
        raise RuntimeError(f"send message failed: {data}")
    return data


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


def handle_lark_message(payload: dict[str, Any]) -> dict[str, Any]:
    msg = extract_text_message(payload)
    chat_id = msg["chat_id"]
    sender_open_id = msg["sender_open_id"]
    if not is_allowed_event(chat_id, sender_open_id):
        return {"ignored": True, "reason": "not_allowed"}
    if msg["message_type"] and msg["message_type"] not in {"text", "post"}:
        return {"ignored": True, "reason": "unsupported_message_type"}

    command = parse_command(msg["text"])
    if not command:
        return {"ignored": True, "reason": "unknown_command"}

    send_text_to_chat(chat_id, f"收到指令 {command.command}，先更新必要数据，再运行模型。")
    refresh = refresh_before_run(command)
    result = run_command(command)
    result["data_refresh"] = refresh
    markdown = build_markdown_report(result)
    report_path = write_markdown_report(result, markdown)
    try:
        doc = sync_markdown_to_lark_doc(report_path, result)
        send_text_to_chat(chat_id, _format_group_reply(result, doc))
        try:
            poster_path = generate_poster_image(result)
            if poster_path:
                send_image_to_chat(chat_id, poster_path)
        except Exception as image_exc:
            send_text_to_chat(chat_id, f"海报图片发送失败，飞书文档已生成。\n错误: {image_exc}")
    except Exception as exc:
        send_text_to_chat(chat_id, f"报告已生成，但同步飞书文档失败。\n错误: {exc}")
        raise
    return {
        "ignored": False,
        "mode": command.mode,
        "total_picks": result.get("total_picks"),
        "markdown_path": str(report_path),
        "doc_xml_path": doc.get("xml_path"),
        "doc_url": doc.get("url"),
    }
