#!/usr/bin/env python3
"""Calibrate supply-chain score weights with walk-forward Rank IC analysis.

对 as-of strict 回填区间内的三高/预期差分数做维度级 Rank IC(Spearman)分析:
- 按 trade_date 分组计算每个维度分数与前向 5/10/20 日收益的 Spearman 相关,
  再对日期取均值(IC)、均值/标准差(ICIR)、IC>0 占比;
- walk-forward 切分:前 60% 日期训练窗、后 40% 验证窗,两窗分别报告,
  防止单一窗口的过拟合幻觉;
- 权重建议(保守):某维度在两窗 IC 均 <= 0 才下调;只有两窗 IC 均 > 0 的
  维度才接收让出的权重;任何一窗方差为零或样本不足的维度不参与调整;
- 默认只出报告不改公式,--apply-weights 才写回
  packages/kronos-factors/kronos_factors/engine/supply_chain_scoring.py
  的 THREE_HIGH_WEIGHTS 常量(保留旧值注释 + docstring 变更记录)。

如实面对数据现状:strict 分数区分度可能很低(证据审批集中在 2026-07,
历史日期 evidence/stage 趋近常数),IC 不可信时结论就是"维持原权重"。
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[1]
SCORING_PATH = REPO_ROOT / "packages" / "kronos-factors" / "kronos_factors" / "engine" / "supply_chain_scoring.py"
OUTPUT_DIR = REPO_ROOT / "outputs"

STRICT_VERSION = "supply-chain-history-asof-v2-strict"

# IC 分析维度:列名 -> 来源表/表达式
IC_DIMENSIONS = {
    "growth_score": "t.growth_score",
    "profit_score": "t.profit_score",
    "moat_score": "t.moat_score",
    "stage_score": "t.stage_score",
    "evidence_score": "t.evidence_score",
    "total_score": "t.total_score",
    "expectation_gap_score": "g.expectation_gap_score",
}

# 参与权重建议的三高公式维度( prosperity 从 score_detail 取)
WEIGHT_DIMENSIONS = ["growth", "profit", "moat", "stage", "evidence", "prosperity"]
DIM_TO_IC_COLUMN = {
    "growth": "growth_score",
    "profit": "profit_score",
    "moat": "moat_score",
    "stage": "stage_score",
    "evidence": "evidence_score",
    "prosperity": "prosperity_score",
}

HOLD_DAYS = [5, 10, 20]
TRAIN_RATIO = 0.60
MIN_DATES_PER_WINDOW = 20   # 窗口内可用 IC 日期少于此值 → 证据不足
MIN_PAIRS_PER_DAY = 20      # 单日有效 (score, return) 对少于此值 → 当日不计 IC
MIN_DAY_STD = 1e-9          # 单日分数/收益方差为零 → Spearman 不可定义


def _load_scores(cur) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT g.mapping_id, g.trade_date,
               split_part(b.code, '.', 1) AS base_code,
               t.growth_score, t.profit_score, t.moat_score, t.stage_score,
               t.evidence_score, t.total_score,
               g.expectation_gap_score,
               coalesce((g.score_detail->>'prosperity_score')::numeric, 50) AS prosperity_score
        FROM business_tag_expectation_gap_scores g
        JOIN business_tag_three_high_scores t
          ON t.mapping_id = g.mapping_id AND t.trade_date = g.trade_date
        JOIN business_tag_mapping b ON b.mapping_id = g.mapping_id
        WHERE g.score_detail->>'version' = %s
        ORDER BY g.trade_date, g.mapping_id
        """,
        (STRICT_VERSION,),
    )
    return [dict(row) for row in cur.fetchall()]


