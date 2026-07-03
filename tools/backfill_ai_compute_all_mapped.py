#!/usr/bin/env python3
"""Batch backfill structured business-tag data for all mapped stocks.

This script uses local PostgreSQL source tables. It does not fabricate missing
evidence and does not call external APIs. For every mapping in
business_tag_mapping, or one selected chain_id, it upserts:
- L8 evidence events
- L8 evidence status
- stage tracking
- three-high scores
- expectation-gap scores
- revenue_ratio when fina_mainbz can support a business-relevant segment
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import argparse
from collections import defaultdict
from datetime import date
from typing import Any

import psycopg2
import psycopg2.extras


DSN = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
TRADE_DATE = date(2026, 7, 2)
START_DATE = date(2016, 1, 1)

DIMENSIONS = {
    "research_progress": {
        "name": "研发进展",
        "keywords": ["研发", "开发", "预研", "技术突破", "技术方向", "布局", "技术创新", "研发投入"],
    },
    "prototype_delivery": {
        "name": "样机或小批量交付",
        "keywords": ["样机", "样品", "送样", "小批量", "试制", "交付", "供应"],
    },
    "customer_validation": {
        "name": "客户验证",
        "keywords": ["客户验证", "验证", "测试", "认证", "导入", "试用", "供应链", "重点客户"],
    },
    "order_award": {
        "name": "订单或中标",
        "keywords": ["订单", "中标", "定点", "合同", "采购", "框架协议"],
    },
    "capacity_mass_production": {
        "name": "产线建设或量产",
        "keywords": ["量产", "产线", "扩产", "投产", "产能", "基地", "出货", "起量", "释放", "生产"],
    },
    "revenue_margin": {
        "name": "收入和毛利改善",
        "keywords": ["收入", "营收", "毛利", "毛利率", "业绩", "利润", "高增", "增长", "贡献", "放量"],
    },
    "patent_standard": {
        "name": "专利与标准",
        "keywords": ["专利", "标准", "知识产权", "认证", "壁垒", "独家", "自主知识产权"],
    },
}

BUSINESS_KEYWORDS = {
    "ai_compute_hardware": ["芯片", "服务器", "光模块", "光芯片", "激光", "GPU", "ASIC", "PCB", "交换机", "数据中心", "算力", "通信"],
    "ai_compute_software": ["软件", "平台", "调度", "操作系统", "数据库", "中间件", "大模型", "算法", "AI"],
    "ai_compute_application": ["应用", "解决方案", "行业", "智能", "AI", "数据中心", "云"],
    "chain_ai_compute": ["AI", "算力", "数据中心", "云", "芯片", "服务器", "光模块", "软件", "通信"],
}

MAINBZ_EXCLUDE_TERMS = [
    "直销",
    "经销",
    "中国大陆",
    "国外",
    "销售模式",
    "其他业务",
    "其他类",
    "其他",
    "小家电",
]

MAINBZ_STRONG_TERMS = [
    "数据中心",
    "数通",
    "AI",
    "算力",
    "光模块",
    "光芯片",
    "激光",
    "CW",
    "服务器",
    "GPU",
    "ASIC",
    "高速",
    "CPO",
    "LPO",
    "云",
]


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:18]}"


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def text(value: Any) -> str:
    return "" if value is None else str(value)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def path_name(path: Any, layer: str) -> str:
    if not isinstance(path, list):
        return ""
    for item in path:
        if isinstance(item, dict) and item.get("layer") == layer:
            return text(item.get("name"))
    return ""


def terms_for_mapping(mapping: dict[str, Any]) -> list[str]:
    path = mapping.get("l1_l8_path") or []
    raw_terms = [
        mapping.get("tag_name"),
        path_name(path, "L4"),
        path_name(path, "L5"),
        path_name(path, "L6"),
        path_name(path, "L7"),
    ]
    raw_terms.extend(BUSINESS_KEYWORDS.get(mapping.get("node_id"), []))
    terms: list[str] = []
    for term in raw_terms:
        for piece in re.split(r"[/、/（）()｜|\\s]+", text(term)):
            piece = piece.strip()
            if len(piece) >= 2 and piece not in terms and not piece.startswith("公司业务标签"):
                terms.append(piece)
    return terms[:24]


def contains_any(content: str, keywords: list[str]) -> bool:
    return any(k and k in content for k in keywords)


def is_relevant_mainbz_item(item: str, terms: list[str]) -> bool:
    if not item or contains_any(item, MAINBZ_EXCLUDE_TERMS):
        return False
    if contains_any(item, MAINBZ_STRONG_TERMS):
        return True
    # Allow exact product/node terms, but avoid broad terms that over-match
    # unrelated product lines such as "小家电控制芯片".
    broad_terms = {"芯片", "平台", "解决方案", "通信", "设备", "产品", "行业"}
    return any(term in item for term in terms if term not in broad_terms)


def evidence_type_for_text(content: str) -> list[str]:
    hits = []
    for dim, meta in DIMENSIONS.items():
        if contains_any(content, meta["keywords"]):
            hits.append(dim)
    return hits


def fetch_all(cur, sql: str, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def batch_event_delete_sql(chain_scoped: bool) -> str:
    chain_filter = "AND m.chain_id = %s" if chain_scoped else ""
    return f"""
            DELETE FROM business_tag_evidence_events e
            USING business_tag_mapping m
            WHERE e.mapping_id = m.mapping_id
              {chain_filter}
              AND e.source_type LIKE 'batch_10y_%%'
              AND NOT EXISTS (
                  SELECT 1
                  FROM evidence_extracted_facts f
                  WHERE f.evidence_event_id = e.event_id
              )
            """


def event(
    mapping: dict[str, Any],
    evidence_type: str,
    event_date,
    source_type: str,
    source_id: str,
    title: str,
    excerpt: str,
    impact: list[str],
    confidence: float,
) -> dict[str, Any]:
    event_id = stable_id("BATCH10Y", mapping["mapping_id"], evidence_type, source_type, source_id, title)
    return {
        "event_id": event_id,
        "mapping_id": mapping["mapping_id"],
        "code": mapping["code"],
        "node_id": mapping["node_id"],
        "event_date": event_date,
        "source_type": source_type,
        "source_id": source_id,
        "title": title[:500],
        "excerpt": excerpt[:3000],
        "original_url": None,
        "evidence_type": evidence_type,
        "impact_dimensions": as_json(impact),
        "confidence": confidence,
        "review_status": "pending_review",
        "stage_before": as_json({}),
        "stage_after": as_json({}),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chain-id",
        default=None,
        help="只更新指定 chain_id；默认更新 business_tag_mapping 中所有已映射股票",
    )
    args = parser.parse_args()
    chain_id = args.chain_id

    with psycopg2.connect(DSN) as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        mapping_where = "WHERE chain_id=%s" if chain_id else ""
        mapping_params = (chain_id,) if chain_id else ()
        mappings = fetch_all(
            cur,
            f"""
            SELECT mapping_id, code, node_id, tag_name, l1_l8_path, confidence, status
            FROM business_tag_mapping
            {mapping_where}
            ORDER BY code, node_id, mapping_id
            """,
            mapping_params,
        )
        codes = sorted({row["code"] for row in mappings})

        profiles = {
            row["code"]: row
            for row in fetch_all(
                cur,
                """
                SELECT code, full_name, main_business, introduction, updated_at
                FROM stock_profiles
                WHERE code = ANY(%s)
                """,
                (codes,),
            )
        }
        stocks = {
            row["code"]: row
            for row in fetch_all(
                cur,
                "SELECT code, name, industry, pe_ratio, pb_ratio FROM stocks WHERE code = ANY(%s)",
                (codes,),
            )
        }
        indicators_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in fetch_all(
            cur,
            """
            SELECT code, end_date, gross_margin, net_margin, revenue_growth, profit_growth, roe, roa
            FROM financial_indicator
            WHERE code = ANY(%s) AND end_date >= %s
            ORDER BY code, end_date
            """,
            (codes, START_DATE),
        ):
            indicators_by_code[row["code"]].append(row)

        incomes_by_code: dict[str, dict[Any, float]] = defaultdict(dict)
        for row in fetch_all(
            cur,
            """
            SELECT code, end_date, total_revenue
            FROM financial_income
            WHERE code = ANY(%s) AND end_date >= %s
            ORDER BY code, end_date
            """,
            (codes, START_DATE),
        ):
            incomes_by_code[row["code"]][row["end_date"]] = as_float(row.get("total_revenue"))

        mainbz_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in fetch_all(
            cur,
            """
            SELECT code, end_date, biz_item, biz_income, biz_ratio
            FROM fina_mainbz
            WHERE code = ANY(%s) AND end_date >= %s AND biz_income IS NOT NULL
            ORDER BY code, end_date DESC, biz_income DESC
            """,
            (codes, START_DATE),
        ):
            mainbz_by_code[row["code"]].append(row)

        qa_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in fetch_all(
            cur,
            """
            SELECT id, code, pub_date, question, answer
            FROM interact_qa
            WHERE code = ANY(%s) AND pub_date >= %s
            ORDER BY code, pub_date DESC
            """,
            (codes, START_DATE),
        ):
            qa_by_code[row["code"]].append(row)

        reports_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in fetch_all(
            cur,
            """
            SELECT code, pub_date, title, broker, rating, target_price
            FROM research_reports_tushare
            WHERE code = ANY(%s) AND pub_date >= %s
            ORDER BY code, pub_date DESC
            """,
            (codes, START_DATE),
        ):
            reports_by_code[row["code"]].append(row)

        forecasts_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in fetch_all(
            cur,
            """
            SELECT code, end_date, forecast_type, forecast_net_profit
            FROM forecast_data
            WHERE code = ANY(%s) AND end_date >= %s
            ORDER BY code, end_date DESC
            """,
            (codes, START_DATE),
        ):
            forecasts_by_code[row["code"]].append(row)

        broker_count_by_code = {
            row["code"]: int(row["cnt"])
            for row in fetch_all(
                cur,
                """
                SELECT code, count(*) AS cnt
                FROM broker_recommend
                WHERE code = ANY(%s) AND month >= '201601'
                GROUP BY code
                """,
                (codes,),
            )
        }
        moneyflow_by_code = {
            row["code"]: row
            for row in fetch_all(
                cur,
                """
                SELECT code, count(*) AS row_count,
                       sum(coalesce(net_mf_amount, 0)) FILTER (WHERE trade_date >= DATE '2026-01-01') AS net_mf_ytd,
                       avg(coalesce(net_mf_amount, 0)) FILTER (WHERE trade_date >= DATE '2026-01-01') AS avg_net_mf_ytd
                FROM moneyflow
                WHERE code = ANY(%s)
                GROUP BY code
                """,
                (codes,),
            )
        }
        daily_count_by_code = {
            row["code"]: int(row["cnt"])
            for row in fetch_all(
                cur,
                "SELECT code, count(*) AS cnt FROM daily_kline WHERE code = ANY(%s) GROUP BY code",
                (codes,),
            )
        }

        all_events: list[dict[str, Any]] = []
        status_rows = []
        score_rows = []
        stage_rows = []
        gap_rows = []
        mapping_updates = []
        processed = 0

        for mapping in mappings:
            processed += 1
            code = mapping["code"]
            terms = terms_for_mapping(mapping)
            profile = profiles.get(code)
            indicators = indicators_by_code.get(code, [])
            latest_indicator = indicators[-1] if indicators else {}
            latest_revenue_growth = as_float(latest_indicator.get("revenue_growth"))
            latest_gross_margin = as_float(latest_indicator.get("gross_margin"))
            latest_net_margin = as_float(latest_indicator.get("net_margin"))

            events: list[dict[str, Any]] = []
            if profile:
                content = f"{profile.get('main_business') or ''}。{profile.get('introduction') or ''}"
                if contains_any(content, terms):
                    event_date = profile["updated_at"].date() if hasattr(profile.get("updated_at"), "date") else None
                    for dim in evidence_type_for_text(content):
                        if dim in {"prototype_delivery", "customer_validation", "order_award"}:
                            continue
                        events.append(
                            event(
                                mapping,
                                dim,
                                event_date,
                                "batch_10y_profile",
                                f"{code}-profile",
                                f"{code} 公司资料匹配 {DIMENSIONS[dim]['name']}",
                                content,
                                ["business_tag", dim],
                                0.68,
                            )
                        )

            relevant_mainbz = []
            for row in mainbz_by_code.get(code, []):
                item = text(row.get("biz_item"))
                if not is_relevant_mainbz_item(item, terms):
                    continue
                income = as_float(row.get("biz_income"))
                total_revenue = incomes_by_code.get(code, {}).get(row.get("end_date")) or 0
                ratio = income / total_revenue * 100 if total_revenue > 0 else as_float(row.get("biz_ratio"), 0)
                relevant_mainbz.append((row, ratio))
                events.append(
                    event(
                        mapping,
                        "revenue_margin",
                        row.get("end_date"),
                        "batch_10y_mainbz",
                        f"{code}-{row.get('end_date')}-{item}",
                        f"{row.get('end_date')} 主营构成：{item}",
                        f"{item}收入={income:.2f}元，占当期总营收约{ratio:.2f}%。用于业务标签收入占比验证；不代表业务毛利率。",
                        ["growth", "profit", "business_split"],
                        0.78 if ratio >= 20 else 0.66,
                    )
                )
            latest_revenue_ratio = round(float(relevant_mainbz[0][1]), 4) if relevant_mainbz else None

            seen_qa: set[str] = set()
            for row in qa_by_code.get(code, [])[:80]:
                content = f"{row.get('question') or ''} {row.get('answer') or ''}"
                if not contains_any(content, terms):
                    continue
                key = hashlib.sha1(content.encode("utf-8")).hexdigest()
                if key in seen_qa:
                    continue
                seen_qa.add(key)
                for dim in evidence_type_for_text(content):
                    events.append(
                        event(
                            mapping,
                            dim,
                            row.get("pub_date"),
                            "batch_10y_interact_qa",
                            str(row.get("id") or key),
                            text(row.get("question"))[:300],
                            text(row.get("answer")),
                            [dim],
                            0.55,
                        )
                    )

            for row in reports_by_code.get(code, [])[:80]:
                title = text(row.get("title"))
                if not contains_any(title, terms):
                    continue
                dims = evidence_type_for_text(title) or ["revenue_margin"]
                for dim in dims:
                    if dim in {"customer_validation", "order_award"} and not contains_any(title, DIMENSIONS[dim]["keywords"]):
                        continue
                    events.append(
                        event(
                            mapping,
                            dim,
                            row.get("pub_date"),
                            "batch_10y_research_title",
                            stable_id("report", code, row.get("pub_date"), title),
                            title,
                            f"{row.get('broker') or ''}_{title}，评级={row.get('rating') or ''}，目标价={row.get('target_price') or ''}",
                            [dim],
                            0.56,
                        )
                    )

            for row in forecasts_by_code.get(code, [])[:12]:
                events.append(
                    event(
                        mapping,
                        "revenue_margin",
                        row.get("end_date"),
                        "batch_10y_forecast",
                        f"{code}-{row.get('end_date')}-{row.get('forecast_type')}",
                        f"{row.get('end_date')} 业绩预告：{row.get('forecast_type')}",
                        f"业绩预告类型={row.get('forecast_type')}，预告净利润={row.get('forecast_net_profit')}",
                        ["growth", "profit"],
                        0.62,
                    )
                )

            for row in indicators[-12:]:
                rg = as_float(row.get("revenue_growth"))
                gm = as_float(row.get("gross_margin"))
                nm = as_float(row.get("net_margin"))
                if rg >= 50 or gm >= 45 or nm >= 20:
                    events.append(
                        event(
                            mapping,
                            "revenue_margin",
                            row.get("end_date"),
                            "batch_10y_financial_indicator",
                            f"{code}-{row.get('end_date')}",
                            f"{row.get('end_date')} 财务指标显示增长/盈利改善",
                            f"营收增速={rg:.2f}%，毛利率={gm:.2f}%，净利率={nm:.2f}%，ROE={as_float(row.get('roe')):.2f}%",
                            ["growth", "profit"],
                            0.70,
                        )
                    )

            event_ids_by_dim: dict[str, list[str]] = defaultdict(list)
            for ev in events:
                event_ids_by_dim[ev["evidence_type"]].append(ev["event_id"])
            matched_dims = sum(1 for ids in event_ids_by_dim.values() if ids)
            source_count = sum(len(ids) for ids in event_ids_by_dim.values())
            all_ids = sorted({eid for ids in event_ids_by_dim.values() for eid in ids})

            for dim_id, meta in DIMENSIONS.items():
                ids = event_ids_by_dim.get(dim_id, [])
                status_rows.append(
                    (
                        f"L8STATUS-{mapping['mapping_id']}-{dim_id}",
                        mapping["mapping_id"],
                        code,
                        mapping["node_id"],
                        dim_id,
                        meta["name"],
                        "matched" if ids else "missing",
                        as_json(ids),
                        len(ids),
                        f"近十年本地资料已匹配 {len(ids)} 条{meta['name']}证据"
                        if ids
                        else f"近十年本地资料暂未命中{meta['name']}，需补公告、年报、客户验证或订单证据",
                        as_json(meta["keywords"]),
                        TRADE_DATE,
                    )
                )

            growth_score = min(100.0, max(20.0, latest_revenue_growth * 0.22 + 35.0))
            profit_score = min(100.0, latest_gross_margin * 0.65 + latest_net_margin * 0.55) if indicators else None
            moat_score = 62.0 if event_ids_by_dim.get("patent_standard") else 45.0 + as_float(mapping.get("confidence")) * 15
            stage_score = 58.0 if event_ids_by_dim.get("capacity_mass_production") else 38.0 if event_ids_by_dim.get("revenue_margin") else 15.0
            evidence_score = min(100.0, matched_dims / 7 * 70 + min(source_count, 12) * 2.5)
            total_score = round(
                growth_score * 0.28
                + (profit_score or 0) * 0.25
                + moat_score * 0.20
                + stage_score * 0.15
                + evidence_score * 0.12,
                2,
            )
            money = moneyflow_by_code.get(code, {})
            detail = {
                "source": "batch_ai_compute_10y_local",
                "score_unit": "business_tag",
                "inference_only": False,
                "mapping_status": mapping.get("status"),
                "data_window": {
                    "start": str(START_DATE),
                    "end": str(TRADE_DATE),
                    "daily_kline_rows": daily_count_by_code.get(code, 0),
                    "moneyflow_rows": int(money.get("row_count") or 0),
                    "financial_indicator_rows": len(indicators),
                    "financial_income_rows": len(incomes_by_code.get(code, {})),
                    "forecast_rows": len(forecasts_by_code.get(code, [])),
                    "fina_mainbz_relevant_rows": len(relevant_mainbz),
                    "interact_qa_rows": len(qa_by_code.get(code, [])),
                    "research_report_rows": len(reports_by_code.get(code, [])),
                    "broker_recommend_rows": broker_count_by_code.get(code, 0),
                },
                "revenue_supported": latest_revenue_ratio is not None,
                "business_revenue_ratio_pct": latest_revenue_ratio,
                "profit_supported": profit_score is not None,
                "profit_score_status": "company_level_margin" if profit_score is not None else "unavailable",
                "business_split_gap": "business revenue ratio supported by fina_mainbz; product-level gross margin remains unavailable"
                if latest_revenue_ratio is not None
                else "business-specific revenue and gross margin split not supported by fina_mainbz",
                "matched_l8_dimensions": matched_dims,
                "candidate_evidence_count": source_count,
                "requires_original_evidence": True,
                "moneyflow_net_ytd": as_float(money.get("net_mf_ytd")),
                "moneyflow_avg_net_ytd": as_float(money.get("avg_net_mf_ytd")),
            }
            score_rows.append(
                (
                    f"THREE-HIGH-{mapping['mapping_id']}-{TRADE_DATE}",
                    mapping["mapping_id"],
                    TRADE_DATE,
                    round(growth_score, 2),
                    round(profit_score, 2) if profit_score is not None else None,
                    round(moat_score, 2),
                    round(stage_score, 2),
                    round(evidence_score, 2),
                    total_score,
                    as_json(detail),
                    as_json(all_ids),
                )
            )

            research_stage = "R2" if event_ids_by_dim.get("research_progress") else "R1" if mapping.get("status") == "verified" else "R0"
            commercial_stage = "C2" if event_ids_by_dim.get("capacity_mass_production") else "C1" if event_ids_by_dim.get("revenue_margin") else "C0"
            stage_reason = (
                f"批量近十年资料重算：L8命中{matched_dims}/7，证据{source_count}条；"
                f"收入占比={latest_revenue_ratio if latest_revenue_ratio is not None else '未拆出'}，"
                "阶段仍需人工复核客户验证、订单或公告原文。"
            )
            source_event_id = all_ids[0] if all_ids else None
            stage_rows.append(
                (
                    f"STAGE-{mapping['mapping_id']}-BATCH10Y",
                    mapping["mapping_id"],
                    TRADE_DATE,
                    research_stage,
                    commercial_stage,
                    stage_reason,
                    source_event_id,
                    TRADE_DATE,
                    "pending_review",
                )
            )

            report_count = len(reports_by_code.get(code, []))
            broker_count = broker_count_by_code.get(code, 0)
            market_expectation_score = min(100.0, report_count * 2.0 + broker_count * 1.2 + max(0, as_float(stocks.get(code, {}).get("pe_ratio")) / 20))
            actual_progress_score = min(100.0, total_score + matched_dims * 4)
            evidence_delta_score = min(100.0, source_count * 2.2)
            risk_penalty_score = 18.0 if as_float(stocks.get(code, {}).get("pe_ratio")) > 150 else 8.0
            gap_score = round(actual_progress_score + evidence_delta_score * 0.35 - market_expectation_score * 0.45 - risk_penalty_score, 2)
            gap_rows.append(
                (
                    f"GAP-{mapping['mapping_id']}-{TRADE_DATE}",
                    mapping["mapping_id"],
                    TRADE_DATE,
                    round(actual_progress_score, 2),
                    round(market_expectation_score, 2),
                    round(evidence_delta_score, 2),
                    round(risk_penalty_score, 2),
                    gap_score,
                    "positive_evidence_delta" if gap_score >= 0 else "high_expectation_needs_hard_evidence",
                    as_json(
                        {
                            "source": "batch_ai_compute_10y_local",
                            "actual_progress_inputs": {
                                "matched_l8_dimensions": matched_dims,
                                "source_evidence_count": source_count,
                                "business_revenue_ratio_pct": latest_revenue_ratio,
                                "latest_revenue_growth_pct": latest_revenue_growth,
                                "latest_gross_margin_pct": latest_gross_margin,
                                "moneyflow_net_ytd": as_float(money.get("net_mf_ytd")),
                            },
                            "market_expectation_inputs": {
                                "research_report_count": report_count,
                                "broker_recommend_count": broker_count,
                                "pe_ratio": as_float(stocks.get(code, {}).get("pe_ratio")),
                                "pb_ratio": as_float(stocks.get(code, {}).get("pb_ratio")),
                            },
                        }
                    ),
                    as_json(all_ids),
                )
            )

            mapping_updates.append((latest_revenue_ratio, as_json(all_ids), mapping["mapping_id"]))
            all_events.extend(events)

        # Clear previous batch-generated events and dependent stage refs.
        cur.execute(
            f"""
            UPDATE business_tag_stage_tracking st
            SET source_event_id = NULL
            FROM business_tag_mapping m
            WHERE st.mapping_id = m.mapping_id
            {"AND m.chain_id = %s" if chain_id else ""}
            """,
            mapping_params,
        )
        cur.execute(batch_event_delete_sql(chain_scoped=bool(chain_id)), mapping_params)

        psycopg2.extras.execute_batch(
            cur,
            """
            INSERT INTO business_tag_evidence_events (
                event_id, mapping_id, code, node_id, event_date, source_type, source_id,
                title, excerpt, original_url, evidence_type, impact_dimensions, confidence,
                review_status, stage_before, stage_after
            ) VALUES (
                %(event_id)s, %(mapping_id)s, %(code)s, %(node_id)s, %(event_date)s,
                %(source_type)s, %(source_id)s, %(title)s, %(excerpt)s, %(original_url)s,
                %(evidence_type)s, %(impact_dimensions)s::jsonb, %(confidence)s,
                %(review_status)s, %(stage_before)s::jsonb, %(stage_after)s::jsonb
            )
            ON CONFLICT (event_id) DO UPDATE SET
                title = EXCLUDED.title,
                excerpt = EXCLUDED.excerpt,
                confidence = EXCLUDED.confidence,
                review_status = EXCLUDED.review_status
            """,
            all_events,
            page_size=1000,
        )

        psycopg2.extras.execute_batch(
            cur,
            """
            INSERT INTO business_tag_l8_evidence_status (
                status_id, mapping_id, code, node_id, dimension_id, dimension_name,
                source_status, evidence_event_ids, evidence_count, evidence_summary,
                required_keywords, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s)
            ON CONFLICT (mapping_id, dimension_id) DO UPDATE SET
                source_status = EXCLUDED.source_status,
                evidence_event_ids = EXCLUDED.evidence_event_ids,
                evidence_count = EXCLUDED.evidence_count,
                evidence_summary = EXCLUDED.evidence_summary,
                required_keywords = EXCLUDED.required_keywords,
                updated_at = EXCLUDED.updated_at
            """,
            status_rows,
            page_size=1000,
        )

        psycopg2.extras.execute_batch(
            cur,
            """
            INSERT INTO business_tag_three_high_scores (
                score_id, mapping_id, trade_date, growth_score, profit_score, moat_score,
                stage_score, evidence_score, total_score, score_detail, evidence_ids
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
            ON CONFLICT (mapping_id, trade_date) DO UPDATE SET
                growth_score = EXCLUDED.growth_score,
                profit_score = EXCLUDED.profit_score,
                moat_score = EXCLUDED.moat_score,
                stage_score = EXCLUDED.stage_score,
                evidence_score = EXCLUDED.evidence_score,
                total_score = EXCLUDED.total_score,
                score_detail = EXCLUDED.score_detail,
                evidence_ids = EXCLUDED.evidence_ids
            """,
            score_rows,
            page_size=1000,
        )

        psycopg2.extras.execute_batch(
            cur,
            """
            INSERT INTO business_tag_stage_tracking (
                stage_id, mapping_id, trade_date, research_stage, commercialization_stage,
                stage_reason, source_event_id, last_stage_change_date, review_status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (stage_id) DO UPDATE SET
                research_stage = EXCLUDED.research_stage,
                commercialization_stage = EXCLUDED.commercialization_stage,
                stage_reason = EXCLUDED.stage_reason,
                source_event_id = EXCLUDED.source_event_id,
                last_stage_change_date = EXCLUDED.last_stage_change_date,
                review_status = EXCLUDED.review_status
            """,
            stage_rows,
            page_size=1000,
        )
        cur.execute(
            f"""
            DELETE FROM business_tag_stage_tracking st
            USING business_tag_mapping m
            WHERE st.mapping_id = m.mapping_id
              {"AND m.chain_id = %s" if chain_id else ""}
              AND st.trade_date = %s
              AND st.stage_id LIKE 'STAGE-%%-INF'
            """,
            (*mapping_params, TRADE_DATE),
        )

        psycopg2.extras.execute_batch(
            cur,
            """
            INSERT INTO business_tag_expectation_gap_scores (
                gap_id, mapping_id, trade_date, actual_progress_score, market_expectation_score,
                evidence_delta_score, risk_penalty_score, expectation_gap_score, gap_type,
                score_detail, evidence_ids
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
            ON CONFLICT (mapping_id, trade_date) DO UPDATE SET
                actual_progress_score = EXCLUDED.actual_progress_score,
                market_expectation_score = EXCLUDED.market_expectation_score,
                evidence_delta_score = EXCLUDED.evidence_delta_score,
                risk_penalty_score = EXCLUDED.risk_penalty_score,
                expectation_gap_score = EXCLUDED.expectation_gap_score,
                gap_type = EXCLUDED.gap_type,
                score_detail = EXCLUDED.score_detail,
                evidence_ids = EXCLUDED.evidence_ids
            """,
            gap_rows,
            page_size=1000,
        )

        psycopg2.extras.execute_batch(
            cur,
            """
            UPDATE business_tag_mapping
            SET revenue_ratio = COALESCE(%s, revenue_ratio),
                evidence_ids = %s::jsonb,
                updated_at = now()
            WHERE mapping_id = %s
            """,
            mapping_updates,
            page_size=1000,
        )

        conn.commit()
        print(
            json.dumps(
                {
                    "scope": chain_id or "all_chains",
                    "processed_mappings": processed,
                    "processed_companies": len(codes),
                    "generated_events": len(all_events),
                    "status_rows": len(status_rows),
                    "score_rows": len(score_rows),
                    "stage_rows": len(stage_rows),
                    "gap_rows": len(gap_rows),
                    "revenue_ratio_supported_mappings": sum(1 for r in mapping_updates if r[0] is not None),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
