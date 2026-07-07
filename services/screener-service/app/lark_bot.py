"""Feishu/Lark group bot integration for screener commands.

This module intentionally keeps the bot surface narrow: fixed model runners,
fixed chat/user allowlists, mention-gated natural language routing, and no
shell execution from group text.
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
    "supply_chain": "产业链预期差选股模型分析报告",
    "bi_trend_launch": "毕师傅硬核科技趋势启动选股分析报告",
    "cb_auction_t0": "竞价 T+0 选债 V1 分析报告",
    "cb_auction_t0_v2": "竞价 T+0 选债 V2 分析报告",
    "cb_auction_t0_v2_1": "竞价 T+0 选债 V2.1 稳健版分析报告",
    "general_qa": "AI 投研问答报告",
}
CB_AUCTION_MODES = {"cb_auction_t0", "cb_auction_t0_v2", "cb_auction_t0_v2_1"}
DEFAULT_LARK_REPORT_FOLDER_TOKEN = "GDlmf7ZIKltfRIdrGn7cyPKJnCg"


@dataclass(frozen=True)
class LarkCommand:
    command: str
    mode: str
    top_n: int = 20
    trade_date: str | None = None


INVESTMENT_INTENTS = {
    "general_qa",
    "model_run",
    "single_stock_model_analysis",
    "stock_research",
    "sector_resonance",
    "bond_research",
    "supply_chain_verification",
    "report_request",
}


MODEL_HINT_TO_MODE = {
    "leader_intraday": "leader_intraday",
    "leader_afternoon": "leader_afternoon",
    "leader_closing": "leader_closing",
    "supply_chain": "supply_chain",
    "bi_trend_launch": "bi_trend_launch",
    "cb_auction_t0_v2_1": "cb_auction_t0_v2_1",
    "秋神盘中": "leader_intraday",
    "秋神午后": "leader_afternoon",
    "秋神尾盘": "leader_closing",
    "大葱产业链": "supply_chain",
    "大葱": "supply_chain",
    "产业链": "supply_chain",
    "产业链预期差": "supply_chain",
    "毕师傅": "bi_trend_launch",
    "硬核科技": "bi_trend_launch",
    "趋势启动": "bi_trend_launch",
    "竞价选债": "cb_auction_t0_v2_1",
    "t+0选债": "cb_auction_t0_v2_1",
}

SINGLE_STOCK_DIAGNOSTIC_TOOL_BY_MODE = {
    "bi_trend_launch": "bi_single_stock_diagnostic",
    "leader_afternoon": "leader_single_stock_diagnostic",
    "leader_intraday": "leader_single_stock_diagnostic",
    "leader_closing": "leader_single_stock_diagnostic",
    "supply_chain": "supply_chain_single_stock_diagnostic",
}


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


def bot_is_mentioned(text: str) -> bool:
    """Group bot only responds when explicitly mentioned."""
    if os.environ.get("LARK_REQUIRE_MENTION", "1").strip().lower() in {"0", "false", "no"}:
        return True
    return "@" in (text or "")


def _strip_bot_mentions(text: str) -> str:
    text = (text or "").strip()
    # Feishu/lark-cli renders mentions as visible @name text in our local bridge.
    return re.sub(r"@\S+(?:\s+)?", "", text).strip()


def _parse_trade_date_and_top(text: str) -> tuple[str | None, int]:
    trade_date = None
    top_n = 20
    for match in re.finditer(r"(?:date=)?(20\d{2}-\d{2}-\d{2})", text):
        trade_date = match.group(1)
    top_match = re.search(r"(?:top|Top|TOP)\s*[=:]?\s*(\d{1,2})", text)
    if top_match:
        top_n = max(5, min(30, int(top_match.group(1))))
    return trade_date, top_n


def _looks_like_research_analysis(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "").lower()
    analysis_terms = [
        "分析",
        "怎么看",
        "评价",
        "判断",
        "解读",
        "指标",
        "逻辑",
        "原因",
        "是不是",
        "是否",
        "这只股票",
        "这只股",
        "个股",
        "单股",
        "吹票",
        "夸大",
    ]
    return any(term.lower() in compact for term in analysis_terms)


def _looks_like_model_run_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "").lower()
    if text.strip().startswith("/"):
        return True
    run_terms = [
        "跑",
        "运行",
        "执行",
        "触发",
        "生成清单",
        "选股清单",
        "选债清单",
        "列出",
        "top",
        "top10",
        "top5",
    ]
    return any(term.lower() in compact for term in run_terms)


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
    if head in {"/大葱产业链", "/产业链", "/大葱", "/产业链预期差", "/产业链预期差选股"}:
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


def parse_message_command(text: str) -> LarkCommand | None:
    """Parse fixed slash commands and common natural-language model requests."""
    command = parse_command(text)
    if command:
        return command

    raw = _strip_bot_mentions(text)
    if not raw:
        return None
    if _looks_like_research_analysis(raw) and not _looks_like_model_run_request(raw):
        return None
    trade_date, top_n = _parse_trade_date_and_top(raw)
    compact = re.sub(r"\s+", "", raw)

    if ("竞价" in compact and ("选债" in compact or "转债" in compact or "T+0" in raw or "T0" in compact)):
        return LarkCommand(command=raw[:40], mode="cb_auction_t0_v2_1", top_n=top_n, trade_date=trade_date)
    if "秋神" in compact and ("盘中" in compact or "早盘" in compact):
        return LarkCommand(command=raw[:40], mode="leader_intraday", top_n=top_n, trade_date=trade_date)
    if "秋神" in compact and ("尾盘" in compact or "收盘" in compact):
        return LarkCommand(command=raw[:40], mode="leader_closing", top_n=top_n, trade_date=trade_date)
    if "秋神" in compact and ("午后" in compact or "下午" in compact or "选股" in compact):
        return LarkCommand(command=raw[:40], mode="leader_afternoon", top_n=top_n, trade_date=trade_date)
    if "午后选股" in compact:
        return LarkCommand(command=raw[:40], mode="leader_afternoon", top_n=top_n, trade_date=trade_date)
    if "大葱" in compact or "产业链" in compact:
        return LarkCommand(command=raw[:40], mode="supply_chain", top_n=top_n, trade_date=trade_date)
    if "毕师傅" in compact or "硬核科技" in compact or "趋势启动" in compact:
        return LarkCommand(command=raw[:40], mode="bi_trend_launch", top_n=top_n, trade_date=trade_date)
    return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    candidates = [raw]
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "是", "需要"}
    return bool(value)


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，、\s]+", value) if item.strip()]
    return [str(value).strip()]


def _infer_stock_from_question(question: str) -> dict[str, Any] | None:
    """Infer a target stock from the raw question without relying on LLM extraction."""
    raw = _strip_bot_mentions(question)
    code_match = re.search(r"(?<!\d)(\d{6})(?!\d)", raw)
    code = code_match.group(1) if code_match else ""
    try:
        from app.routers.screener import _get_factor_db

        with _get_factor_db() as db:
            if code:
                row = db.execute("SELECT code, name, industry FROM stocks WHERE code=? LIMIT 1", (code,)).fetchone()
                if row:
                    return {"code": str(row.get("code") or code), "name": row.get("name"), "industry": row.get("industry")}
            row = db.execute(
                """
                SELECT code, name, industry
                FROM stocks
                WHERE ? LIKE '%' || name || '%'
                ORDER BY LENGTH(name) DESC
                LIMIT 1
                """,
                (raw,),
            ).fetchone()
            if row:
                return {"code": str(row.get("code")), "name": row.get("name"), "industry": row.get("industry")}
    except Exception:
        if code:
            return {"code": code, "name": ""}
    return {"code": code, "name": ""} if code else None


def _normalize_intent_plan(plan: dict[str, Any], question: str) -> dict[str, Any]:
    intent = str(plan.get("intent") or "").strip() or "general_qa"
    if intent not in INVESTMENT_INTENTS:
        intent = "stock_research" if _coerce_bool(plan.get("is_investment_related")) else "general_qa"
    trade_date, top_n = _parse_trade_date_and_top(question)
    inferred_stock = _infer_stock_from_question(question)
    normalized = {
        "intent": intent,
        "is_investment_related": _coerce_bool(plan.get("is_investment_related")) or intent != "general_qa",
        "needs_report": _coerce_bool(plan.get("needs_report")),
        "target_stock": str(plan.get("target_stock") or plan.get("target_stock_name") or (inferred_stock or {}).get("name") or "").strip(),
        "stock_code": str(plan.get("stock_code") or (inferred_stock or {}).get("code") or "").strip(),
        "model_hints": _coerce_list(plan.get("model_hints") or plan.get("model_hint")),
        "requested_tools": _coerce_list(plan.get("requested_tools")),
        "top_n": max(5, min(30, int(plan.get("top_n") or top_n or 10))),
        "trade_date": str(plan.get("trade_date") or trade_date or "").strip() or None,
        "answer_mode": str(plan.get("answer_mode") or "stream").strip() or "stream",
        "reason": str(plan.get("reason") or "").strip(),
        "source": str(plan.get("source") or "llm").strip(),
    }
    if (
        normalized["is_investment_related"]
        and not normalized["needs_report"]
        and normalized["intent"] in {"stock_research", "general_qa"}
        and (normalized["target_stock"] or normalized["stock_code"])
        and (_looks_like_research_analysis(question) or normalized["model_hints"])
    ):
        normalized["intent"] = "single_stock_model_analysis"
    if normalized["needs_report"] and normalized["intent"] in {"stock_research", "single_stock_model_analysis", "sector_resonance", "bond_research"}:
        normalized["intent"] = "report_request"
    return normalized


def _fallback_intent_plan(question: str) -> dict[str, Any]:
    raw = _strip_bot_mentions(question)
    compact = re.sub(r"\s+", "", raw or "").lower()
    trade_date, top_n = _parse_trade_date_and_top(raw)
    is_investment = is_investment_question(raw)
    needs_report = _looks_like_model_run_request(raw) or any(k in compact for k in ["报告", "文档", "清单", "top"])
    intent = "general_qa"
    if is_investment:
        if any(k in compact for k in ["转债", "选债", "可转债"]):
            intent = "model_run" if needs_report else "bond_research"
        elif _looks_like_research_analysis(raw):
            intent = "single_stock_model_analysis" if any(k in compact for k in ["这只股", "这只股票", "个股", "股票", "指标"]) else "stock_research"
        elif needs_report:
            intent = "model_run"
        elif any(k in compact for k in ["板块", "共振", "题材"]):
            intent = "sector_resonance"
        elif any(k in compact for k in ["吹票", "夸大", "产业链", "大葱"]):
            intent = "supply_chain_verification"
        else:
            intent = "stock_research"
    return _normalize_intent_plan(
        {
            "intent": intent,
            "is_investment_related": is_investment,
            "needs_report": needs_report and intent in {"model_run", "report_request"},
            "model_hints": [hint for hint in MODEL_HINT_TO_MODE if hint.lower() in compact],
            "requested_tools": [],
            "top_n": top_n,
            "trade_date": trade_date,
            "reason": "规则兜底",
            "source": "fallback",
        },
        raw,
    )


def parse_intent_with_llm(question: str) -> dict[str, Any]:
    """Use LLM for semantic intent parsing; fall back to deterministic rules."""
    raw = _strip_bot_mentions(question)
    if os.environ.get("LARK_LLM_INTENT_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return _fallback_intent_plan(raw)
    prompt = (
        "你是投研机器人入口的意图解析器，只能输出一个 JSON 对象，不能输出解释文字。\n"
        "允许的 intent: general_qa, model_run, single_stock_model_analysis, stock_research, "
        "sector_resonance, bond_research, supply_chain_verification, report_request。\n"
        "字段：intent, is_investment_related, needs_report, target_stock, stock_code, "
        "model_hints, requested_tools, top_n, trade_date, answer_mode, reason。\n"
        "判断规则：\n"
        "- 用户明确要求跑模型/选股清单/选债清单/top/生成报告，才 needs_report=true 或 intent=model_run/report_request。\n"
        "- 用户说用某模型指标分析某只股票，属于 single_stock_model_analysis，不是 model_run。\n"
        "- 股票、转债、板块、财报、公告、产业链、吹票核验都属于投研相关。\n"
        "- 不确定股票代码时 stock_code 留空，不要编造。\n\n"
        f"用户问题：{raw}"
    )
    parsed = _extract_json_object(ask_llm(prompt))
    if not parsed:
        return _fallback_intent_plan(raw)
    parsed["source"] = "llm"
    return _normalize_intent_plan(parsed, raw)


def is_investment_question(text: str) -> bool:
    compact = re.sub(r"\s+", "", _strip_bot_mentions(text) or "").lower()
    if re.search(r"\b(?:[0-9]{6}|[shszbj][0-9]{6}|[0-9]{6}\\.(?:sh|sz|bj))\b", compact):
        return True
    keywords = [
        "股票",
        "选股",
        "个股",
        "正股",
        "转债",
        "选债",
        "行情",
        "涨幅",
        "跌幅",
        "涨停",
        "跌停",
        "板块",
        "概念",
        "题材",
        "共振",
        "产业链",
        "大葱",
        "毕师傅",
        "秋神",
        "硬核科技",
        "趋势启动",
        "午后",
        "盘中",
        "尾盘",
        "竞价",
        "目标价",
        "止损",
        "买入",
        "卖出",
        "财报",
        "公告",
        "业绩预告",
        "上市公司",
        "吹票",
        "夸大",
        "具身智能",
        "机器人",
        "半导体",
        "算力",
        "光模块",
        "券商",
        "小金属",
        "商业航天",
    ]
    return any(keyword.lower() in compact for keyword in keywords)


def _research_modes_for_question(question: str) -> list[str]:
    compact = re.sub(r"\s+", "", _strip_bot_mentions(question) or "").lower()
    modes: list[str] = []
    if any(k in compact for k in ["转债", "选债", "可转债", "t+0", "t0"]):
        modes.append("cb_auction_t0_v2_1")
    if any(k in compact for k in ["大葱", "产业链", "吹票", "夸大", "证据", "逻辑"]):
        modes.append("supply_chain")
    if any(k in compact for k in ["毕师傅", "硬核科技", "趋势启动", "半导体", "算力", "光模块"]):
        modes.append("bi_trend_launch")
    if any(k in compact for k in ["秋神", "午后", "盘中", "尾盘", "板块", "共振", "题材", "具身智能", "机器人"]):
        modes.append("leader_afternoon")
    if not modes and is_investment_question(question):
        modes.extend(["leader_afternoon", "bi_trend_launch"])

    deduped: list[str] = []
    for mode in modes:
        if mode not in deduped:
            deduped.append(mode)
    max_runs = max(1, min(4, int(os.environ.get("LARK_RESEARCH_QA_MAX_MODE_RUNS", "2"))))
    return deduped[:max_runs]


def _modes_from_intent(intent_plan: dict[str, Any], question: str) -> list[str]:
    modes: list[str] = []
    for hint in _coerce_list(intent_plan.get("model_hints")):
        normalized = MODEL_HINT_TO_MODE.get(hint) or MODEL_HINT_TO_MODE.get(hint.lower())
        if normalized:
            modes.append(normalized)
    for tool in _coerce_list(intent_plan.get("requested_tools")):
        normalized = MODEL_HINT_TO_MODE.get(tool) or MODEL_HINT_TO_MODE.get(tool.lower())
        if normalized:
            modes.append(normalized)
    intent = intent_plan.get("intent")
    if intent == "bond_research":
        modes.append("cb_auction_t0_v2_1")
    elif intent == "supply_chain_verification":
        modes.append("supply_chain")
    elif intent == "sector_resonance":
        modes.append("leader_afternoon")
    elif intent == "single_stock_model_analysis" and not modes:
        modes.extend(_research_modes_for_question(question))
    elif intent in {"stock_research", "model_run", "report_request"} and not modes:
        modes.extend(_research_modes_for_question(question))
    if not modes:
        modes.extend(_research_modes_for_question(question))

    deduped: list[str] = []
    for mode in modes:
        if mode in {
            "leader_intraday",
            "leader_afternoon",
            "leader_closing",
            "supply_chain",
            "bi_trend_launch",
            "cb_auction_t0_v2_1",
        } and mode not in deduped:
            deduped.append(mode)
    max_runs = max(1, min(4, int(os.environ.get("LARK_RESEARCH_QA_MAX_MODE_RUNS", "2"))))
    return deduped[:max_runs]


def build_tool_plan(intent_plan: dict[str, Any], question: str) -> list[dict[str, Any]]:
    """Translate a normalized intent into whitelisted project tool calls."""
    tools = []
    modes = _modes_from_intent(intent_plan, question)
    if intent_plan.get("intent") == "single_stock_model_analysis":
        for mode in modes:
            diagnostic_tool = SINGLE_STOCK_DIAGNOSTIC_TOOL_BY_MODE.get(mode)
            if diagnostic_tool:
                tools.append(
                    {
                        "tool": diagnostic_tool,
                        "mode": mode,
                        "target_stock": intent_plan.get("target_stock"),
                        "stock_code": intent_plan.get("stock_code"),
                        "trade_date": intent_plan.get("trade_date"),
                    }
                )
    for mode in modes:
        tools.append(
            {
                "tool": "model_run",
                "mode": mode,
                "top_n": int(intent_plan.get("top_n") or 10),
                "trade_date": intent_plan.get("trade_date"),
            }
        )
    return tools


def _target_stock_tokens(intent_plan: dict[str, Any]) -> list[str]:
    tokens = []
    for value in [intent_plan.get("target_stock"), intent_plan.get("stock_code")]:
        if value:
            tokens.append(str(value).strip().lower())
    return [token for token in tokens if token]


def _pick_matches_target(pick: dict[str, Any], target_tokens: list[str]) -> bool:
    if not target_tokens:
        return False
    values = [
        pick.get("code"),
        pick.get("name"),
        pick.get("stk_code"),
        pick.get("stk_name"),
        pick.get("cb_code"),
        pick.get("cb_name"),
    ]
    normalized_values = [str(value).strip().lower() for value in values if value not in (None, "")]
    return any(token and any(token in value or value in token for value in normalized_values) for token in target_tokens)


def _resolve_stock_identity(target_stock: str | None, stock_code: str | None) -> dict[str, Any] | None:
    code = re.sub(r"\D", "", str(stock_code or ""))[:6]
    target = str(target_stock or "").strip()
    if not code and not target:
        return None
    try:
        from app.routers.screener import _get_factor_db

        with _get_factor_db() as db:
            if code:
                row = db.execute("SELECT code, name, industry FROM stocks WHERE code=?", (code,)).fetchone()
                if row:
                    return {"code": str(row.get("code") or code), "name": row.get("name") or target, "industry": row.get("industry")}
            if target:
                row = db.execute(
                    "SELECT code, name, industry FROM stocks WHERE name=? OR name LIKE ? ORDER BY code LIMIT 1",
                    (target, f"%{target}%"),
                ).fetchone()
                if row:
                    return {"code": str(row.get("code")), "name": row.get("name"), "industry": row.get("industry")}
    except Exception as exc:
        return {"code": code, "name": target, "error": str(exc)[-300:]}
    return {"code": code, "name": target} if code or target else None


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _calc_adx(rows: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(rows) < period + 1:
        return None
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    tr_list: list[float] = []
    for i in range(1, len(rows)):
        high = float(rows[i].get("high") or 0)
        low = float(rows[i].get("low") or 0)
        close_prev = float(rows[i - 1].get("close") or 0)
        high_prev = float(rows[i - 1].get("high") or 0)
        low_prev = float(rows[i - 1].get("low") or 0)
        up_move = high - high_prev
        down_move = low_prev - low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        tr_list.append(max(high - low, abs(high - close_prev), abs(low - close_prev)))

    dx_values: list[float] = []
    for i in range(period - 1, len(tr_list)):
        tr_sum = sum(tr_list[i - period + 1 : i + 1])
        if tr_sum <= 0:
            continue
        plus_di = 100 * sum(plus_dm[i - period + 1 : i + 1]) / tr_sum
        minus_di = 100 * sum(minus_dm[i - period + 1 : i + 1]) / tr_sum
        denom = plus_di + minus_di
        if denom > 0:
            dx_values.append(100 * abs(plus_di - minus_di) / denom)
    recent = dx_values[-period:]
    return round(sum(recent) / len(recent), 2) if recent else None


def _fetch_stock_daily_rows(code: str, trade_date: str | None, limit: int = 60) -> tuple[list[dict[str, Any]], str | None]:
    from app.routers.screener import _get_factor_db, _resolve_trade_date

    resolved_date = _resolve_trade_date(trade_date)
    with _get_factor_db() as db:
        rows = db.execute(
            """
            SELECT trade_date, open, high, low, close, volume, amount
            FROM daily_kline
            WHERE code=? AND trade_date <= ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (code, resolved_date, limit),
        ).fetchall()
    return list(reversed([dict(row) for row in rows])), resolved_date


