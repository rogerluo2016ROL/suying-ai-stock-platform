#!/usr/bin/env python3
"""Unified runner for stock/bond research model pipelines.

Flow:
  trigger -> data refresh -> model run -> markdown/json output -> optional Lark doc
  sync -> optional group message/poster.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "model_pipeline.json"
DEFAULT_PG_URL = "postgresql://kronos:kronos@localhost:6432/kronos"

for path in (
    ROOT / "services" / "screener-service",
    ROOT / "packages" / "kronos-factors",
    ROOT / "packages" / "kronos-data",
    ROOT / "packages" / "kronos-contracts",
):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_send_feishu(args: argparse.Namespace, config: dict[str, Any]) -> bool:
    if args.send_feishu is not None:
        return bool(args.send_feishu)
    return bool(config.get("send_feishu_by_default", False))


def resolve_chat_targets(args: argparse.Namespace, config: dict[str, Any]) -> list[dict[str, str]]:
    """解析发送目标，显式 CLI 参数优先，否则使用配置中的全部群。"""

    raw_chat_ids = getattr(args, "chat_id", [])
    if isinstance(raw_chat_ids, str):
        chat_ids = [raw_chat_ids] if raw_chat_ids.strip() else []
    else:
        chat_ids = [str(item).strip() for item in (raw_chat_ids or []) if str(item).strip()]
    if chat_ids:
        return [
            {"key": f"cli_{index}", "name": f"目标群 {index}", "chat_id": chat_id}
            for index, chat_id in enumerate(chat_ids, 1)
        ]

    targets = []
    for item in config.get("chat_targets") or []:
        chat_id = str(item.get("chat_id") or "").strip()
        if chat_id:
            targets.append(
                {
                    "key": str(item.get("key") or ""),
                    "name": str(item.get("name") or ""),
                    "chat_id": chat_id,
                }
            )
    if targets:
        return targets
    default_chat_id = str(config.get("default_chat_id") or "").strip()
    return (
        [{"key": "default", "name": "默认群", "chat_id": default_chat_id}]
        if default_chat_id
        else []
    )


def resolve_model(config: dict[str, Any], model_key: str) -> tuple[str, dict[str, Any]]:
    models = config.get("models") or {}
    if model_key in models:
        return model_key, models[model_key]
    compact = model_key.strip().lower()
    for key, item in models.items():
        aliases = [str(x).lower() for x in item.get("aliases") or []]
        if compact in aliases:
            return key, item
    available = ", ".join(sorted(models))
    raise SystemExit(f"未知模型: {model_key}. 可用模型: {available}")


def today() -> str:
    return date.today().isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def extract_message_id(response: Any) -> str:
    if isinstance(response, dict):
        message_id = response.get("message_id")
        if isinstance(message_id, str) and message_id.strip():
            return message_id.strip()
        for value in response.values():
            found = extract_message_id(value)
            if found:
                return found
    elif isinstance(response, list):
        for value in response:
            found = extract_message_id(value)
            if found:
                return found
    return ""


def _contains_message_id(payload: Any, message_id: str) -> bool:
    if isinstance(payload, dict):
        if payload.get("message_id") == message_id:
            return True
        return any(_contains_message_id(value, message_id) for value in payload.values())
    if isinstance(payload, list):
        return any(_contains_message_id(value, message_id) for value in payload)
    return False


def confirm_message_delivery(chat_id: str, message_id: str, *, attempts: int = 3) -> bool:
    total_attempts = max(attempts, 1)
    for attempt in range(total_attempts):
        read_status_cmd = [
            "lark-cli",
            "im",
            "messages",
            "read_users",
            "--as",
            "bot",
            "--message-id",
            message_id,
            "--user-id-type",
            "open_id",
            "--page-size",
            "1",
            "--format",
            "json",
        ]
        read_status = subprocess.run(
            read_status_cmd,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if read_status.returncode == 0:
            return True

        for identity in ("bot", "user"):
            cmd = [
                "lark-cli",
                "im",
                "+chat-messages-list",
                "--as",
                identity,
                "--chat-id",
                chat_id,
                "--page-size",
                "20",
                "--no-reactions",
                "--json",
            ]
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            if proc.returncode == 0:
                try:
                    payload = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    payload = None
                if _contains_message_id(payload, message_id):
                    return True
        if attempt + 1 < total_attempts:
            time.sleep(0.5)
    return False


def write_delivery_state(
    run_dir: Path,
    result: dict[str, Any],
    state: dict[str, Any],
) -> None:
    result.setdefault("pipeline", {})["feishu_delivery"] = state
    _write_json(run_dir / "result.json", result)

    pipeline_path = run_dir / "pipeline.json"
    if pipeline_path.exists():
        pipeline_payload = json.loads(pipeline_path.read_text(encoding="utf-8"))
    else:
        pipeline_payload = {}
    pipeline_payload["feishu_delivery"] = state
    _write_json(pipeline_path, pipeline_payload)


def _delivery_error(exc: Exception) -> str:
    detail = str(exc)
    for key in ("LARK_APP_ID", "LARK_APP_SECRET"):
        value = os.environ.get(key, "").strip()
        if value:
            detail = detail.replace(value, "<redacted>")
    return f"{type(exc).__name__}: {detail}"[-500:]


def deliver_feishu_message(
    *,
    run_dir: Path,
    result: dict[str, Any],
    chat_id: str,
    message: str,
    sender: Any,
) -> dict[str, Any]:
    try:
        response = sender(chat_id, message)
    except Exception as exc:
        state = {
            "push_status": "failed",
            "chat_id": chat_id,
            "message_id": "",
            "error": _delivery_error(exc),
        }
        write_delivery_state(run_dir, result, state)
        raise

    message_id = extract_message_id(response)
    if not message_id:
        state = {
            "push_status": "unconfirmed",
            "chat_id": chat_id,
            "message_id": "",
            "error": "missing_message_id",
        }
        write_delivery_state(run_dir, result, state)
        raise RuntimeError("飞书接口未返回消息 ID，无法确认送达。")

    try:
        confirmed = confirm_message_delivery(chat_id, message_id)
    except Exception as exc:
        state = {
            "push_status": "unconfirmed",
            "chat_id": chat_id,
            "message_id": message_id,
            "error": _delivery_error(exc),
        }
        write_delivery_state(run_dir, result, state)
        raise RuntimeError("飞书消息送达核验失败。") from exc

    if not confirmed:
        state = {
            "push_status": "unconfirmed",
            "chat_id": chat_id,
            "message_id": message_id,
            "error": "message_not_found_in_chat",
        }
        write_delivery_state(run_dir, result, state)
        raise RuntimeError("飞书消息未确认送达目标群。")

    state = {
        "push_status": "confirmed",
        "chat_id": chat_id,
        "message_id": message_id,
    }
    write_delivery_state(run_dir, result, state)
    return state


def deliver_feishu_messages(
    *,
    run_dir: Path,
    result: dict[str, Any],
    targets: list[dict[str, str]],
    message: str,
    sender: Any,
    attempts: int = 3,
) -> dict[str, Any]:
    """向多个群发送同一份结果；单群失败不阻断其他群。"""

    deliveries: list[dict[str, Any]] = []
    for target in targets:
        chat_id = str(target.get("chat_id") or "").strip()
        delivered: dict[str, Any] | None = None
        last_error = ""
        for _attempt in range(max(1, attempts)):
            try:
                delivered = deliver_feishu_message(
                    run_dir=run_dir,
                    result=result,
                    chat_id=chat_id,
                    message=message,
                    sender=sender,
                )
                break
            except Exception as exc:
                last_error = _delivery_error(exc)
                recorded = (result.get("pipeline") or {}).get("feishu_delivery") or {}
                if recorded.get("chat_id") == chat_id and recorded.get("message_id"):
                    delivered = dict(recorded)
                    break
        if delivered is None:
            delivered = {
                "push_status": "failed",
                "chat_id": chat_id,
                "message_id": "",
                "error": last_error or "send_failed",
            }
        delivered = {
            "key": target.get("key") or "",
            "name": target.get("name") or "",
            **delivered,
        }
        deliveries.append(delivered)

    confirmed = sum(item.get("push_status") == "confirmed" for item in deliveries)
    if deliveries and confirmed == len(deliveries):
        status = "success"
    elif confirmed:
        status = "partial_delivery"
    else:
        status = "failed_delivery"
    aggregate = {"status": status, "deliveries": deliveries}

    result.setdefault("pipeline", {})["feishu_delivery"] = aggregate
    result["pipeline"]["feishu_deliveries"] = deliveries
    _write_json(run_dir / "result.json", result)
    pipeline_path = run_dir / "pipeline.json"
    pipeline_payload = (
        json.loads(pipeline_path.read_text(encoding="utf-8"))
        if pipeline_path.exists()
        else {}
    )
    pipeline_payload["feishu_delivery"] = aggregate
    pipeline_payload["feishu_deliveries"] = deliveries
    _write_json(pipeline_path, pipeline_payload)
    return aggregate


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _git_state() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False,
        ).stdout.strip() or "unknown"
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False,
        ).stdout.strip())
    except FileNotFoundError:
        return {"commit": "unavailable", "dirty": True}
    return {"commit": commit, "dirty": dirty}


def build_run_manifest(*, args, model_key: str, run_id: str, trade_date: str,
                       result: dict[str, Any], parameters: dict[str, Any], artifacts: list[Path],
                       git_state: dict[str, Any] | None = None):
    from kronos_contracts.model_run import ModelRunManifest

    git = git_state or _git_state()
    if args.official and git["dirty"]:
        raise SystemExit(2)
    try:
        cutoff = datetime.fromisoformat(args.cutoff_time) if args.cutoff_time else None
        snapshot_id = args.data_snapshot_id or "UNAVAILABLE"
        return ModelRunManifest(
            schema_version="1.0", run_id=run_id, official=bool(args.official),
            working_tree_dirty=git["dirty"], strict_timeline=bool(args.strict_timeline),
            model_key=model_key, model_version=args.model_version or "unversioned",
            code_commit=git["commit"], parameters_hash=_stable_hash(parameters),
            target_trade_date=trade_date, cutoff_time=cutoff, data_snapshot_id=snapshot_id,
            universe_hash=_stable_hash(sorted({str(p.get("code") or p.get("ts_code")) for p in result.get("picks", []) if p.get("code") or p.get("ts_code")})),
            cost_bps=float(args.cost_bps), artifacts=[str(path) for path in artifacts],
            result_status=str(result.get("status") or "success"),
        )
    except ValueError as exc:
        if args.official:
            raise SystemExit(2) from exc
        raise


def _run_subprocess(cmd: list[str], timeout: int = 240) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    result: dict[str, Any] = {
        "returncode": proc.returncode,
        "elapsed": round(time.time() - started, 1),
        "stdout_tail": (proc.stdout or "").strip()[-2000:],
        "stderr_tail": (proc.stderr or "").strip()[-2000:],
    }
    lines = (proc.stdout or "").strip().splitlines()
    if lines:
        for line in reversed(lines):
            text = line.strip()
            if not text.startswith("{"):
                continue
            try:
                result["json"] = json.loads("\n".join(lines[lines.index(line) :]))
                break
            except Exception:
                try:
                    result["json"] = json.loads(text)
                    break
                except Exception:
                    pass
    return result


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _query_count(sql: str) -> int:
    import psycopg2

    conn = psycopg2.connect(os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL))
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return int(row[0] or 0)
    finally:
        conn.close()


def _safe_query_count(sql: str) -> int:
    try:
        return _query_count(sql)
    except Exception:
        return 0


def _cb_primary_source_rows(trade_date: str) -> dict[str, int]:
    dash = trade_date
    compact = trade_date.replace("-", "")
    return {
        "limit_list_d": _safe_query_count(
            "SELECT COUNT(*) FROM limit_list_d "
            f"WHERE trade_date::text IN ('{dash}', '{compact}') AND limit_type='U'"
        ),
        "kpl_list": _safe_query_count(
            "SELECT COUNT(*) FROM kpl_list "
            f"WHERE trade_date::text IN ('{dash}', '{compact}')"
        ),
        "eastmoney_limit_pool": _safe_query_count(
            "SELECT COUNT(*) FROM eastmoney_limit_pool "
            f"WHERE trade_date::text IN ('{dash}', '{compact}')"
        ),
        "stk_auction_o": _safe_query_count(
            "SELECT COUNT(*) FROM stk_auction_o "
            f"WHERE trade_date::text IN ('{dash}', '{compact}')"
        ),
    }


def plan_cb_auction_fallback(rows: dict[str, int]) -> dict[str, Any]:
    """根据当天 Tushare 关键表是否可用，决定东方财富补采范围。"""

    tushare_trigger_ready = int(rows.get("limit_list_d") or 0) > 0
    tushare_auction_ready = int(rows.get("stk_auction_o") or 0) > 0
    return {
        "collect_eastmoney_limit_pool": not tushare_trigger_ready,
        "collect_eastmoney_snapshot": not tushare_auction_ready,
        "primary_source": "tushare" if tushare_trigger_ready and tushare_auction_ready else "tushare_unavailable",
    }


def _run_auction_trigger() -> dict[str, Any]:
    code = (
        "import json; "
        "from app.scheduler import collect_auction_snapshot; "
        "print(json.dumps(collect_auction_snapshot(), ensure_ascii=False, default=str))"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(ROOT / "services" / "data-service"),
            str(ROOT / "packages" / "kronos-data"),
            str(ROOT / "packages" / "kronos-factors"),
            env.get("PYTHONPATH", ""),
        ]
    )
    started = time.time()
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT / "services" / "data-service",
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    payload: dict[str, Any] = {
        "returncode": proc.returncode,
        "elapsed": round(time.time() - started, 1),
        "stdout_tail": (proc.stdout or "").strip()[-2000:],
        "stderr_tail": (proc.stderr or "").strip()[-2000:],
    }
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload["json"] = json.loads(line)
            payload.update(payload["json"])
            break
        except Exception:
            continue
    if proc.returncode != 0 and "status" not in payload:
        payload["status"] = "error"
    return payload


def _run_eastmoney_fallback(trade_date: str) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "collect_eastmoney_auction_snapshot.py"),
        "--trade-date",
        trade_date,
        "--overwrite",
    ]
    return _run_subprocess(cmd, timeout=120)


def _run_eastmoney_limit_pool_fallback(trade_date: str) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "collect_eastmoney_limit_pool.py"),
        "--trade-date",
        trade_date,
        "--overwrite",
    ]
    return _run_subprocess(cmd, timeout=120)


def _run_cb_emergency_snapshot(trade_date: str, top_n: int) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "cb_auction_snapshot_emergency.py"),
        trade_date,
        "--top-n",
        str(top_n),
        "--max-triggers",
        "50",
        "--min-gap-pct",
        "8",
        "--min-amount-wan",
        "1000",
    ]
    run = _run_subprocess(cmd, timeout=180)
    output_path = ROOT / "outputs" / "cb_auction_snapshot_emergency" / f"{trade_date}_cb_auction_snapshot_emergency.json"
    if output_path.exists():
        run["result_path"] = str(output_path)
        run["result"] = json.loads(output_path.read_text(encoding="utf-8"))
    return run


def _append_fallback_markdown(markdown: str, fallback: dict[str, Any] | None) -> str:
    if not fallback or not fallback.get("result"):
        return markdown
    result = fallback["result"]
    bonds = result.get("bonds") or []
    concepts = result.get("concepts") or []
    lines = [
        "",
        "## 六、东方财富普通快照兜底口径",
        "",
        "> 这是最后兜底口径，来自普通行情快照，不包含涨停池封单资金，不能等价替代 `limit_list_d.fd_amount` 或东方财富涨停池 `fund`。",
        "",
        "| 序号 | 转债代码 | 转债名称 | 正股 | 题材分 | 匹配概念 | 风险 |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    if bonds:
        for idx, bond in enumerate(bonds[:10], 1):
            concepts_text = "、".join(bond.get("matched_concepts") or [])
            risks = "；".join(bond.get("risk_notes") or [])
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(idx),
                        str(bond.get("cb_code") or bond.get("code") or "-"),
                        str(bond.get("cb_name") or bond.get("name") or "-"),
                        f"{bond.get('stk_code') or '-'} {bond.get('stk_name') or '-'}",
                        f"{float(bond.get('theme_score') or bond.get('score') or 0):.1f}",
                        concepts_text or "-",
                        risks or "-",
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | - | 未产生备用清单 |")
    lines.extend(["", "### 备用口径板块共振", ""])
    if concepts:
        for item in concepts[:10]:
            lines.append(
                f"- {item.get('concept_name') or '-'}：触发股 {item.get('trigger_stock_count') or 0} 只，"
                f"竞价强度 {float(item.get('concept_strength') or 0):.2f}%，"
                f"代理金额 {float(item.get('concept_fd_amount_yi') or 0):.2f} 亿。"
            )
    else:
        lines.append("- 暂无备用口径共振数据。")
    return markdown + "\n".join(lines) + "\n"


def _fallback_summary(fallback: dict[str, Any] | None) -> str:
    if not fallback or not fallback.get("result"):
        return ""
    result = fallback["result"]
    bonds = result.get("bonds") or []
    lines = [f"东方财富普通快照兜底口径: {len(bonds)} 只"]
    for idx, bond in enumerate(bonds[:5], 1):
        lines.append(
            f"{idx}. {bond.get('cb_code') or bond.get('code')} {bond.get('cb_name') or bond.get('name')}"
            f" | 正股 {bond.get('stk_code') or '-'} {bond.get('stk_name') or '-'}"
            f" | 题材分 {float(bond.get('theme_score') or bond.get('score') or 0):.1f}"
        )
    lines.append("说明: 普通快照不含涨停池封单资金，只作最后兜底观察。")
    return "\n".join(lines)


def _attach_candidate_fallback(result: dict[str, Any], command: Any, top_n: int) -> None:
    """Attach non-tradeable candidates when strict model output is empty.

    This keeps the executable `picks` list honest while still giving users the
    watchlist/context they expect in weak markets.
    """
    if result.get("picks") or result.get("candidate_picks"):
        return
    if command.mode != "leader_afternoon":
        return

    try:
        from kronos_factors.scorer._db_stub import set_db_adapter
        from kronos_factors.pg_adapter import create_pg_adapter
        from kronos_factors.engine.leader_afternoon import build_sector_resonance_summary, run_afternoon_screening

        adapter = create_pg_adapter(os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL))
        if adapter:
            set_db_adapter(adapter)
        _, scores = run_afternoon_screening(
            command.trade_date,
            time_slot="14:30",
            top_n=top_n,
            tradeable_only=False,
        )
    except Exception as exc:
        result.setdefault("pipeline", {})["candidate_fallback_error"] = str(exc)[-500:]
        return

    scores = sorted(scores or [], key=lambda item: -float(item.get("total_score") or item.get("score") or 0))
    if not scores:
        return

    result["candidate_total"] = len(scores)
    result["candidate_reason"] = (
        result.get("no_result_reason")
        or "严格主买为空；以下为弱市过滤前的候选池，仅供观察，不作为主买清单。"
    )
    result["candidate_picks"] = scores[: max(5, min(30, top_n))]
    try:
        result["candidate_sector_resonance"] = build_sector_resonance_summary(scores, limit=12)
    except Exception:
        result["candidate_sector_resonance"] = []

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in scores:
        grouped[str(item.get("industry") or "其他")].append(item)
    details = []
    for sector, items in grouped.items():
        top_items = sorted(items, key=lambda item: -float(item.get("total_score") or 0))[:6]
        details.append(
            {
                "sector": sector,
                "count": len(items),
                "avg_score": round(sum(float(x.get("total_score") or 0) for x in items) / max(1, len(items)), 1),
                "avg_gain": round(sum(float(x.get("gain_pct") or 0) for x in items) / max(1, len(items)), 2),
                "top_names": [f"{x.get('name')}({float(x.get('gain_pct') or 0):+.1f}%,{float(x.get('total_score') or 0):.1f})" for x in top_items],
            }
        )
    details.sort(key=lambda item: (item["count"], item["avg_score"]), reverse=True)
    result["candidate_sector_details"] = details[:12]


def _candidate_summary(result: dict[str, Any]) -> str:
    candidates = result.get("candidate_picks") or []
    if not candidates:
        return ""
    lines = [
        f"主买为空，已推送候选池: {result.get('candidate_total') or len(candidates)} 只",
        "候选Top5:",
    ]
    for idx, pick in enumerate(candidates[:5], 1):
        lines.append(
            f"{idx}. {pick.get('code')} {pick.get('name')}"
            f" | {pick.get('industry') or '-'}"
            f" | 涨幅 {float(pick.get('gain_pct') or 0):+.2f}%"
            f" | 评分 {float(pick.get('total_score') or pick.get('score') or 0):.1f}"
        )
    sectors = result.get("candidate_sector_details") or []
    if sectors:
        lines.append("候选共振:")
        for item in sectors[:3]:
            lines.append(
                f"- {item.get('sector')}: {item.get('count')}只，"
                f"均分 {item.get('avg_score')}，均涨 {float(item.get('avg_gain') or 0):+.2f}%"
            )
    lines.append("说明: 候选池不是主买清单，只供观察。")
    return "\n".join(lines)


def _normalize_report_labels(markdown: str, mode: str) -> str:
    if not mode.startswith("cb_"):
        return markdown
    replacements = {
        "选股日期": "选债日期",
        "选股清单": "选债清单",
        "本报告是模型筛选结果，不是自动买入指令。": "本报告是模型筛选结果，不是自动买入指令。",
        "本次没有股票通过模型门槛。": "本次没有转债通过模型门槛。",
        "盘中数据随时间变化，后续重新运行可能得到不同结果。": "转债和正股数据随时间变化，后续重新运行可能得到不同结果。",
    }
    for old, new in replacements.items():
        markdown = markdown.replace(old, new)
    return markdown


def _run_registered_mode(
    mode: str,
    top_n: int,
    trade_date: str | None,
    *,
    time_slot: str = "14:30",
) -> dict[str, Any]:
    """Run every mode registered by screener-service config."""
    from app.routers.screener import (
        _run_afternoon_mode,
        _run_bi_full_market_mode,
        _run_bi_shifu_trend_mode,
        _run_bi_trend_mode,
        _run_cb_mode,
        _run_leader_mode,
        _run_multifactor_mode,
        _run_supply_chain_mode,
        _run_supply_chain_trend_launch_mode,
    )

    if mode in {"leader_scalp", "leader_intraday", "leader_auction", "leader_closing"}:
        return _run_leader_mode(mode, top_n, trade_date)
    if mode in {"leader_afternoon", "leader_afternoon_trend_full"}:
        return _run_afternoon_mode(mode, top_n, trade_date, time_slot=time_slot)
    if mode in {
        "cb_floor",
        "cb_intraday",
        "cb_auction",
        "cb_auction_t0",
        "cb_auction_t0_v2",
        "cb_auction_t0_v2_1",
    }:
        return _run_cb_mode(mode, top_n, trade_date)
    if mode == "bi_trend_launch":
        return _run_bi_trend_mode(mode, top_n, trade_date)
    if mode == "bi_shifu_trend":
        return _run_bi_shifu_trend_mode(mode, top_n, trade_date)
    if mode == "bi_trend_full_market":
        return _run_bi_full_market_mode(mode, top_n, trade_date)
    if mode == "supply_chain":
        return _run_supply_chain_mode(mode, top_n, trade_date)
    if mode == "supply_chain_trend_launch":
        return _run_supply_chain_trend_launch_mode(mode, top_n, trade_date)
    if mode in {"short", "chokepoint"}:
        result = _run_multifactor_mode(mode, top_n, trade_date)
        if not result.get("trade_date"):
            result["trade_date"] = trade_date
        if "total_picks" not in result:
            result["total_picks"] = len(result.get("picks") or [])
        return result
    raise ValueError(f"unsupported registered mode: {mode}")


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    _load_dotenv(ROOT / "docker" / ".env.lark-bot")
    os.environ.setdefault("KRONOS_PG_URL", DEFAULT_PG_URL)

    from app.lark_bot import (
        LarkCommand,
        _format_group_reply,
        build_markdown_report,
        generate_poster_image,
        refresh_before_run,
        send_image_to_chat,
        send_text_to_chat,
        sync_markdown_to_lark_doc,
        write_markdown_report,
    )
    import app.lark_bot as lark_bot

    config = load_config(Path(args.config))
    model_key, model_cfg = resolve_model(config, args.model)
    trade_date = today() if args.trade_date in {"", "today", None} else args.trade_date
    run_git_state = _git_state()
    if args.official and (
        run_git_state["dirty"] or not args.strict_timeline or not args.data_snapshot_id or not args.cutoff_time
    ):
        raise SystemExit(2)
    top_n = args.top_n or int(model_cfg.get("top_n") or 20)
    requested_time_slot = getattr(args, "time_slot", "") or "14:30"
    command = LarkCommand(
        command=str(model_cfg.get("title") or model_key),
        mode=str(model_cfg["mode"]),
        top_n=top_n,
        trade_date=trade_date,
    )
    lark_bot.MODEL_TITLES[command.mode] = str(model_cfg.get("title") or model_key)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ROOT / "outputs" / "pipeline_runs" / trade_date / f"{run_id}_{model_key}"
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        payload = {
            "status": "dry_run",
            "model_key": model_key,
            "mode": command.mode,
            "trade_date": trade_date,
            "top_n": top_n,
            "command": command.__dict__,
            "run_dir": str(run_dir),
        }
        _write_json(run_dir / "pipeline.json", payload)
        return payload

    refresh = {"status": "skipped"}
    auction_trigger: dict[str, Any] | None = None
    primary_rows: dict[str, int] | None = None
    fallback: dict[str, Any] | None = None
    pre_model_fallback: dict[str, Any] | None = None
    cb_data_readiness: dict[str, Any] | None = None

    if not args.no_refresh:
        refresh = refresh_before_run(command)
        if command.mode.startswith("cb_auction_t0") and args.trigger_auction:
            auction_trigger = _run_auction_trigger()

    if command.mode.startswith("cb_auction_t0"):
        fallback_enabled = bool(model_cfg.get("eastmoney_fallback")) and args.eastmoney_fallback
        primary_rows = _cb_primary_source_rows(trade_date)
        fallback_plan = plan_cb_auction_fallback(primary_rows)
        pre_model_fallback = {}
        if fallback_enabled and fallback_plan["collect_eastmoney_limit_pool"]:
            pre_model_fallback["eastmoney_limit_pool"] = _run_eastmoney_limit_pool_fallback(trade_date)
        if fallback_enabled and fallback_plan["collect_eastmoney_snapshot"]:
            pre_model_fallback["eastmoney_snapshot"] = _run_eastmoney_fallback(trade_date)
        if not pre_model_fallback:
            pre_model_fallback = None
        primary_rows = _cb_primary_source_rows(trade_date)
        trigger_ready = (
            int(primary_rows.get("limit_list_d") or 0) > 0
            or int(primary_rows.get("eastmoney_limit_pool") or 0) > 0
        )
        auction_ready = int(primary_rows.get("stk_auction_o") or 0) > 0
        cb_data_readiness = {
            "ready": trigger_ready and auction_ready,
            "trigger_ready": trigger_ready,
            "auction_ready": auction_ready,
            "source": (
                "tushare"
                if fallback_plan["primary_source"] == "tushare"
                else "eastmoney_fallback"
                if trigger_ready and auction_ready
                else "unavailable"
            ),
            "rows": primary_rows,
        }

    if cb_data_readiness is not None and not cb_data_readiness["ready"]:
        missing = []
        if not cb_data_readiness["trigger_ready"]:
            missing.append("涨停触发数据")
        if not cb_data_readiness["auction_ready"]:
            missing.append("竞价快照")
        result = {
            "status": "data_insufficient",
            "mode": command.mode,
            "trade_date": command.trade_date,
            "total_picks": 0,
            "picks": [],
            "no_result_reason": "主源和备用源仍缺少" + "、".join(missing) + "，本次不生成选债清单。",
        }
    else:
        result = _run_registered_mode(
            command.mode,
            command.top_n,
            command.trade_date,
            time_slot=requested_time_slot,
        )
    result["data_refresh"] = refresh
    result["pipeline"] = {
        "model_key": model_key,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    if auction_trigger is not None:
        result["pipeline"]["auction_trigger"] = auction_trigger
    if pre_model_fallback is not None:
        result["pipeline"]["pre_model_fallback"] = pre_model_fallback
    if cb_data_readiness is not None:
        result["pipeline"]["auction_data_readiness"] = cb_data_readiness
        result["pipeline"]["data_source"] = cb_data_readiness["source"]

    _attach_candidate_fallback(result, command, top_n)

    if command.mode.startswith("cb_auction_t0") and cb_data_readiness and cb_data_readiness["ready"]:
        primary_rows = _cb_primary_source_rows(trade_date)
        result["pipeline"]["primary_rows"] = primary_rows
        fallback_enabled = bool(model_cfg.get("eastmoney_fallback")) and args.eastmoney_fallback
        if fallback_enabled and int(result.get("total_picks") or 0) == 0:
            if (
                (primary_rows.get("limit_list_d") or 0) == 0
                and (primary_rows.get("kpl_list") or 0) == 0
                and (primary_rows.get("eastmoney_limit_pool") or 0) == 0
            ):
                em_pool = _run_eastmoney_limit_pool_fallback(trade_date)
                primary_rows = _cb_primary_source_rows(trade_date)
                result["pipeline"]["primary_rows"] = primary_rows
                result["pipeline"]["eastmoney_limit_pool_fallback"] = em_pool
                result = _run_registered_mode(
                    command.mode,
                    command.top_n,
                    command.trade_date,
                    time_slot=requested_time_slot,
                )
                result["data_refresh"] = refresh
                result["pipeline"] = {
                    "model_key": model_key,
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                    "primary_rows": primary_rows,
                    "eastmoney_limit_pool_fallback": em_pool,
                }
                if auction_trigger is not None:
                    result["pipeline"]["auction_trigger"] = auction_trigger
            if fallback_enabled and int(result.get("total_picks") or 0) == 0 and (primary_rows.get("eastmoney_limit_pool") or 0) == 0:
                em = _run_eastmoney_fallback(trade_date)
                emergency = _run_cb_emergency_snapshot(trade_date, top_n)
                fallback = {"eastmoney": em, **emergency}
                result["pipeline"]["eastmoney_fallback"] = fallback

    explicit_time_slot = getattr(args, "time_slot", "")
    if explicit_time_slot and not command.mode.startswith("cb_"):
        from app.market_strength import load_market_strength

        market_strength = load_market_strength(
            trade_date,
            explicit_time_slot,
            os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL),
        )
        result["market_strength"] = market_strength
        result["pipeline"]["planned_time_slot"] = explicit_time_slot
        result["pipeline"]["market_snapshot_time"] = market_strength.get("snapshot_time")

    markdown = build_markdown_report(result)
    markdown = _normalize_report_labels(markdown, command.mode)
    markdown = _append_fallback_markdown(markdown, fallback)
    report_path = write_markdown_report(result, markdown)
    result["pipeline"]["markdown_path"] = str(report_path)

    _write_json(run_dir / "result.json", result)
    _write_json(
        run_dir / "pipeline.json",
        {
            "status": "ok",
            "model_key": model_key,
            "trade_date": trade_date,
            "mode": command.mode,
            "top_n": top_n,
            "refresh": refresh,
            "primary_rows": primary_rows,
            "pre_model_fallback": pre_model_fallback,
            "fallback": fallback,
            "report_path": str(report_path),
        },
    )
    manifest = build_run_manifest(
        args=args, model_key=model_key, run_id=run_id, trade_date=trade_date, result=result,
        parameters={"mode": command.mode, "top_n": top_n, "cost_bps": args.cost_bps},
        artifacts=[run_dir / "result.json", run_dir / "pipeline.json", report_path],
        git_state=run_git_state,
    )
    manifest_path = run_dir / "manifest.json"
    _write_json(manifest_path, manifest.model_dump(mode="json"))
    result["pipeline"]["manifest_path"] = str(manifest_path)
    _write_json(run_dir / "result.json", result)

    doc: dict[str, Any] | None = None
    if args.sync_doc:
        doc = sync_markdown_to_lark_doc(report_path, result)
        result["pipeline"]["lark_doc"] = doc
        _write_json(run_dir / "result.json", result)

    chat_targets = resolve_chat_targets(args, config)
    if resolve_send_feishu(args, config):
        if not chat_targets:
            raise SystemExit("缺少 chat_id，无法发送飞书群。")
        message = _format_group_reply(result, doc or {})
        extra = _fallback_summary(fallback)
        if extra:
            message = message + "\n\n" + extra
        candidate_extra = _candidate_summary(result)
        if candidate_extra:
            message = message + "\n\n" + candidate_extra
        deliver_feishu_messages(
            run_dir=run_dir,
            result=result,
            targets=chat_targets,
            message=message,
            sender=send_text_to_chat,
        )
        if args.send_poster:
            poster = generate_poster_image(result)
            if poster:
                for target in chat_targets:
                    send_image_to_chat(target["chat_id"], poster)

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="统一选股/选债模型流水线")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--model", default="", help="模型 key 或别名")
    parser.add_argument("--date", dest="trade_date", default="today")
    parser.add_argument("--time-slot", default="", help="盘中模型数据截止时点，如 14:00")
    parser.add_argument("--top-n", type=int, default=0)
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-refresh", action="store_true")
    parser.add_argument("--trigger-auction", action="store_true", help="竞价选债时额外触发9:25竞价采集")
    parser.add_argument("--eastmoney-fallback", action="store_true", help="竞价选债无主数据时启用东方财富备用快照")
    parser.add_argument("--sync-doc", action="store_true", help="同步飞书文档")
    parser.add_argument(
        "--send-feishu",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="发送飞书群消息（默认读取配置，可用 --no-send-feishu 临时关闭）",
    )
    parser.add_argument("--send-poster", action="store_true", help="发送海报图片")
    parser.add_argument("--chat-id", action="append", default=[])
    parser.add_argument("--official", action="store_true", help="正式运行：要求 clean worktree、strict timeline、snapshot 和 cutoff")
    parser.add_argument("--strict-timeline", action="store_true")
    parser.add_argument("--data-snapshot-id", default="")
    parser.add_argument("--cutoff-time", default="", help="ISO-8601 数据截止时间")
    parser.add_argument("--model-version", default="")
    parser.add_argument("--cost-bps", type=float, default=14.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(Path(args.config))
    if args.list_models:
        for key, item in (config.get("models") or {}).items():
            aliases = "、".join(item.get("aliases") or [])
            print(f"{key}\t{item.get('mode')}\t{item.get('title')}\t{aliases}")
        return 0
    if not args.model:
        raise SystemExit("请指定 --model，或用 --list-models 查看可用模型。")
    result = run_pipeline(args)
    pipeline = result.get("pipeline") or {}
    print(
        json.dumps(
            {
                "status": result.get("status") or "ok",
                "mode": result.get("mode") or pipeline.get("mode"),
                "trade_date": result.get("trade_date") or pipeline.get("trade_date"),
                "total_picks": result.get("total_picks", len(result.get("picks") or [])),
                "run_dir": pipeline.get("run_dir") or result.get("run_dir"),
                "report_path": pipeline.get("markdown_path"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
