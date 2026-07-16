#!/usr/bin/env python3
"""Repair thin/stale priority supply chains from local evidence tables.

The script mines already-landed PostgreSQL sources. It does not call external
APIs and does not infer a company without at least one local source hit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

from embodied_refresh.sources import SOURCE_SPECS, fetch_incremental_sources


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "priority_chain_repair_20260703"
RECENT_CUTOFF = date(2026, 1, 1)


@dataclass(frozen=True)
class ChainNode:
    tag_name: str
    keywords: tuple[str, ...]
    l3: str
    l4: str | None = None

    @property
    def node_id(self) -> str:
        digest = hashlib.sha1(self.tag_name.encode("utf-8")).hexdigest()[:10]
        return f"REPAIR-L5-{digest}"


@dataclass(frozen=True)
class ChainConfig:
    chain_id: str
    l1: str
    l2: str
    nodes: tuple[ChainNode, ...]

    @property
    def keywords(self) -> tuple[str, ...]:
        values: list[str] = []
        for node in self.nodes:
            for keyword in node.keywords:
                if keyword not in values:
                    values.append(keyword)
        return tuple(values)


@dataclass(frozen=True)
class SourceHit:
    code: str
    name: str
    source_type: str
    source_date: str | None
    title: str
    content: str
    source_weight: float
    matched_terms: list[str]


@dataclass(frozen=True)
class Candidate:
    chain_id: str
    code: str
    name: str
    node: ChainNode
    score: float
    confidence: float
    status: str
    hits: list[SourceHit]

    @property
    def mapping_id(self) -> str:
        return stable_id("18C-REPAIR", self.chain_id, self.code, self.node.tag_name)


CHAIN_CONFIGS: dict[str, ChainConfig] = {
    "future_materials": ChainConfig(
        chain_id="future_materials",
        l1="未来产业扩展方向",
        l2="未来材料",
        nodes=(
            ChainNode("碳纤维", ("碳纤维", "碳纤维复合材料", "复合材料", "预浸料"), "上游关键材料"),
            ChainNode("高温合金", ("高温合金", "超高温材料", "航空合金", "粉末高温合金"), "上游关键材料"),
            ChainNode("稀土永磁", ("稀土永磁", "钕铁硼", "磁材", "永磁材料"), "上游关键材料"),
            ChainNode("先进陶瓷", ("先进陶瓷", "电子陶瓷", "结构陶瓷", "陶瓷基板"), "中游制造与集成"),
            ChainNode("超导材料", ("超导材料", "高温超导", "超导线材", "超导磁体"), "前沿材料"),
            ChainNode("石墨烯/气凝胶", ("石墨烯", "气凝胶", "纳米材料"), "前沿材料"),
            ChainNode("可降解/生物基材料", ("可降解材料", "生物基材料", "PLA", "PBAT"), "绿色材料"),
        ),
    ),
    "industrial_software": ChainConfig(
        chain_id="industrial_software",
        l1="新质生产力",
        l2="工业软件",
        nodes=(
            ChainNode("CAD/CAE/CAM", ("CAD", "CAE", "CAM", "三维设计", "工业设计软件"), "软件与控制系统"),
            ChainNode("EDA", ("EDA", "芯片设计软件", "电子设计自动化"), "核心部件/BOM"),
            ChainNode("MES/ERP/PLM", ("MES", "ERP", "PLM", "制造执行系统", "企业资源计划"), "软件与控制系统"),
            ChainNode("工业操作系统/边缘控制", ("工业操作系统", "操作系统", "边缘控制", "实时操作系统"), "软件与控制系统"),
            ChainNode("SCADA/DCS/PLC", ("SCADA", "DCS", "PLC", "组态软件", "工业控制软件"), "软件与控制系统"),
            ChainNode("工业互联网平台", ("工业互联网", "工业软件平台", "工业数据平台", "数字孪生"), "平台与应用"),
        ),
    ),
    "embodied_intelligence": ChainConfig(
        chain_id="embodied_intelligence",
        l1="未来产业主攻方向",
        l2="具身智能",
        nodes=(
            ChainNode("谐波/RV/行星减速器", ("谐波减速器", "RV减速器", "行星减速器", "精密减速器"), "核心部件/BOM"),
            ChainNode("滚柱丝杠/滚珠丝杠", ("滚柱丝杠", "滚珠丝杠", "丝杠", "直线执行器"), "核心部件/BOM"),
            ChainNode("机器人轴承/关节零部件", ("机器人轴承", "交叉滚子轴承", "精密轴承", "关节轴承"), "核心部件/BOM"),
            ChainNode("关节模组/执行器", ("关节模组", "执行器", "智能执行单元", "机器人关节"), "中游制造与集成"),
            ChainNode("空心杯/无框力矩电机", ("空心杯电机", "无框力矩电机", "微特电机", "伺服电机"), "核心部件/BOM"),
            ChainNode("驱动器/控制器/编码器", ("驱动器", "控制器", "编码器", "运动控制", "伺服系统"), "软件与控制系统"),
            ChainNode("力传感器/视觉/灵巧手", ("六维力", "力传感器", "3D视觉", "深度相机", "灵巧手"), "感知与交互"),
            ChainNode("人形机器人整机", ("人形机器人", "具身智能", "机器人本体", "机器人整机"), "整机与应用"),
        ),
    ),
}


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:18]}"


def normalize_code(code: str | None) -> str:
    text = "" if code is None else str(code).strip()
    return text.split(".")[0]


def build_l1_l8_path(config: ChainConfig, node: ChainNode) -> list[dict[str, str]]:
    l4 = node.l4 or node.tag_name
    return [
        {"name": config.l1, "level": "L1"},
        {"name": config.l2, "level": "L2"},
        {"name": node.l3, "level": "L3"},
        {"name": l4, "level": "L4"},
        {"name": node.tag_name, "level": "L5"},
        {"name": f"{node.tag_name}技术路线", "level": "L6"},
        {"name": f"{node.tag_name}壁垒与国产替代", "level": "L7"},
        {"name": f"{node.tag_name}研发/商用/三高证据链", "level": "L8"},
    ]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _contains_any(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [keyword for keyword in keywords if keyword and keyword in text]


def _best_node(config: ChainConfig, hits: list[SourceHit]) -> ChainNode:
    counts: dict[str, float] = defaultdict(float)
    for hit in hits:
        content = f"{hit.title} {hit.content}"
        for node in config.nodes:
            matched = _contains_any(content, node.keywords)
            if matched:
                counts[node.tag_name] += len(matched) * hit.source_weight
    if counts:
        best_name = max(counts, key=counts.get)
        for node in config.nodes:
            if node.tag_name == best_name:
                return node
    return config.nodes[0]


def build_candidate_from_hits(config: ChainConfig, code: str, hits: list[SourceHit]) -> Candidate | None:
    if not hits:
        return None
    normalized = normalize_code(code)
    node = _best_node(config, hits)
    terms = sorted({term for hit in hits for term in hit.matched_terms})
    recent_hits = sum(1 for hit in hits if (_parse_date(hit.source_date) or date.min) >= RECENT_CUTOFF)
    source_types = {hit.source_type for hit in hits}
    score = round(sum(hit.source_weight for hit in hits) + len(terms) * 0.8 + recent_hits * 1.5 + len(source_types) * 0.8, 2)
    confidence = round(min(0.92, 0.42 + score / 28), 4)
    return Candidate(
        chain_id=config.chain_id,
        code=normalized,
        name=hits[0].name,
        node=node,
        score=score,
        confidence=confidence,
        status="candidate",
        hits=hits,
    )


def rank_candidates(candidates: list[Candidate]) -> list[Candidate]:
    filtered: list[Candidate] = []
    for candidate in candidates:
        if not re.fullmatch(r"\d{6}", candidate.code):
            continue
        source_count = len(candidate.hits)
        max_weight = max((hit.source_weight for hit in candidate.hits), default=0)
        terms = {term for hit in candidate.hits for term in hit.matched_terms}
        term_count = len(terms)
        if candidate.score < 2.5:
            continue
        if source_count < 2 and max_weight < 2.5 and term_count < 2:
            continue
        if candidate.chain_id == "embodied_intelligence" and terms <= {"人形机器人"} and source_count < 2:
            continue
        filtered.append(candidate)
    return sorted(filtered, key=lambda item: (-item.score, item.chain_id, item.code))


def mapping_row_for_candidate(config: ChainConfig, candidate: Candidate) -> dict[str, Any]:
    return {
        "mapping_id": candidate.mapping_id,
        "code": candidate.code,
        "business_segment_id": None,
        "node_id": candidate.node.node_id,
        "theme_id": config.chain_id,
        "chain_id": config.chain_id,
        "tag_name": candidate.node.tag_name,
        "l1_l8_path": build_l1_l8_path(config, candidate.node),
        "confidence": candidate.confidence,
        "status": candidate.status,
    }


def _patterns(keywords: tuple[str, ...]) -> list[str]:
    return [f"%{keyword}%" for keyword in keywords if keyword]


def fetch_source_hits(pg_url: str, config: ChainConfig, since: str | None = None) -> dict[str, list[SourceHit]]:
    keywords = config.keywords
    patterns = _patterns(keywords)
    since_clause = "AND {date_col} >= %s" if since else ""
    hits_by_code: dict[str, list[SourceHit]] = defaultdict(list)

    def add_hit(code: str, name: str, source_type: str, source_date: Any, title: str, content: str, weight: float) -> None:
        full_text = f"{title or ''} {content or ''}"
        matched = _contains_any(full_text, keywords)
        if not matched:
            return
        hits_by_code[normalize_code(code)].append(
            SourceHit(
                normalize_code(code),
                name or "",
                source_type,
                str(source_date)[:10] if source_date else None,
                title or "",
                content or "",
                weight,
                matched[:12],
            )
        )

    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT p.code, s.name, p.updated_at::date AS dt,
                       coalesce(p.full_name, '') AS title,
                       concat_ws(' ', p.main_business, p.business_scope, p.introduction) AS content
                FROM stock_profiles p
                LEFT JOIN stocks s ON s.code = p.code
                WHERE concat_ws(' ', p.main_business, p.business_scope, p.introduction) ILIKE ANY(%s)
                """,
                (patterns,),
            )
            for row in cur.fetchall():
                add_hit(row["code"], row["name"], "profile", row["dt"], row["title"], row["content"], 2.5)

            ann_sql = f"""
                SELECT a.code, s.name, a.ann_date AS dt, a.title,
                       left(coalesce(a.content, ''), 3000) AS content
                FROM announcements a
                LEFT JOIN stocks s ON s.code = a.code
                WHERE concat_ws(' ', a.title, a.content) ILIKE ANY(%s)
                  {since_clause.format(date_col='a.ann_date')}
                ORDER BY a.ann_date DESC
                LIMIT 2000
            """
            cur.execute(ann_sql, (patterns, since) if since else (patterns,))
            for row in cur.fetchall():
                add_hit(row["code"], row["name"], "announcement", row["dt"], row["title"], row["content"], 3.0)

            qa_sql = f"""
                SELECT q.code, s.name, q.pub_date AS dt,
                       left(coalesce(q.question, ''), 500) AS title,
                       left(coalesce(q.answer, ''), 3000) AS content
                FROM interact_qa q
                LEFT JOIN stocks s ON s.code = q.code
                WHERE concat_ws(' ', q.question, q.answer) ILIKE ANY(%s)
                  {since_clause.format(date_col='q.pub_date')}
                ORDER BY q.pub_date DESC
                LIMIT 3000
            """
            cur.execute(qa_sql, (patterns, since) if since else (patterns,))
            for row in cur.fetchall():
                add_hit(row["code"], row["name"], "interact_qa", row["dt"], row["title"], row["content"], 2.0)

            report_sql = f"""
                SELECT r.code, s.name, r.pub_date AS dt, r.title,
                       concat_ws(' ', r.broker, r.rating, r.target_price::text) AS content
                FROM research_reports_tushare r
                LEFT JOIN stocks s ON s.code = r.code
                WHERE r.title ILIKE ANY(%s)
                  {since_clause.format(date_col='r.pub_date')}
                ORDER BY r.pub_date DESC
                LIMIT 3000
            """
            cur.execute(report_sql, (patterns, since) if since else (patterns,))
            for row in cur.fetchall():
                add_hit(row["code"], row["name"], "research", row["dt"], row["title"], row["content"], 1.5)
    return hits_by_code