def _load_forward_returns(cur, codes: list[str], start_date: date, end_date: date, hold_days: list[int]) -> dict[tuple[str, str], dict[int, float]]:
    """(base_code, trade_date) -> {hold: 前向收益%},口径与回测一致(收盘→第 N 个交易日收盘)。"""
    if not codes:
        return {}
    kline_end = (end_date + timedelta(days=max(hold_days) * 2 + 20)).isoformat()
    ret_cols = ", ".join(
        f"(fwd_{days} / close - 1.0) * 100.0 AS ret_{days}" for days in hold_days
    )
    lead_cols = ", ".join(
        f"lead(close, {days}) OVER w AS fwd_{days}" for days in hold_days
    )
    cur.execute(
        f"""
        SELECT code, trade_date, {ret_cols}
        FROM (
            SELECT code, trade_date, close, {lead_cols}
            FROM daily_kline
            WHERE code = ANY(%s) AND trade_date BETWEEN %s AND %s
              AND close IS NOT NULL AND close > 0
            WINDOW w AS (PARTITION BY code ORDER BY trade_date)
        ) k
        WHERE trade_date BETWEEN %s AND %s
        """,
        (codes, start_date.isoformat(), kline_end, start_date.isoformat(), end_date.isoformat()),
    )
    result: dict[tuple[str, str], dict[int, float]] = {}
    for row in cur.fetchall():
        key = (str(row["code"]), str(row["trade_date"])[:10])
        result[key] = {
            days: round(float(row[f"ret_{days}"]), 4)
            for days in hold_days
            if row[f"ret_{days}"] is not None
        }
    return result


def _daily_rank_ics(pairs: list[tuple[float, float]]) -> float | None:
    """单日 Spearman IC;方差为零或样本不足返回 None。"""
    if len(pairs) < MIN_PAIRS_PER_DAY:
        return None
    scores = [p[0] for p in pairs]
    rets = [p[1] for p in pairs]
    if (max(scores) - min(scores)) < MIN_DAY_STD or (max(rets) - min(rets)) < MIN_DAY_STD:
        return None
    result = spearmanr(scores, rets)
    value = float(result.statistic)
    return value if value == value else None  # NaN 过滤


def _window_ic(rows_by_date: dict[str, list[dict[str, Any]]], dates: list[str], dim: str, hold: int) -> dict[str, Any]:
    daily_ics: list[float] = []
    for day in dates:
        pairs = [
            (float(row[dim]), float(row["fwd_returns"][hold]))
            for row in rows_by_date.get(day, [])
            if row.get(dim) is not None and hold in row.get("fwd_returns", {})
        ]
        ic = _daily_rank_ics(pairs)
        if ic is not None:
            daily_ics.append(ic)
    if not daily_ics:
        return {"dates": 0, "ic": None, "icir": None, "ic_positive_ratio": None}
    mean_ic = sum(daily_ics) / len(daily_ics)
    variance = sum((v - mean_ic) ** 2 for v in daily_ics) / len(daily_ics)
    std_ic = variance ** 0.5
    return {
        "dates": len(daily_ics),
        "ic": round(mean_ic, 4),
        "icir": round(mean_ic / std_ic, 4) if std_ic > MIN_DAY_STD else None,
        "ic_positive_ratio": round(sum(1 for v in daily_ics if v > 0) / len(daily_ics), 4),
    }


def suggest_weights(
    current_weights: dict[str, float],
    train_ic: dict[str, float | None],
    val_ic: dict[str, float | None],
) -> dict[str, Any]:
    """保守调权建议:两窗 IC 均 <=0 的维度减半,让出的权重按训练窗 IC 比例
    分给两窗 IC 均 >0 的维度;无可接收维度或证据不足则维持原权重。"""
    down: list[str] = []
    up: list[str] = []
    insufficient: list[str] = []
    for dim in WEIGHT_DIMENSIONS:
        ic_col = DIM_TO_IC_COLUMN[dim]
        t = train_ic.get(ic_col)
        v = val_ic.get(ic_col)
        if t is None or v is None:
            insufficient.append(dim)
            continue
        if t <= 0 and v <= 0:
            down.append(dim)
        elif t > 0 and v > 0:
            up.append(dim)
    if not down or not up:
        return {
            "changed": False,
            "reason": (
                f"无需调整:down={down}, up={up}, 证据不足维度={insufficient};"
                "没有同时满足'两窗 IC<=0 让权'与'两窗 IC>0 接收'的组合。"
            ),
            "down": down,
            "up": up,
            "insufficient": insufficient,
            "weights": dict(current_weights),
        }
    freed = sum(current_weights[d] * 0.5 for d in down)
    up_ic_sum = sum(max(train_ic[DIM_TO_IC_COLUMN[d]], 0.0) for d in up)
    new_weights = dict(current_weights)
    for dim in down:
        new_weights[dim] = round(current_weights[dim] * 0.5, 4)
    for dim in up:
        share = max(train_ic[DIM_TO_IC_COLUMN[dim]], 0.0) / up_ic_sum if up_ic_sum > 0 else 1.0 / len(up)
        new_weights[dim] = round(current_weights[dim] + freed * share, 4)
    total = sum(new_weights.values())
    new_weights = {d: round(w / total, 4) for d, w in new_weights.items()}
    return {
        "changed": True,
        "reason": f"两窗 IC 均<=0 的维度 {down} 权重减半,让渡 {round(freed, 4)} 给两窗 IC 均>0 的 {up}(按训练窗 IC 比例),归一化到 1.0。",
        "down": down,
        "up": up,
        "insufficient": insufficient,
        "weights": new_weights,
    }