def _latest_stock_profile(code: str) -> dict[str, Any] | None:
    try:
        from app.routers.screener import _get_factor_db

        with _get_factor_db() as db:
            row = db.execute(
                """
                SELECT code, full_name, main_business, business_scope, introduction, employees, updated_at
                FROM stock_profiles
                WHERE code=?
                """,
                (code,),
            ).fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def _latest_financial_indicator(code: str) -> dict[str, Any] | None:
    try:
        from app.routers.screener import _get_factor_db

        with _get_factor_db() as db:
            row = db.execute(
                """
                SELECT code, end_date, roe, gross_margin, net_margin, revenue_growth, profit_growth
                FROM financial_indicator
                WHERE code=?
                ORDER BY end_date DESC
                LIMIT 1
                """,
                (code,),
            ).fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def _latest_financial_income(code: str) -> dict[str, Any] | None:
    try:
        from app.routers.screener import _get_factor_db

        with _get_factor_db() as db:
            row = db.execute(
                """
                SELECT code, end_date, total_revenue, net_profit_parent
                FROM financial_income
                WHERE code=?
                ORDER BY end_date DESC
                LIMIT 1
                """,
                (code,),
            ).fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def _stock_chain_mapping(code: str) -> list[dict[str, Any]]:
    try:
        from app.routers.screener import _get_factor_db

        with _get_factor_db() as db:
            rows = db.execute(
                """
                SELECT code, node_id, main_pct, policy_match_score, chokepoint_score, evidence, three_factors, trade_signal
                FROM company_chain_mapping
                WHERE code=?
                ORDER BY policy_match_score DESC NULLS LAST, chokepoint_score DESC NULLS LAST
                LIMIT 8
                """,
                (code,),
            ).fetchall()
            return [dict(row) for row in rows]
    except Exception:
        return []


