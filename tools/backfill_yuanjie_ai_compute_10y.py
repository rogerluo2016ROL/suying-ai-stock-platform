#!/usr/bin/env python3
"""Backfill 688498 Yuanjie AI-compute business-tag evidence from local 10Y data.

The script only uses data already present in PostgreSQL. It upserts structured
L8 evidence, stage tracking, three-high scoring, and expectation-gap scoring
for the existing AI-compute mapping.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import date
from typing import Any

import psycopg2
import psycopg2.extras


DSN = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
CODE = "688498"
TRADE_DATE = date(2026, 7, 2)


DIMENSIONS = {
    "research_progress": {
        "name": "研发进展",
        "keywords": ["研发", "开发", "技术创新", "核心驱动力", "技术领先", "光芯片"],
    },
    "prototype_delivery": {
        "name": "样机或小批量交付",
        "keywords": ["样机", "样品", "送样", "小批量", "试制", "交付"],
    },
    "customer_validation": {
        "name": "客户验证",
        "keywords": ["客户验证", "验证", "测试", "认证", "导入", "试用"],
    },
    "order_award": {
        "name": "订单或中标",
        "keywords": ["订单", "中标", "定点", "合同", "采购", "框架协议"],
    },
    "capacity_mass_production": {
        "name": "产线建设或量产",
        "keywords": ["产能", "产能建设", "工业化规模生产", "量产", "生产"],
    },
    "revenue_margin": {
        "name": "收入和毛利改善",
        "keywords": ["收入", "营收", "毛利", "毛利率", "净利率", "业绩", "高增", "增长"],
    },
    "patent_standard": {
        "name": "专利与标准",
        "keywords": ["自主知识产权", "知识产权", "专利", "标准", "壁垒"],
    },
}


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def fetch_one(cur, sql: str, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def fetch_all(cur, sql: str, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def upsert_event(cur, event: dict[str, Any]) -> None:
    cur.execute(
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
            event_date = EXCLUDED.event_date,
            source_type = EXCLUDED.source_type,
            source_id = EXCLUDED.source_id,
            title = EXCLUDED.title,
            excerpt = EXCLUDED.excerpt,
            original_url = EXCLUDED.original_url,
            evidence_type = EXCLUDED.evidence_type,
            impact_dimensions = EXCLUDED.impact_dimensions,
            confidence = EXCLUDED.confidence,
            review_status = EXCLUDED.review_status,
            stage_after = EXCLUDED.stage_after
        """,
        event,
    )