def apply_weights_to_scoring(new_weights: dict[str, float], report_note: str) -> None:
    """把新权重写回 supply_chain_scoring.py 的 THREE_HIGH_WEIGHTS 常量。

    保留旧值为注释,并在模块 docstring 变更记录追加一条。
    """
    text = SCORING_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"THREE_HIGH_WEIGHTS[^=]*=\s*\{[^}]*\}",
        text,
    )
    if not match:
        raise RuntimeError("THREE_HIGH_WEIGHTS constant not found in supply_chain_scoring.py")
    old_block = match.group(0)
    old_values = {
        dim: float(val)
        for dim, val in re.findall(r'"(\w+)":\s*([0-9.]+)', old_block.split("{", 1)[1])
    }
    lines = ["THREE_HIGH_WEIGHTS: dict[str, float] = {"]
    for dim in WEIGHT_DIMENSIONS:
        old = old_values.get(dim)
        comment = f"  # 原 {old}" if old is not None and abs(old - new_weights[dim]) > 1e-9 else ""
        lines.append(f'    "{dim}": {new_weights[dim]},{comment}')
    lines.append("}")
    new_block = "\n".join(lines)
    text = text.replace(old_block, new_block, 1)
    today = date.today().isoformat()
    changelog = (
        f"- {today}(阶段三B) 三高权重按 walk-forward IC 标定调整(--apply-weights):"
        f" {json.dumps(new_weights, ensure_ascii=False)};{report_note}\n"
    )
    marker = '"""\n\nfrom __future__ import annotations'
    if marker in text:
        text = text.replace(marker, changelog + '"""\n\nfrom __future__ import annotations', 1)
    SCORING_PATH.write_text(text, encoding="utf-8")


def run_calibration(pg_url: str, hold_days: list[int], apply_weights: bool) -> dict[str, Any]:
    import sys
    sys.path.insert(0, str(REPO_ROOT / "packages" / "kronos-factors"))
    from kronos_factors.engine.supply_chain_scoring import THREE_HIGH_WEIGHTS

    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = _load_scores(cur)
            if not rows:
                raise RuntimeError(f"no strict-version scores found (version={STRICT_VERSION})")
            dates = sorted({str(row["trade_date"])[:10] for row in rows})
            start = date.fromisoformat(dates[0])
            end = date.fromisoformat(dates[-1])
            codes = sorted({str(row["base_code"]) for row in rows})
            fwd = _load_forward_returns(cur, codes, start, end, hold_days)
    for row in rows:
        row["fwd_returns"] = fwd.get((str(row["base_code"]), str(row["trade_date"])[:10]), {})
    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_date.setdefault(str(row["trade_date"])[:10], []).append(row)

    split = max(1, int(len(dates) * TRAIN_RATIO))
    train_dates = dates[:split]
    val_dates = dates[split:]

    ic_table: dict[str, Any] = {}
    for dim in list(IC_DIMENSIONS) + ["prosperity_score"]:
        ic_table[dim] = {"train": {}, "validation": {}}
        for hold in hold_days:
            ic_table[dim]["train"][str(hold)] = _window_ic(rows_by_date, train_dates, dim, hold)
            ic_table[dim]["validation"][str(hold)] = _window_ic(rows_by_date, val_dates, dim, hold)

    # 权重建议以主口径 5 日前向收益为准
    primary_hold = str(hold_days[0])
    train_ic = {dim: ic_table[dim]["train"][primary_hold]["ic"] for dim in ic_table}
    val_ic = {dim: ic_table[dim]["validation"][primary_hold]["ic"] for dim in ic_table}
    suggestion = suggest_weights(dict(THREE_HIGH_WEIGHTS), train_ic, val_ic)

    evidence_notes: list[str] = []
    low_ic_dates = [
        dim for dim in ic_table
        if ic_table[dim]["train"][primary_hold]["dates"] < MIN_DATES_PER_WINDOW
        or ic_table[dim]["validation"][primary_hold]["dates"] < MIN_DATES_PER_WINDOW
    ]
    if low_ic_dates:
        evidence_notes.append(
            f"维度 {low_ic_dates} 在某窗口有效 IC 日期 < {MIN_DATES_PER_WINDOW}"
            "(strict 口径下区分度不足/方差为零),其 IC 不可信,已排除出调权依据。"
        )
    if not suggestion["changed"]:
        evidence_notes.append("当前证据不足以支持权重调整,维持原权重。")

    if apply_weights and suggestion["changed"]:
        apply_weights_to_scoring(suggestion["weights"], suggestion["reason"])
        evidence_notes.append("已通过 --apply-weights 写回 supply_chain_scoring.py THREE_HIGH_WEIGHTS(旧值保留为注释)。")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "score_version": STRICT_VERSION,
        "date_range": [dates[0], dates[-1]],
        "total_dates": len(dates),
        "train_dates": [train_dates[0], train_dates[-1], len(train_dates)],
        "validation_dates": [val_dates[0], val_dates[-1], len(val_dates)],
        "rows": len(rows),
        "codes": len(codes),
        "hold_days": hold_days,
        "primary_hold_days": int(primary_hold),
        "ic_table": ic_table,
        "current_weights": dict(THREE_HIGH_WEIGHTS),
        "suggestion": suggestion,
        "evidence_notes": evidence_notes,
    }