def _stock_supply_chain_score(code: str, trade_date: str | None) -> dict[str, Any] | None:
    try:
        from app.routers.screener import _get_factor_db, _resolve_trade_date

        resolved_date = _resolve_trade_date(trade_date)
        with _get_factor_db() as db:
            row = db.execute(
                """
                SELECT code, trade_date, node_id, total_score, rating, trade_signal, dimension_scores, evidence_ids
                FROM supply_chain_scores
                WHERE code=? AND trade_date <= ?
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (code, resolved_date),
            ).fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def _text_contains_any(text: str, words: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(word.lower() in lowered for word in words)


def _sane_pct(value: Any, max_abs: float = 500.0) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if abs(number) <= max_abs else None


def _display_chain_node(node_id: Any) -> str:
    node = str(node_id or "").strip()
    mapping = {
        "semiconductor_design": "半导体设计",
        "tao_law_advanced_packaging_先进封测": "先进封测",
        "ai_compute_hardware": "AI算力硬件",
        "chain_eda_industrial_software": "EDA/工业软件",
        "chain_huawei_devices": "华为终端链",
        "chain_memory_chips": "存储芯片",
    }
    if node in mapping:
        return mapping[node]
    return node.replace("chain_", "").replace("_", "/")


def _build_hardtech_h1_h6_rubric(
    identity: dict[str, Any],
    profile: dict[str, Any] | None,
    financial: dict[str, Any] | None,
    income: dict[str, Any] | None,
    chain_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    profile_text = " ".join(
        str((profile or {}).get(key) or "")
        for key in ("main_business", "business_scope", "introduction")
    )
    chain_ids = [str(row.get("node_id") or "") for row in chain_rows]
    evidence_gaps = []
    for row in chain_rows:
        evidence = row.get("evidence")
        if isinstance(evidence, dict):
            evidence_gaps.extend(evidence.get("evidence_gaps") or [])
    industry = str(identity.get("industry") or "")
    gross_margin = float(financial.get("gross_margin")) if financial and financial.get("gross_margin") is not None else None
    roe = float(financial.get("roe")) if financial and financial.get("roe") is not None else None
    revenue_growth = _sane_pct(financial.get("revenue_growth")) if financial else None
    profit_growth = _sane_pct(financial.get("profit_growth")) if financial else None

    h1_keywords = ["mosfet", "igbt", "功率器件", "芯片", "半导体", "国产替代", "集成电路"]
    h1_score = 7.0 if industry == "半导体" and _text_contains_any(profile_text, h1_keywords) else 4.0
    if not any("chokepoint" in cid or "semiconductor" in cid for cid in chain_ids):
        h1_score -= 1.0

    h2_score = 3.0
    if gross_margin is not None:
        h2_score += 3.0 if gross_margin >= 40 else 2.0 if gross_margin >= 25 else 1.0
    if _text_contains_any(profile_text, ["研发", "设计", "技术", "专利", "平台"]):
        h2_score += 1.0

    h3_score = 4.0 if industry == "半导体" else 2.0
    if _text_contains_any(profile_text, ["龙头", "领先", "少数", "全球"]):
        h3_score += 1.0

    h4_score = 3.0
    if chain_rows:
        h4_score += 1.5
    if evidence_gaps:
        h4_score -= min(1.5, len(evidence_gaps) * 0.3)
    if _text_contains_any(profile_text, ["量产", "销售", "客户", "应用"]):
        h4_score += 1.0

    h5_score = 0.0
    h5_pieces = []
    if revenue_growth is not None:
        h5_score += 2.0 if revenue_growth >= 20 else 1.0 if revenue_growth >= 0 else 0.0
        h5_pieces.append(f"营收增速 {revenue_growth:.1f}%")
    if roe is not None:
        h5_score += 2.0 if roe >= 10 else 1.0 if roe > 0 else 0.0
        h5_pieces.append(f"ROE {roe:.1f}%")
    if profit_growth is not None:
        h5_score += 2.0 if profit_growth >= 20 else 1.0 if profit_growth >= 0 else 0.0
        h5_pieces.append(f"利润增速 {profit_growth:.1f}%")
    if not h5_pieces and income and income.get("total_revenue") is not None:
        h5_score += 1.0
        h5_pieces.append(f"营收 {float(income['total_revenue']) / 100000000:.1f}亿")

    policy_scores = [float(row.get("policy_match_score")) for row in chain_rows if row.get("policy_match_score") is not None]
    h6_score = max(policy_scores) * 5 if policy_scores else 0.0

    rows = [
        ("H1 卡脖子紧迫度", h1_score, 10, f"行业 {industry or '-'}；链路 {'、'.join(_display_chain_node(item) for item in chain_ids[:3]) or '-'}；关键字来自主营/简介"),
        ("H2 真硬核纯度", h2_score, 10, f"毛利率 {gross_margin:.1f}%" if gross_margin is not None else "缺少最新毛利率；使用主营技术描述降级判断"),
        ("H3 稀缺性", h3_score, 8, "半导体赛道拥挤，需结合细分壁垒与份额验证" if industry == "半导体" else "非半导体硬科技，稀缺性需另证"),
        ("H4 产业阶段", h4_score, 7, f"项目链映射 {len(chain_rows)} 条；证据缺口 {len(evidence_gaps)} 项"),
        ("H5 业绩验证", h5_score, 10, "；".join(h5_pieces) if h5_pieces else "缺少可用财务指标"),
        ("H6 政策共振", h6_score, 5, f"最高政策匹配 {max(policy_scores):.2f}" if policy_scores else "项目链路未给出政策匹配"),
    ]
    return [
        {"dimension": name, "score": round(max(0.0, min(score, full)), 1), "full_score": full, "key_data": data}
        for name, score, full, data in rows
    ]


def build_bi_single_stock_diagnostic(intent_plan: dict[str, Any]) -> dict[str, Any] | None:
    identity = _resolve_stock_identity(intent_plan.get("target_stock"), intent_plan.get("stock_code"))
    if not identity or not identity.get("code"):
        return None
    code = str(identity.get("code"))
    try:
        ordered, _ = _fetch_stock_daily_rows(code, intent_plan.get("trade_date"), 60)
    except Exception as exc:
        return {"tool": "bi_single_stock_diagnostic", "status": "error", "stock": identity, "message": str(exc)[-500:]}

    if len(ordered) < 20:
        return {"tool": "bi_single_stock_diagnostic", "status": "insufficient_data", "stock": identity, "bar_count": len(ordered)}

    latest = ordered[-1]
    prev = ordered[-2] if len(ordered) >= 2 else {}
    closes = [float(row.get("close") or 0) for row in ordered if row.get("close") is not None]
    volumes = [float(row.get("volume") or 0) for row in ordered if row.get("volume") is not None]
    ma5 = _avg(closes[-5:])
    ma10 = _avg(closes[-10:])
    ma20 = _avg(closes[-20:])
    close = float(latest.get("close") or 0)
    prev_close = float(prev.get("close") or 0)
    pct_chg = ((close / prev_close - 1) * 100) if prev_close > 0 else None
    recent_changes = []
    for i in range(max(1, len(ordered) - 5), len(ordered)):
        p = float(ordered[i - 1].get("close") or 0)
        c = float(ordered[i].get("close") or 0)
        if p > 0:
            recent_changes.append((c / p - 1) * 100)
    max_single_drop_5d = min(recent_changes) if recent_changes else None
    avg_vol5_prev = _avg(volumes[-6:-1])
    volume_ratio_5d = (float(latest.get("volume") or 0) / avg_vol5_prev) if avg_vol5_prev and avg_vol5_prev > 0 else None
    obv = 0.0
    for i in range(1, len(ordered)):
        c = float(ordered[i].get("close") or 0)
        p = float(ordered[i - 1].get("close") or 0)
        vol = float(ordered[i].get("volume") or 0)
        if c > p:
            obv += vol
        elif c < p:
            obv -= vol
    adx = _calc_adx(ordered)

    gates = [
        {"gate": "硬科技行业门控", "passed": identity.get("industry") in {"半导体", "电子", "通信设备", "计算机设备", "计算机应用"}, "value": identity.get("industry") or "-", "note": "半导体/电子/通信/计算机等硬科技行业更匹配"},
        {"gate": "收盘价站上 MA5", "passed": bool(ma5 and close >= ma5), "value": round(ma5, 2) if ma5 else None, "note": "趋势启动要求短线重新站上均线"},
        {"gate": "收盘价站上 MA10", "passed": bool(ma10 and close >= ma10), "value": round(ma10, 2) if ma10 else None, "note": "未站上代表修复不足"},
        {"gate": "OBV 不为负", "passed": obv >= 0, "value": round(obv, 2), "note": "资金趋势不应明显为负"},
        {"gate": "ADX >= 25", "passed": bool(adx is not None and adx >= 25), "value": adx, "note": "趋势强度门槛"},
        {"gate": "弱市 5 日内不能有单日跌幅超过 8%", "passed": bool(max_single_drop_5d is None or max_single_drop_5d > -8), "value": f"{max_single_drop_5d:.2f}%" if max_single_drop_5d is not None else "-", "note": "触发接飞刀过滤则不入买入池"},
    ]
    failed = [gate for gate in gates if not gate["passed"]]
    profile = _latest_stock_profile(code)
    financial = _latest_financial_indicator(code)
    income = _latest_financial_income(code)
    chain_rows = _stock_chain_mapping(code)
    rubric = _build_hardtech_h1_h6_rubric(identity, profile, financial, income, chain_rows)
    return {
        "tool": "bi_single_stock_diagnostic",
        "model": "bi_trend_launch",
        "diagnostic_style": "毕师傅硬核科技 H1-H6 + 趋势启动门槛",
        "status": "ok",
        "stock": identity,
        "trade_date": str(latest.get("trade_date"))[:10],
        "data_source": "daily_kline",
        "metrics": {
            "close": close,
            "pct_chg": round(pct_chg, 2) if pct_chg is not None else None,
            "ma5": round(ma5, 2) if ma5 else None,
            "ma10": round(ma10, 2) if ma10 else None,
            "ma20": round(ma20, 2) if ma20 else None,
            "volume_ratio_5d": round(volume_ratio_5d, 2) if volume_ratio_5d is not None else None,
            "obv": round(obv, 2),
            "adx": adx,
            "max_single_drop_5d": round(max_single_drop_5d, 2) if max_single_drop_5d is not None else None,
        },
        "gates": gates,
        "failed_gates": failed,
        "rubric": rubric,
        "rubric_total_score": round(sum(float(row["score"]) for row in rubric), 1),
        "rubric_full_score": sum(int(row["full_score"]) for row in rubric),
        "fundamental_context": {
            "profile_updated_at": (profile or {}).get("updated_at"),
            "main_business": (profile or {}).get("main_business"),
            "financial_end_date": (financial or {}).get("end_date"),
            "income_end_date": (income or {}).get("end_date"),
            "chain_nodes": [row.get("node_id") for row in chain_rows[:6]],
        },
        "model_verdict": "pass" if not failed else "fail",
    }


def build_leader_single_stock_diagnostic(intent_plan: dict[str, Any]) -> dict[str, Any] | None:
    identity = _resolve_stock_identity(intent_plan.get("target_stock"), intent_plan.get("stock_code"))
    if not identity or not identity.get("code"):
        return None
    code = str(identity.get("code"))
    try:
        ordered, _ = _fetch_stock_daily_rows(code, intent_plan.get("trade_date"), 30)
    except Exception as exc:
        return {"tool": "leader_single_stock_diagnostic", "status": "error", "stock": identity, "message": str(exc)[-500:]}
    if len(ordered) < 10:
        return {"tool": "leader_single_stock_diagnostic", "status": "insufficient_data", "stock": identity, "bar_count": len(ordered)}

    latest = ordered[-1]
    prev = ordered[-2]
    close = float(latest.get("close") or 0)
    prev_close = float(prev.get("close") or 0)
    pct_chg = ((close / prev_close - 1) * 100) if prev_close > 0 else None
    amount = float(latest.get("amount") or 0)
    volumes = [float(row.get("volume") or 0) for row in ordered if row.get("volume") is not None]
    closes = [float(row.get("close") or 0) for row in ordered if row.get("close") is not None]
    ma5 = _avg(closes[-5:])
    ma10 = _avg(closes[-10:])
    avg_vol5_prev = _avg(volumes[-6:-1])
    volume_ratio = (float(latest.get("volume") or 0) / avg_vol5_prev) if avg_vol5_prev and avg_vol5_prev > 0 else None
    gates = [
        {"gate": "涨幅强度", "passed": bool(pct_chg is not None and pct_chg >= 3), "value": f"{pct_chg:.2f}%" if pct_chg is not None else "-", "note": "秋神午后更偏龙头/强势确认，弱涨幅通常不优先"},
        {"gate": "成交活跃", "passed": amount >= 300000000, "value": f"{amount / 100000000:.2f}亿", "note": "成交额过低时承接质量不足"},
        {"gate": "量能确认", "passed": bool(volume_ratio is not None and volume_ratio >= 1.0), "value": round(volume_ratio, 2) if volume_ratio is not None else None, "note": "午后模型更关注放量而非缩量"},
        {"gate": "短线均线", "passed": bool(ma5 and ma10 and close >= ma5 >= ma10), "value": f"close {close:.2f} / MA5 {ma5:.2f} / MA10 {ma10:.2f}" if ma5 and ma10 else "-", "note": "强势股应站上短均线"},
    ]
    failed = [gate for gate in gates if not gate["passed"]]
    return {
        "tool": "leader_single_stock_diagnostic",
        "model": intent_plan.get("model") or "leader_afternoon",
        "diagnostic_style": "秋神龙头/午后模型强度诊断",
        "status": "ok",
        "stock": identity,
        "trade_date": str(latest.get("trade_date"))[:10],
        "data_source": "daily_kline",
        "metrics": {
            "close": close,
            "pct_chg": round(pct_chg, 2) if pct_chg is not None else None,
            "amount_yi": round(amount / 100000000, 2),
            "volume_ratio_5d": round(volume_ratio, 2) if volume_ratio is not None else None,
            "ma5": round(ma5, 2) if ma5 else None,
            "ma10": round(ma10, 2) if ma10 else None,
        },
        "gates": gates,
        "failed_gates": failed,
        "model_verdict": "pass" if not failed else "fail",
    }


def build_supply_chain_single_stock_diagnostic(intent_plan: dict[str, Any]) -> dict[str, Any] | None:
    identity = _resolve_stock_identity(intent_plan.get("target_stock"), intent_plan.get("stock_code"))
    if not identity or not identity.get("code"):
        return None
    code = str(identity.get("code"))
    profile = _latest_stock_profile(code)
    chain_rows = _stock_chain_mapping(code)
    score = _stock_supply_chain_score(code, intent_plan.get("trade_date"))
    profile_text = " ".join(str((profile or {}).get(key) or "") for key in ("main_business", "business_scope", "introduction"))
    dimension_scores = score.get("dimension_scores") if isinstance(score, dict) else None
    gates = [
        {"gate": "产业链映射", "passed": bool(chain_rows), "value": len(chain_rows), "note": "没有映射时只能做弱相关分析"},
        {"gate": "主营业务匹配", "passed": bool(_text_contains_any(profile_text, ["芯片", "半导体", "功率器件", "mosfet", "igbt", "国产替代"])), "value": (profile or {}).get("main_business"), "note": "用主营/简介验证是不是硬贴概念"},
        {"gate": "项目评分记录", "passed": bool(score), "value": score.get("total_score") if score else None, "note": "有 supply_chain_scores 才能引用模型五维评分"},
        {"gate": "证据质量", "passed": bool(chain_rows and any((row.get("evidence") or {}) for row in chain_rows)), "value": [row.get("evidence") for row in chain_rows[:2]], "note": "证据不足时不能把概念当确定产业链地位"},
    ]
    failed = [gate for gate in gates if not gate["passed"]]
    return {
        "tool": "supply_chain_single_stock_diagnostic",
        "model": "supply_chain",
        "diagnostic_style": "产业链预期差五维/证据质量诊断",
        "status": "ok",
        "stock": identity,
        "data_source": "company_chain_mapping + supply_chain_scores + stock_profiles",
        "chain_nodes": [row.get("node_id") for row in chain_rows],
        "mapping_rows": chain_rows[:5],
        "latest_score": score,
        "dimension_scores": dimension_scores,
        "profile": {
            "updated_at": (profile or {}).get("updated_at"),
            "main_business": (profile or {}).get("main_business"),
        },
        "gates": gates,
        "failed_gates": failed,
        "model_verdict": "pass" if chain_rows and not failed else "needs_verification",
    }


SINGLE_STOCK_DIAGNOSTIC_BUILDERS = {
    "bi_single_stock_diagnostic": "build_bi_single_stock_diagnostic",
    "leader_single_stock_diagnostic": "build_leader_single_stock_diagnostic",
    "supply_chain_single_stock_diagnostic": "build_supply_chain_single_stock_diagnostic",
}


def _summarize_model_result_for_llm(result: dict[str, Any]) -> dict[str, Any]:
    picks = result.get("picks") or []
    observation = result.get("observation_picks") or []
    top_picks = []
    for p in picks[:8]:
        top_picks.append(
            {
                "code": p.get("code") or p.get("cb_code"),
                "name": p.get("name") or p.get("cb_name"),
                "price": _fmt_price(_pick_price(p)) if result.get("mode") not in CB_AUCTION_MODES else None,
                "gain": _fmt_pct(_pick_gain(p)) if result.get("mode") not in CB_AUCTION_MODES else None,
                "sector": _first_value(p.get("industry"), p.get("sector"), p.get("chain"), p.get("node_name"), p.get("concept_name"), "-"),
                "score": _fmt_score(p.get("total_score") or p.get("score") or p.get("theme_score")),
                "reason": _cb_reason(p) if result.get("mode") in CB_AUCTION_MODES else _pick_reason(p),
                "stk_code": p.get("stk_code"),
                "stk_name": p.get("stk_name"),
                "quality_tier": p.get("quality_tier"),
            }
        )
    resonance = _cb_resonance_lines(picks, result) if result.get("mode") in CB_AUCTION_MODES else _sector_resonance_lines(picks, result)
    return {
        "mode": result.get("mode"),
        "model_title": MODEL_TITLES.get(str(result.get("mode") or ""), str(result.get("mode") or "")),
        "trade_date": result.get("trade_date"),
        "total_picks": result.get("total_picks", len(picks)),
        "total_observation_picks": result.get("total_observation_picks", len(observation)),
        "no_result_reason": result.get("no_result_reason"),
        "top_picks": top_picks,
        "resonance": resonance[:6],
        "process_summary": result.get("process_summary"),
        "data_refresh": result.get("data_refresh"),
    }


def validate_research_context(intent_plan: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    target_tokens = _target_stock_tokens(intent_plan)
    target_hits = []
    for run in runs:
        for pick in run.get("top_picks") or []:
            if _pick_matches_target(pick, target_tokens):
                target_hits.append(
                    {
                        "mode": run.get("mode"),
                        "model_title": run.get("model_title"),
                        "pick": pick,
                    }
                )
    warnings = []
    if target_tokens and not target_hits:
        warnings.append("目标股票未出现在本次项目模型返回的 Top 结果中，不能直接视为模型支持。")
    if any(run.get("status") == "error" for run in runs):
        warnings.append("部分项目工具调用失败，回答必须标注数据不完整。")
    return {
        "target_stock_checked": bool(target_tokens),
        "target_hits": target_hits,
        "warnings": warnings,
    }


def build_project_research_context(question: str, intent_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect project model/data context for investment-related group questions."""
    intent_plan = intent_plan or _fallback_intent_plan(question)
    tool_plan = build_tool_plan(intent_plan, question)
    runs = []
    diagnostics = []
    for tool in tool_plan:
        diagnostic_builder_name = SINGLE_STOCK_DIAGNOSTIC_BUILDERS.get(str(tool.get("tool") or ""))
        diagnostic_builder = globals().get(diagnostic_builder_name or "")
        if callable(diagnostic_builder):
            diagnostic = diagnostic_builder({**intent_plan, "model": tool.get("mode")})
            if diagnostic:
                diagnostics.append(diagnostic)
            continue
        if tool.get("tool") != "model_run":
            continue
        mode = str(tool.get("mode") or "")
        command = LarkCommand(
            command=f"research_qa:{mode}",
            mode=mode,
            top_n=int(tool.get("top_n") or 10),
            trade_date=tool.get("trade_date"),
        )
        try:
            result = run_command(command)
            runs.append({"status": "ok", **_summarize_model_result_for_llm(result)})
        except Exception as exc:
            runs.append(
                {
                    "status": "error",
                    "mode": mode,
                    "model_title": MODEL_TITLES.get(mode, mode),
                    "message": str(exc)[-500:],
                }
            )
    validation = validate_research_context(intent_plan, runs)
    return {
        "question": question,
        "generated_at": _generated_at(),
        "intent": intent_plan,
        "tool_plan": tool_plan,
        "mode_count": len(tool_plan),
        "runs": runs,
        "diagnostics": diagnostics,
        "validation": validation,
        "instruction": "这些是项目内模型/数据结果。回答时必须基于这些结果，缺失处要明确说明，不得编造价格、评分、公告或入选结果。",
    }


def _plain_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if isinstance(value, list):
        return "、".join(str(item) for item in value[:5]) or "-"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _short_text(value: Any, max_len: int = 42) -> str:
    text = re.sub(r"\s+", " ", _plain_value(value)).strip()
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _score_plain(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return _plain_value(value)


def _sanitize_feishu_text(text: str) -> str:
    """Convert LLM Markdown-ish text into Feishu plain text that reads cleanly."""
    cleaned = str(text or "").replace("\\n", "\n")
    cleaned = re.sub(r"```(?:\w+)?\n?", "", cleaned)
    cleaned = cleaned.replace("```", "")
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*[-*]\s+", "· ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _format_feishu_diagnostic_report(context: dict[str, Any]) -> str | None:
    diagnostics = context.get("diagnostics") or []
    if not diagnostics:
        return None
    diagnostic = diagnostics[0]
    stock = diagnostic.get("stock") or {}
    name = stock.get("name") or context.get("intent", {}).get("target_stock") or "目标股票"
    code = stock.get("code") or context.get("intent", {}).get("stock_code") or "-"
    style = diagnostic.get("diagnostic_style") or diagnostic.get("model") or "模型诊断"
    verdict_map = {"pass": "通过", "fail": "不通过", "needs_verification": "需进一步验证"}
    verdict = verdict_map.get(str(diagnostic.get("model_verdict") or ""), _plain_value(diagnostic.get("model_verdict")))
    lines = [
        f"📌 {name}（{code}）",
        f"模型：{style}",
        f"数据日期：{diagnostic.get('trade_date') or context.get('generated_at') or '-'}",
        f"结论：{verdict}",
    ]
    warnings = ((context.get("validation") or {}).get("warnings") or [])
    if warnings:
        lines.append("提示：" + "；".join(str(item) for item in warnings[:2]))

    metrics = diagnostic.get("metrics") or {}
    if metrics:
        metric_items = []
        labels = {
            "close": "收盘",
            "pct_chg": "涨幅%",
            "ma5": "MA5",
            "ma10": "MA10",
            "ma20": "MA20",
            "volume_ratio_5d": "量比",
            "obv": "OBV",
            "adx": "ADX",
            "max_single_drop_5d": "5日最大单跌%",
            "amount_yi": "成交额亿",
        }
        for key, label in labels.items():
            if key in metrics:
                metric_items.append(f"{label}={_plain_value(metrics.get(key))}")
        if metric_items:
            lines.extend(["", "【核心指标】", "  " + "；".join(metric_items)])

    rubric = diagnostic.get("rubric") or []
    if rubric:
        total = diagnostic.get("rubric_total_score")
        full = diagnostic.get("rubric_full_score")
        lines.extend(["", f"【H1-H6 评分】合计 {_plain_value(total)}/{_plain_value(full)}", "维度                 得分      关键数据"])
        for row in rubric:
            dimension = _short_text(row.get("dimension"), 18)
            score = f"{_score_plain(row.get('score'))}/{_plain_value(row.get('full_score'))}"
            key_data = _short_text(row.get("key_data"), 52)
            lines.append(f"{dimension:<18} {score:<8} {key_data}")

    gates = diagnostic.get("gates") or []
    if gates:
        lines.extend(["", "【门槛诊断】", "结果  门槛                 数值        说明"])
        for gate in gates:
            status = "通过" if gate.get("passed") else "未过"
            name_text = _short_text(gate.get("gate"), 18)
            value = _short_text(gate.get("value"), 12)
            note = _short_text(gate.get("note"), 42)
            lines.append(f"{status}  {name_text:<18} {value:<10} {note}")

    failed = diagnostic.get("failed_gates") or []
    if failed:
        lines.extend(["", "【失败原因】"])
        for gate in failed[:5]:
            lines.append(f"- {gate.get('gate')}: {_plain_value(gate.get('value'))}，{_short_text(gate.get('note'), 60)}")

    chain_nodes = diagnostic.get("chain_nodes") or (diagnostic.get("fundamental_context") or {}).get("chain_nodes") or []
    if chain_nodes:
        lines.extend(["", "【产业链/题材映射】", "  " + "、".join(_display_chain_node(item) for item in chain_nodes[:8])])

    lines.extend(["", "说明：以上只代表模型诊断结果，不构成自动买卖指令。"])
    return "\n".join(lines)


def _format_feishu_model_run_report(context: dict[str, Any]) -> str | None:
    runs = [run for run in (context.get("runs") or []) if run.get("status") == "ok"]
    if not runs:
        return None
    run = runs[0]
    title = run.get("model_title") or run.get("mode") or "项目模型"
    trade_date = run.get("trade_date") or context.get("generated_at") or "-"
    total_picks = run.get("total_picks", 0)
    top_picks = run.get("top_picks") or []
    resonance = run.get("resonance") or []
    lines = [
        "📊 投研模型结果",
        f"模型：{title}",
        f"日期：{trade_date}",
        f"入选数量：{total_picks}",
    ]
    warnings = ((context.get("validation") or {}).get("warnings") or [])
    if warnings:
        lines.append("提示：" + "；".join(str(item) for item in warnings[:2]))

    lines.extend(["", "【板块共振】"])
    if resonance:
        for item in resonance[:8]:
            text = re.sub(r"^\s*[-·]\s*", "", str(item)).strip()
            lines.append(f"· {text}")
    else:
        lines.append("· 暂无可统计的板块共振数据")

    if top_picks:
        lines.extend(["", "【入选清单】", "序号  代码      名称          板块/概念        评分     核心原因"])
        for index, pick in enumerate(top_picks[:10], 1):
            code = _short_text(pick.get("code"), 8)
            name = _short_text(pick.get("name"), 10)
            sector = _short_text(pick.get("sector"), 14)
            score = _short_text(pick.get("score"), 8)
            reason = _short_text(pick.get("reason"), 42)
            lines.append(f"{index:<4} {code:<8} {name:<10} {sector:<14} {score:<8} {reason}")
    else:
        reason = run.get("no_result_reason")
        lines.extend(["", "【模型结论】"])
        if reason:
            lines.append(f"· 未产生入选标的。原因：{_short_text(reason, 80)}")
        else:
            lines.append("· 本次模型未产生入选标的，因此没有可展开的标的清单。")

    process = run.get("process_summary")
    if process:
        lines.extend(["", "【过程摘要】", "  " + _short_text(process, 120)])

    lines.extend(["", "说明：以上只代表项目模型输出，不构成自动买卖指令。"])
    return "\n".join(lines)


def answer_investment_question(question: str, intent_plan: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    context = build_project_research_context(question, intent_plan)
    formatted = _format_feishu_diagnostic_report(context)
    if formatted:
        return formatted, context
    formatted = _format_feishu_model_run_report(context)
    if formatted:
        return formatted, context
    context_text = json.dumps(context, ensure_ascii=False, default=str)[:12000]
    prompt = (
        "请像投研助手一样回答用户问题。你必须先使用下面的项目数据/模型上下文，再结合常识解释。\n"
        "要求：\n"
        "1. 用中文直接回答结论；\n"
        "2. 明确引用 intent、tool_plan、diagnostics、validation 和项目模型里的日期、入选数量、板块共振、失败原因或标的；\n"
        "3. 如果 validation 有 warning，必须在回答中写出来；\n"
        "4. 如果项目数据不足，直接说不足，不能编造；\n"
        "5. 如果用户问某一只股票，先说明该股票是否出现在项目模型结果中；如果 diagnostics 有单票指标诊断，必须继续基于指标、门槛、失败项给出分析；不在结果且无 diagnostics 时，只能说明模型未给出直接支持，不能把其他标的结论套到它身上；\n"
        "6. 如果 diagnostics 包含 rubric，用 Markdown 表格输出维度、得分、满分、关键数据，并逐项解读；如果包含 gates，用表格输出门槛、是否通过、数值、说明；\n"
        "7. 对比不同模型时，必须说明各模型看的指标不同，不能混用；\n"
        "8. 涉及交易必须说明不构成自动买卖指令。\n\n"
        f"用户问题：{question}\n\n"
        f"项目上下文 JSON：{context_text}"
    )
    return _sanitize_feishu_text(ask_llm(prompt)), context


def command_from_intent(intent_plan: dict[str, Any], question: str) -> LarkCommand | None:
    if intent_plan.get("intent") not in {"model_run", "report_request"} and not _coerce_bool(intent_plan.get("needs_report")):
        return None
    modes = _modes_from_intent(intent_plan, question)
    if not modes:
        return parse_message_command(question)
    return LarkCommand(
        command=_strip_bot_mentions(question)[:40] or "模型运行",
        mode=modes[0],
        top_n=int(intent_plan.get("top_n") or 10),
        trade_date=intent_plan.get("trade_date"),
    )


def ask_llm(question: str) -> str:
    """Answer a non-model group question with a configured LLM."""
    question = (question or "").strip()
    if not question:
        return "我没有识别到具体问题，请在 @机器人 后面写清楚要问的内容。"

    system_prompt = (
        "你是 Suying AI 投研群助手。请用中文、直接、谨慎地回答。"
        "如果问题涉及投资决策，必须说明不构成买卖建议。"
        "不知道或缺少实时数据时要明确说明，不能编造数据、价格、公告或模型结果。"
    )
    timeout = int(os.environ.get("LARK_LLM_TIMEOUT_SEC", "30"))

    if os.environ.get("OPENAI_API_KEY"):
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        body = {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.2,
        }
        return _call_openai_compatible_llm(base_url, os.environ["OPENAI_API_KEY"], body, timeout)

    if os.environ.get("DEEPSEEK_API_KEY"):
        body = {
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.2,
        }
        return _call_openai_compatible_llm("https://api.deepseek.com/v1", os.environ["DEEPSEEK_API_KEY"], body, timeout)

    if os.environ.get("ANTHROPIC_API_KEY"):
        return _call_anthropic_llm(system_prompt, question, timeout)

    return (
        "当前后端没有配置大模型 API Key，所以普通问题暂时不能调用大模型回答。\n"
        "请配置 OPENAI_API_KEY、DEEPSEEK_API_KEY 或 ANTHROPIC_API_KEY 之一。\n"
        "选股/选债模型指令仍可使用，例如：@机器人 跑秋神午后选股。"
    )


def _call_openai_compatible_llm(base_url: str, api_key: str, body: dict[str, Any], timeout: int) -> str:
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return f"调用大模型失败：{exc}"
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    return content or "大模型没有返回有效内容。"


def _call_anthropic_llm(system_prompt: str, question: str, timeout: int) -> str:
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    body = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
        "max_tokens": int(os.environ.get("LARK_LLM_MAX_TOKENS", "1600")),
        "system": system_prompt,
        "messages": [{"role": "user", "content": question}],
    }
    req = urllib.request.Request(
        f"{base_url}/v1/messages",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return f"调用大模型失败：{exc}"
    parts = []
    for item in data.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
    return "\n".join(part.strip() for part in parts if part.strip()) or "大模型没有返回有效内容。"


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
    if not os.environ.get("LARK_APP_ID", "").strip() or not os.environ.get("LARK_APP_SECRET", "").strip():
        return _send_text_to_chat_via_lark_cli(chat_id, text)

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


def _send_text_to_chat_via_lark_cli(chat_id: str, text: str) -> dict[str, Any]:
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


def send_streaming_text_to_chat(chat_id: str, text: str) -> list[dict[str, Any]]:
    """Approximate streaming in Feishu by sending a long answer in paced chunks."""
    chunks = _split_streaming_text(text, int(os.environ.get("LARK_STREAM_CHUNK_CHARS", "700")))
    responses = []
    delay = float(os.environ.get("LARK_STREAM_CHUNK_DELAY_SEC", "0.6"))
    for index, chunk in enumerate(chunks):
        prefix = "" if len(chunks) == 1 else f"({index + 1}/{len(chunks)}) "
        responses.append(send_text_to_chat(chat_id, prefix + chunk))
        if index < len(chunks) - 1 and delay > 0:
            time.sleep(delay)
    return responses


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

    if not bot_is_mentioned(msg["text"]):
        return {"ignored": True, "reason": "bot_not_mentioned"}

    question = _strip_bot_mentions(msg["text"])
    if not question:
        return {"ignored": True, "reason": "empty_question"}

    intent_plan: dict[str, Any] | None = None
    if question.strip().startswith("/"):
        command = parse_message_command(msg["text"])
    else:
        intent_plan = parse_intent_with_llm(question)
        command = command_from_intent(intent_plan, question) or (
            parse_message_command(msg["text"]) if _looks_like_model_run_request(question) else None
        )
    if not command:
        if intent_plan is None:
            intent_plan = parse_intent_with_llm(question)
        if _coerce_bool(intent_plan.get("is_investment_related")) or is_investment_question(question):
            send_text_to_chat(chat_id, "收到投研问题，正在理解意图并调用项目数据/模型。")
            answer, context = answer_investment_question(question, intent_plan)
            if context.get("diagnostics") or context.get("runs"):
                send_text_to_chat(chat_id, answer)
            else:
                send_streaming_text_to_chat(chat_id, answer)
            return {
                "ignored": False,
                "mode": "research_qa",
                "question": question,
                "intent": intent_plan.get("intent"),
                "context_modes": [run.get("mode") for run in context.get("runs", [])],
                "answer_sent": True,
            }
        send_text_to_chat(chat_id, "收到问题，正在调用大模型分析。")
        answer = _sanitize_feishu_text(ask_llm(question))
        send_streaming_text_to_chat(chat_id, answer)
        return {
            "ignored": False,
            "mode": "general_qa",
            "question": question,
            "answer_sent": True,
        }

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