def fetch_embodied_incremental_sources(pg_url: str, cursors: dict[str, str | None]):
    """Backward-compatible entry point for the daily embodied refresh adapter."""
    return fetch_incremental_sources(pg_url, cursors)


def fetch_existing_mappings(pg_url: str, chain_ids: list[str]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT mapping_id, chain_id, code, node_id, tag_name, l1_l8_path, status
                FROM business_tag_mapping
                WHERE chain_id = ANY(%s)
                """,
                (chain_ids,),
            )
            result: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for row in cur.fetchall():
                item = dict(row)
                item["code"] = normalize_code(item.get("code"))
                result[(item["chain_id"], item["code"])].append(item)
            return result


def _choose_mapping(existing: list[dict[str, Any]], candidate: Candidate) -> dict[str, Any] | None:
    if not existing:
        return None
    for item in existing:
        if candidate.node.tag_name in str(item.get("tag_name") or "") or str(item.get("tag_name") or "") in candidate.node.tag_name:
            return item
    return existing[0]


def _evidence_type(content: str) -> str:
    if any(term in content for term in ("量产", "产线", "产能", "投产", "出货")):
        return "capacity_mass_production"
    if any(term in content for term in ("订单", "中标", "合同", "定点", "采购")):
        return "order_award"
    if any(term in content for term in ("客户", "验证", "认证", "供应商", "导入")):
        return "customer_validation"
    if any(term in content for term in ("收入", "营收", "毛利", "利润", "业绩", "增长")):
        return "revenue_margin"
    if any(term in content for term in ("专利", "标准", "知识产权", "壁垒", "国产替代")):
        return "patent_standard"
    return "research_progress"


def build_repair_plan(pg_url: str, chain_ids: list[str], limit_per_chain: int, since: str | None) -> dict[str, Any]:
    configs = [CHAIN_CONFIGS[chain_id] for chain_id in chain_ids]
    existing = fetch_existing_mappings(pg_url, chain_ids)
    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "chains": {},
        "mapping_rows": [],
        "event_rows": [],
    }
    for config in configs:
        hits_by_code = fetch_source_hits(pg_url, config, since=since)
        candidates = rank_candidates([
            item for code, hits in hits_by_code.items()
            if (item := build_candidate_from_hits(config, code, hits)) is not None
        ])[:limit_per_chain]
        inserted_candidate_count = 0
        reused_mapping_count = 0
        event_count = 0
        for candidate in candidates:
            chosen = _choose_mapping(existing.get((config.chain_id, candidate.code), []), candidate)
            if chosen:
                mapping_id = chosen["mapping_id"]
                tag_name = chosen["tag_name"]
                node_id = chosen["node_id"]
                reused_mapping_count += 1
            else:
                mapping_id = candidate.mapping_id
                tag_name = candidate.node.tag_name
                node_id = candidate.node.node_id
                inserted_candidate_count += 1
                report["mapping_rows"].append(mapping_row_for_candidate(config, candidate))
            for hit in candidate.hits[:6]:
                content = f"{hit.title} {hit.content}"
                event_id = stable_id("REPAIR-EV", mapping_id, hit.source_type, hit.source_date, hit.title, content[:80])
                report["event_rows"].append({
                    "event_id": event_id,
                    "mapping_id": mapping_id,
                    "code": candidate.code,
                    "node_id": node_id,
                    "event_date": hit.source_date,
                    "source_type": f"repair_local_{hit.source_type}",
                    "source_id": stable_id("SRC", candidate.code, hit.source_type, hit.source_date, hit.title),
                    "title": hit.title[:500],
                    "excerpt": hit.content[:3000],
                    "original_url": None,
                    "evidence_type": _evidence_type(content),
                    "impact_dimensions": ["business_tag", "priority_chain_repair", config.chain_id],
                    "confidence": min(0.88, candidate.confidence),
                    "review_status": "pending_review",
                    "stage_before": {},
                    "stage_after": {},
                })
                event_count += 1
        report["chains"][config.chain_id] = {
            "source_hit_codes": len(hits_by_code),
            "selected_candidates": len(candidates),
            "new_candidate_mappings": inserted_candidate_count,
            "existing_mappings_refreshed": reused_mapping_count,
            "evidence_events": event_count,
        }
    return report


def persist_repair_plan(pg_url: str, plan: dict[str, Any]) -> dict[str, int]:
    mapping_rows = plan["mapping_rows"]
    event_rows = plan["event_rows"]
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            if mapping_rows:
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    INSERT INTO business_tag_mapping (
                        mapping_id, code, business_segment_id, node_id, theme_id, chain_id,
                        tag_name, l1_l8_path, confidence, status, evidence_ids, created_at, updated_at
                    ) VALUES (
                        %(mapping_id)s, %(code)s, %(business_segment_id)s, %(node_id)s, %(theme_id)s,
                        %(chain_id)s, %(tag_name)s, %(l1_l8_path)s::jsonb, %(confidence)s,
                        %(status)s, '[]'::jsonb, now(), now()
                    )
                    ON CONFLICT (mapping_id) DO UPDATE SET
                        confidence = GREATEST(business_tag_mapping.confidence, EXCLUDED.confidence),
                        status = EXCLUDED.status,
                        updated_at = now()
                    """,
                    [{**row, "l1_l8_path": json.dumps(row["l1_l8_path"], ensure_ascii=False)} for row in mapping_rows],
                    page_size=500,
                )
            if event_rows:
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
                    [
                        {
                            **row,
                            "impact_dimensions": json.dumps(row["impact_dimensions"], ensure_ascii=False),
                            "stage_before": json.dumps(row["stage_before"], ensure_ascii=False),
                            "stage_after": json.dumps(row["stage_after"], ensure_ascii=False),
                        }
                        for row in event_rows
                    ],
                    page_size=1000,
                )
        conn.commit()
    return {"mapping_rows": len(mapping_rows), "event_rows": len(event_rows)}