def write_report(payload: dict[str, Any]) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    json_path = OUTPUT_DIR / f"supply_chain_score_calibration_{stamp}.json"
    md_path = OUTPUT_DIR / f"supply_chain_score_calibration_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    primary = str(payload["primary_hold_days"])
    lines = [
        f"# 产业链分数标定报告({payload['generated_at'][:10]})",
        "",
        f"- 分数版本:`{payload['score_version']}`",
        f"- 区间:{payload['date_range'][0]} ~ {payload['date_range'][1]},共 {payload['total_dates']} 个交易日,{payload['rows']} 行,{payload['codes']} 只股票",
        f"- 训练窗:{payload['train_dates'][0]} ~ {payload['train_dates'][1]}({payload['train_dates'][2]} 日,前 60%)",
        f"- 验证窗:{payload['validation_dates'][0]} ~ {payload['validation_dates'][1]}({payload['validation_dates'][2]} 日,后 40%)",
        f"- 主口径:前向 {primary} 日收益的按日 Rank IC(Spearman)均值",
        "",
        f"## Rank IC 表(前向 {primary} 日)",
        "",
        "| 维度 | 训练 IC | 训练 ICIR | 训练 IC>0 | 训练日数 | 验证 IC | 验证 ICIR | 验证 IC>0 | 验证日数 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for dim, windows in payload["ic_table"].items():
        t = windows["train"][primary]
        v = windows["validation"][primary]
        fmt = lambda x: "—" if x is None else x
        lines.append(
            f"| {dim} | {fmt(t['ic'])} | {fmt(t['icir'])} | {fmt(t['ic_positive_ratio'])} | {t['dates']} "
            f"| {fmt(v['ic'])} | {fmt(v['icir'])} | {fmt(v['ic_positive_ratio'])} | {v['dates']} |"
        )
    lines += [
        "",
        "## 权重建议",
        "",
        f"- 当前权重:`{json.dumps(payload['current_weights'], ensure_ascii=False)}`",
        f"- 建议权重:`{json.dumps(payload['suggestion']['weights'], ensure_ascii=False)}`",
        f"- 是否建议调整:{'是' if payload['suggestion']['changed'] else '否(维持原权重)'}",
        f"- 理由:{payload['suggestion']['reason']}",
        "",
        "## 证据说明",
        "",
    ]
    lines += [f"- {note}" for note in payload["evidence_notes"]]
    lines += [
        "",
        "各持有期完整 IC 见同名 .json。",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward Rank IC calibration for supply-chain scores")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--hold-days", default="5,10,20")
    parser.add_argument("--apply-weights", action="store_true",
                        help="把建议权重写回 supply_chain_scoring.py(默认只出报告)")
    args = parser.parse_args()
    hold_days = [int(item.strip()) for item in args.hold_days.split(",") if item.strip()]
    payload = run_calibration(args.pg_url, hold_days, args.apply_weights)
    md_path, json_path = write_report(payload)
    print(json.dumps({"report_md": str(md_path), "report_json": str(json_path),
                      "suggestion": payload["suggestion"],
                      "evidence_notes": payload["evidence_notes"]}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