def main() -> None:
    with psycopg2.connect(DSN) as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        mapping = fetch_one(
            cur,
            """
            SELECT mapping_id, code, node_id, tag_name, l1_l8_path
            FROM business_tag_mapping
            WHERE code=%s AND chain_id='ai_compute'
            ORDER BY confidence DESC
            LIMIT 1
            """,
            (CODE,),
        )
        if not mapping:
            raise SystemExit("No AI-compute business tag mapping found for 688498")

        mapping_id = mapping["mapping_id"]
        node_id = mapping["node_id"]

        stock = fetch_one(cur, "SELECT name, industry, pe_ratio, pb_ratio FROM stocks WHERE code=%s", (CODE,))
        profile = fetch_one(
            cur,
            """
            SELECT full_name, main_business, introduction, updated_at
            FROM stock_profiles
            WHERE code=%s
            """,
            (CODE,),
        )
        indicators = fetch_all(
            cur,
            """
            SELECT end_date, gross_margin, net_margin, revenue_growth, profit_growth, roe, roa
            FROM financial_indicator
            WHERE code=%s AND end_date >= DATE '2016-01-01'
            ORDER BY end_date
            """,
            (CODE,),
        )
        incomes = fetch_all(
            cur,
            """
            SELECT end_date, total_revenue
            FROM financial_income
            WHERE code=%s AND end_date >= DATE '2016-01-01'
            ORDER BY end_date
            """,
            (CODE,),
        )
        forecasts = fetch_all(
            cur,
            """
            SELECT end_date, forecast_type, forecast_net_profit
            FROM forecast_data
            WHERE code=%s AND end_date >= DATE '2016-01-01'
            ORDER BY end_date
            """,
            (CODE,),
        )
        reports = fetch_all(
            cur,
            """
            SELECT pub_date, title, broker, rating, target_price
            FROM research_reports_tushare
            WHERE code=%s AND pub_date >= DATE '2016-01-01'
            ORDER BY pub_date
            """,
            (CODE,),
        )
        mainbz_rows = fetch_all(
            cur,
            """
            SELECT mb.end_date, mb.biz_item, mb.biz_income,
                   CASE
                     WHEN inc.total_revenue IS NOT NULL AND inc.total_revenue > 0
                     THEN mb.biz_income / inc.total_revenue * 100
                     ELSE mb.biz_ratio
                   END AS computed_ratio
            FROM fina_mainbz mb
            LEFT JOIN financial_income inc
              ON inc.code = mb.code AND inc.end_date = mb.end_date
            WHERE mb.code=%s
              AND mb.end_date >= DATE '2016-01-01'
              AND mb.biz_income IS NOT NULL
              AND (
                mb.biz_item ILIKE '%%数据中心%%'
                OR mb.biz_item ILIKE '%%数通%%'
                OR mb.biz_item ILIKE '%%光芯片%%'
                OR mb.biz_item ILIKE '%%激光%%'
              )
            ORDER BY mb.end_date DESC, mb.biz_income DESC
            """,
            (CODE,),
        )
        broker_recs = fetch_all(
            cur,
            """
            SELECT month, broker
            FROM broker_recommend
            WHERE code=%s AND month >= '2016-01'
            ORDER BY month
            """,
            (CODE,),
        )
        qa_rows = fetch_all(
            cur,
            """
            SELECT id, pub_date, question, answer, source
            FROM interact_qa
            WHERE code=%s AND pub_date >= DATE '2016-01-01'
            ORDER BY pub_date
            """,
            (CODE,),
        )
        moneyflow_summary = fetch_one(
            cur,
            """
            SELECT count(*) AS row_count,
                   min(trade_date) AS min_date,
                   max(trade_date) AS max_date,
                   sum(coalesce(net_mf_amount, 0)) FILTER (WHERE trade_date >= DATE '2026-01-01') AS net_mf_ytd,
                   avg(coalesce(net_mf_amount, 0)) FILTER (WHERE trade_date >= DATE '2026-01-01') AS avg_net_mf_ytd
            FROM moneyflow
            WHERE code=%s
            """,
            (CODE,),
        ) or {}

        events: list[dict[str, Any]] = []

        def add_event(
            evidence_type: str,
            event_date,
            source_type: str,
            source_id: str,
            title: str,
            excerpt: str,
            impact_dimensions: list[str],
            confidence: float,
            stage_after: dict[str, Any] | None = None,
        ):
            event_id = stable_id("L8-auto_688498_ai_compute_hardware", evidence_type, source_type, source_id, title)
            events.append(
                {
                    "event_id": event_id,
                    "mapping_id": mapping_id,
                    "code": CODE,
                    "node_id": node_id,
                    "event_date": event_date,
                    "source_type": source_type,
                    "source_id": source_id,
                    "title": title[:500],
                    "excerpt": excerpt[:3000],
                    "original_url": None,
                    "evidence_type": evidence_type,
                    "impact_dimensions": as_json(impact_dimensions),
                    "confidence": confidence,
                    "review_status": "pending_review",
                    "stage_before": as_json({}),
                    "stage_after": as_json(stage_after or {}),
                }
            )

        if profile:
            intro = profile.get("introduction") or ""
            main_business = profile.get("main_business") or ""
            updated_at = profile.get("updated_at")
            profile_date = updated_at.date() if hasattr(updated_at, "date") else None
            profile_text = f"主营业务：{main_business}。公司介绍：{intro}"
            add_event(
                "research_progress",
                profile_date,
                "company_profile",
                f"{CODE}-profile",
                "公司主营光芯片研发、设计、生产与销售",
                profile_text,
                ["research_stage", "business_tag", "moat"],
                0.72,
                {"research_stage": "R2", "reason": "主营与公司介绍明确光芯片研发设计生产"},
            )
            if "工业化规模生产" in intro or "生产" in main_business:
                add_event(
                    "capacity_mass_production",
                    profile_date,
                    "company_profile",
                    f"{CODE}-profile",
                    "公司介绍披露已形成工业化规模生产能力",
                    profile_text,
                    ["commercialization_stage", "growth"],
                    0.72,
                    {"commercialization_stage": "C2", "reason": "公司介绍提及工业化规模生产"},
                )
            if "自主知识产权" in intro:
                add_event(
                    "patent_standard",
                    profile_date,
                    "company_profile",
                    f"{CODE}-profile",
                    "公司介绍披露拥有完整独立自主知识产权",
                    profile_text,
                    ["moat"],
                    0.70,
                    {"moat": "自主知识产权"},
                )

        seen_qa: set[str] = set()
        for row in qa_rows:
            question = row.get("question") or ""
            answer = row.get("answer") or ""
            text = f"{question} {answer}"
            dedupe_key = hashlib.sha1(text.encode("utf-8")).hexdigest()
            if dedupe_key in seen_qa:
                continue
            seen_qa.add(dedupe_key)
            if any(k in text for k in ["产能建设", "市场需求", "经营规划"]):
                add_event(
                    "capacity_mass_production",
                    row.get("pub_date"),
                    "interact_qa",
                    str(row.get("id") or dedupe_key),
                    question,
                    answer,
                    ["commercialization_stage", "growth"],
                    0.62,
                    {"commercialization_stage": "C2", "reason": "董秘回复有序推进产能建设"},
                )
            if any(k in text for k in ["研发投入", "技术创新", "核心竞争力"]):
                add_event(
                    "research_progress",
                    row.get("pub_date"),
                    "interact_qa",
                    str(row.get("id") or dedupe_key),
                    question,
                    answer,
                    ["research_stage", "moat"],
                    0.62,
                    {"research_stage": "R2", "reason": "董秘回复持续加大研发投入"},
                )

        for row in reports:
            title = row.get("title") or ""
            if not title:
                continue
            impact = ["growth", "profit"]
            if any(k in title for k in ["CW", "激光器", "光芯片", "AI"]):
                impact.append("business_tag")
            add_event(
                "revenue_margin",
                row.get("pub_date"),
                "research_title",
                stable_id("report", row.get("pub_date"), row.get("broker"), title),
                title,
                f"{row.get('broker') or ''}_{title}，评级={row.get('rating') or ''}，目标价={row.get('target_price') or ''}",
                impact,
                0.58,
            )

        for row in mainbz_rows:
            end_date = row.get("end_date")
            biz_item = row.get("biz_item") or ""
            income = float(row.get("biz_income") or 0)
            ratio = float(row.get("computed_ratio") or 0)
            add_event(
                "revenue_margin",
                end_date,
                "fina_mainbz",
                f"{CODE}-{end_date}-{biz_item}",
                f"{end_date} 主营构成：{biz_item}",
                (
                    f"{biz_item}收入={income:.2f}元，占当期总营收约{ratio:.2f}%。"
                    "该数据支持AI算力/数据中心相关业务收入占比；产品级毛利未披露，不能替代业务毛利证据。"
                ),
                ["growth", "profit", "business_split"],
                0.82 if ratio >= 30 else 0.72,
            )

        for row in forecasts:
            ftype = row.get("forecast_type") or ""
            net_profit = row.get("forecast_net_profit")
            add_event(
                "revenue_margin",
                row.get("end_date"),
                "forecast",
                f"{CODE}-{row.get('end_date')}-{ftype}",
                f"{row.get('end_date')} 业绩预告：{ftype}",
                f"业绩预告类型={ftype}，预告净利润={net_profit if net_profit is not None else '未披露'}。该数据用于增长/盈利趋势验证。",
                ["growth", "profit"],
                0.68,
            )

        for row in indicators:
            end_date = row.get("end_date")
            revenue_growth = float(row.get("revenue_growth") or 0)
            gross_margin = float(row.get("gross_margin") or 0)
            net_margin = float(row.get("net_margin") or 0)
            if revenue_growth >= 50 or gross_margin >= 45 or net_margin >= 20:
                add_event(
                    "revenue_margin",
                    end_date,
                    "financial_indicator",
                    f"{CODE}-{end_date}",
                    f"{end_date} 财务指标显示收入/盈利改善",
                    (
                        f"营收增速={revenue_growth:.2f}%，毛利率={gross_margin:.2f}%，"
                        f"净利率={net_margin:.2f}%，ROE={float(row.get('roe') or 0):.2f}%"
                    ),
                    ["growth", "profit"],
                    0.76 if end_date and end_date.year >= 2025 else 0.66,
                )

        cur.execute(
            """
            UPDATE business_tag_stage_tracking
            SET source_event_id = NULL
            WHERE mapping_id = %s
            """,
            (mapping_id,),
        )
        cur.execute(
            """
            DELETE FROM business_tag_evidence_events
            WHERE mapping_id = %s
              AND source_type IN (
                'company_profile', 'interact_qa', 'research_title',
                'financial_indicator', 'fina_mainbz', 'forecast'
              )
            """,
            (mapping_id,),
        )

        for event in events:
            upsert_event(cur, event)

        event_ids_by_dim: dict[str, list[str]] = defaultdict(list)
        for event in events:
            event_ids_by_dim[event["evidence_type"]].append(event["event_id"])

        # Preserve any existing events not generated by this script.
        existing_events = fetch_all(
            cur,
            """
            SELECT evidence_type, event_id
            FROM business_tag_evidence_events
            WHERE mapping_id=%s AND evidence_type <> 'inferred_business_tag'
            """,
            (mapping_id,),
        )
        for row in existing_events:
            dim = row["evidence_type"]
            eid = row["event_id"]
            if eid not in event_ids_by_dim[dim]:
                event_ids_by_dim[dim].append(eid)

        for dim_id, meta in DIMENSIONS.items():
            ids = event_ids_by_dim.get(dim_id, [])
            source_status = "matched" if ids else "missing"
            summary = (
                f"近十年本地资料已匹配 {len(ids)} 条{meta['name']}证据"
                if ids
                else f"近十年本地资料暂未命中{meta['name']}，需补公告、年报、客户验证或订单证据"
            )
            cur.execute(
                """
                INSERT INTO business_tag_l8_evidence_status (
                    status_id, mapping_id, code, node_id, dimension_id, dimension_name,
                    source_status, evidence_event_ids, evidence_count, evidence_summary,
                    required_keywords, updated_at
                ) VALUES (
                    %(status_id)s, %(mapping_id)s, %(code)s, %(node_id)s, %(dimension_id)s,
                    %(dimension_name)s, %(source_status)s, %(evidence_event_ids)s::jsonb,
                    %(evidence_count)s, %(evidence_summary)s, %(required_keywords)s::jsonb,
                    %(updated_at)s
                )
                ON CONFLICT (mapping_id, dimension_id) DO UPDATE SET
                    source_status = EXCLUDED.source_status,
                    evidence_event_ids = EXCLUDED.evidence_event_ids,
                    evidence_count = EXCLUDED.evidence_count,
                    evidence_summary = EXCLUDED.evidence_summary,
                    required_keywords = EXCLUDED.required_keywords,
                    updated_at = EXCLUDED.updated_at
                """,
                {
                    "status_id": f"L8STATUS-{mapping_id}-{dim_id}",
                    "mapping_id": mapping_id,
                    "code": CODE,
                    "node_id": node_id,
                    "dimension_id": dim_id,
                    "dimension_name": meta["name"],
                    "source_status": source_status,
                    "evidence_event_ids": as_json(ids),
                    "evidence_count": len(ids),
                    "evidence_summary": summary,
                    "required_keywords": as_json(meta["keywords"]),
                    "updated_at": TRADE_DATE,
                },
            )

        matched_dims = sum(1 for ids in event_ids_by_dim.values() if ids)
        approved_count = 0
        source_count = sum(len(ids) for ids in event_ids_by_dim.values())

        latest_indicator = indicators[-1] if indicators else {}
        latest_income = incomes[-1] if incomes else {}
        latest_mainbz = mainbz_rows[0] if mainbz_rows else {}
        latest_ai_revenue_ratio = (
            round(float(latest_mainbz.get("computed_ratio") or 0), 4)
            if latest_mainbz
            else None
        )
        latest_ai_revenue_item = latest_mainbz.get("biz_item") if latest_mainbz else None
        latest_ai_revenue_income = (
            float(latest_mainbz.get("biz_income") or 0)
            if latest_mainbz
            else None
        )
        latest_revenue_growth = float(latest_indicator.get("revenue_growth") or 0)
        latest_gross_margin = float(latest_indicator.get("gross_margin") or 0)
        latest_net_margin = float(latest_indicator.get("net_margin") or 0)
        latest_revenue = float(latest_income.get("total_revenue") or 0)

        growth_score = min(100.0, max(25.0, latest_revenue_growth * 0.22 + 35.0))
        profit_score = min(100.0, latest_gross_margin * 0.65 + latest_net_margin * 0.55)
        moat_score = 62.0 if event_ids_by_dim.get("patent_standard") else 50.0
        stage_score = 58.0 if event_ids_by_dim.get("capacity_mass_production") else 25.0
        evidence_score = min(100.0, matched_dims / 7 * 70 + min(source_count, 12) * 2.5)
        total_score = round(growth_score * 0.28 + profit_score * 0.25 + moat_score * 0.20 + stage_score * 0.15 + evidence_score * 0.12, 2)

        score_detail = {
            "source": "local_10y_backfill",
            "score_unit": "business_tag",
            "data_window": {
                "start": "2016-01-01",
                "end": str(TRADE_DATE),
                "daily_kline_rows": fetch_one(cur, "SELECT count(*) c FROM daily_kline WHERE code=%s", (CODE,))["c"],
                "moneyflow_rows": int(moneyflow_summary.get("row_count") or 0),
                "moneyflow_range": [
                    str(moneyflow_summary.get("min_date") or ""),
                    str(moneyflow_summary.get("max_date") or ""),
                ],
                "financial_indicator_rows": len(indicators),
                "financial_income_rows": len(incomes),
                "forecast_rows": len(forecasts),
                "interact_qa_rows_raw": len(qa_rows),
                "interact_qa_rows_deduped": len(seen_qa),
                "research_report_rows": len(reports),
                "broker_recommend_rows": len(broker_recs),
                "fina_mainbz_relevant_rows": len(mainbz_rows),
            },
            "inference_only": False,
            "mapping_source": "main_business+profile+local_10y_evidence",
            "mapping_status": "pending_review",
            "revenue_supported": True,
            "profit_supported": True,
            "profit_score_status": "company_level_supported_business_split_missing",
            "business_revenue_supported": bool(latest_ai_revenue_ratio),
            "business_revenue_item": latest_ai_revenue_item,
            "business_revenue_ratio_pct": latest_ai_revenue_ratio,
            "business_revenue_income": latest_ai_revenue_income,
            "business_split_gap": (
                "fina_mainbz now supports data-center related revenue ratio; "
                "product-level gross profit/margin is still unavailable, so profit score uses company-level margins."
                if latest_ai_revenue_ratio
                else "fina_mainbz has no usable 688498 AI/data-center segment rows; scores use company-level financials plus business-tag evidence."
            ),
            "matched_l8_dimensions": matched_dims,
            "approved_evidence_count": approved_count,
            "candidate_evidence_count": source_count,
            "requires_original_evidence": True,
            "latest_financial": {
                "end_date": str(latest_indicator.get("end_date") or ""),
                "total_revenue": latest_revenue,
                "revenue_growth_pct": latest_revenue_growth,
                "gross_margin_pct": latest_gross_margin,
                "net_margin_pct": latest_net_margin,
            },
            "analysis_summary": {
                "strength": "光芯片上游位置明确，毛利率和净利率显著改善，具备国产替代与AI光通信上游弹性。",
                "weakness": "客户验证、订单/中标、样机交付仍缺结构化原始证据，主营构成收入毛利未拆分。",
                "stage": "根据公司简介工业化规模生产、互动问答产能建设和研发投入，建议暂按R2/C2候选处理，等待人工复核。",
            },
        }
        all_evidence_ids = sorted({eid for ids in event_ids_by_dim.values() for eid in ids})
        cur.execute(
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
            (
                f"THREE-HIGH-{mapping_id}-{TRADE_DATE}",
                mapping_id,
                TRADE_DATE,
                round(growth_score, 2),
                round(profit_score, 2),
                round(moat_score, 2),
                round(stage_score, 2),
                round(evidence_score, 2),
                total_score,
                as_json(score_detail),
                as_json(all_evidence_ids),
            ),
        )

        stage_source_id = None
        for preferred in ("capacity_mass_production", "research_progress", "revenue_margin"):
            if event_ids_by_dim.get(preferred):
                stage_source_id = event_ids_by_dim[preferred][0]
                break
        stage_reason = (
            "近十年资料显示：公司主营光芯片研发设计生产，公司介绍披露工业化规模生产；"
            "互动问答披露将按市场需求有序推进产能建设并持续加大研发投入。"
            "但客户验证和订单证据仍未结构化命中，阶段需人工复核。"
        )
        cur.execute(
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
            (
                f"STAGE-{mapping_id}-10Y",
                mapping_id,
                TRADE_DATE,
                "R2",
                "C2",
                stage_reason,
                stage_source_id,
                TRADE_DATE,
                "pending_review",
            ),
        )
        cur.execute(
            """
            UPDATE business_tag_stage_tracking
            SET research_stage = 'R2',
                commercialization_stage = 'C2',
                stage_reason = %s,
                source_event_id = %s,
                last_stage_change_date = %s,
                review_status = 'pending_review'
            WHERE mapping_id = %s AND trade_date = %s
            """,
            (stage_reason, stage_source_id, TRADE_DATE, mapping_id, TRADE_DATE),
        )

        market_expectation_score = min(100.0, len(reports) * 5 + len(broker_recs) * 1.5 + 35)
        actual_progress_score = min(100.0, total_score + matched_dims * 4)
        evidence_delta_score = min(100.0, source_count * 3.5)
        risk_penalty_score = 24.0 if stock and float(stock.get("pe_ratio") or 0) > 150 else 8.0
        expectation_gap_score = round(actual_progress_score + evidence_delta_score * 0.35 - market_expectation_score * 0.45 - risk_penalty_score, 2)
        gap_type = "high_expectation_needs_hard_evidence" if expectation_gap_score < 0 else "positive_evidence_delta"
        gap_detail = {
            "source": "local_10y_backfill",
            "interpretation": "市场关注度较高且估值高，虽然财务弹性强，但订单/客户验证/主营拆分证据不足，预期差更偏风险验证型。",
            "market_expectation_inputs": {
                "research_report_count": len(reports),
                "broker_recommend_count": len(broker_recs),
                "pe_ratio": float(stock.get("pe_ratio") or 0) if stock else None,
                "pb_ratio": float(stock.get("pb_ratio") or 0) if stock else None,
            },
            "actual_progress_inputs": {
                "matched_l8_dimensions": matched_dims,
                "source_evidence_count": source_count,
                "latest_revenue_growth_pct": latest_revenue_growth,
                "latest_gross_margin_pct": latest_gross_margin,
                "latest_net_margin_pct": latest_net_margin,
                "business_revenue_ratio_pct": latest_ai_revenue_ratio,
                "moneyflow_net_ytd": float(moneyflow_summary.get("net_mf_ytd") or 0),
                "moneyflow_avg_net_ytd": float(moneyflow_summary.get("avg_net_mf_ytd") or 0),
            },
        }
        cur.execute(
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
            (
                f"GAP-{mapping_id}-{TRADE_DATE}",
                mapping_id,
                TRADE_DATE,
                round(actual_progress_score, 2),
                round(market_expectation_score, 2),
                round(evidence_delta_score, 2),
                round(risk_penalty_score, 2),
                expectation_gap_score,
                gap_type,
                as_json(gap_detail),
                as_json(all_evidence_ids),
            ),
        )

        # Keep mapping conservative: evidence improved, but still needs review.
        cur.execute(
            """
            UPDATE business_tag_mapping
            SET confidence = GREATEST(confidence, 0.78),
                status = CASE WHEN status='weak_evidence' THEN 'pending_review' ELSE status END,
                revenue_ratio = COALESCE(%s, revenue_ratio),
                evidence_ids = %s::jsonb,
                updated_at = now()
            WHERE mapping_id=%s
            """,
            (latest_ai_revenue_ratio, as_json(all_evidence_ids), mapping_id),
        )

        conn.commit()
        print(
            json.dumps(
                {
                    "code": CODE,
                    "name": stock.get("name") if stock else "源杰科技",
                    "mapping_id": mapping_id,
                    "generated_events": len(events),
                    "total_evidence_ids": len(all_evidence_ids),
                    "matched_l8_dimensions": matched_dims,
                    "research_stage": "R2",
                    "commercialization_stage": "C2",
                    "three_high_total_score": total_score,
                    "expectation_gap_score": expectation_gap_score,
                    "gap_type": gap_type,
                    "financial_rows": {
                        "indicator": len(indicators),
                        "income": len(incomes),
                    },
                    "raw_sources": {
                        "interact_qa_raw": len(qa_rows),
                        "interact_qa_deduped": len(seen_qa),
                        "research_reports": len(reports),
                        "broker_recommend": len(broker_recs),
                        "fina_mainbz_relevant": len(mainbz_rows),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