def write_reports(plan: dict[str, Any], output_dir: Path, persisted: dict[str, int] | None = None) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    payload = {
        "generated_at": plan["generated_at"],
        "chains": plan["chains"],
        "persisted": persisted or {"mapping_rows": 0, "event_rows": 0},
    }
    json_path = output_dir / f"priority_chain_repair_{stamp}.json"
    md_path = output_dir / f"priority_chain_repair_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 优先产业链候选池和证据修复报告",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "| chain_id | 来源命中公司 | 选中候选 | 新增映射 | 刷新已有映射 | 证据事件 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for chain_id, row in payload["chains"].items():
        lines.append(
            f"| {chain_id} | {row['source_hit_codes']} | {row['selected_candidates']} | "
            f"{row['new_candidate_mappings']} | {row['existing_mappings_refreshed']} | {row['evidence_events']} |"
        )
    lines.extend([
        "",
        "## 口径",
        "",
        "- 只使用本地 PostgreSQL 已落库来源：公司资料、公告、互动问答、研报标题。",
        "- 新增映射状态统一为 `candidate`，后续仍需复核。",
        "- 证据事件进入 `business_tag_evidence_events`，再由证据结构化管道转入原始文档和事实表。",
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair priority supply-chain candidates from local evidence")
    parser.add_argument("--pg-url", default=DEFAULT_PG_URL)
    parser.add_argument("--chains", default="future_materials,industrial_software,embodied_intelligence")
    parser.add_argument("--limit-per-chain", type=int, default=80)
    parser.add_argument("--since", default=None, help="Only use dated event sources after YYYY-MM-DD; profiles are always considered")
    parser.add_argument("--execute", action="store_true", help="Persist mappings and evidence events")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    chain_ids = [item.strip() for item in args.chains.split(",") if item.strip()]
    unknown = [item for item in chain_ids if item not in CHAIN_CONFIGS]
    if unknown:
        raise SystemExit(f"unknown chain_id: {','.join(unknown)}")

    plan = build_repair_plan(args.pg_url, chain_ids, args.limit_per_chain, args.since)
    persisted = persist_repair_plan(args.pg_url, plan) if args.execute else {"mapping_rows": 0, "event_rows": 0}
    json_path, md_path = write_reports(plan, Path(args.output_dir), persisted)
    print(json.dumps({
        "execute": args.execute,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "chains": plan["chains"],
        "persisted": persisted,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
