#!/usr/bin/env python3
"""Materialize V2 industry research nodes, dimensions, routes, and edges."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "packages" / "kronos-factors"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from kronos_factors.engine.industry_chain_templates import (  # noqa: E402
    EXPECTED_DIMENSIONS,
    get_industry_template,
    load_selection_v2_profile,
    validate_selection_v2_profile,
)
from kronos_factors.scorer.supply_chain_selection_v2 import (  # noqa: E402
    score_node_attractiveness,
)


DEFAULT_DSN = os.environ.get(
    "KRONOS_PG_URL",
    "postgresql://kronos:kronos@localhost:6432/kronos",
)
MODEL_VERSION = "v2.0"

NODE_FACTOR_BY_DIMENSION = {
    "function_value": "demand_certainty",
    "value_pool": "value_pool_score",
    "competition_moat": "bottleneck_score",
    "supply_demand_cycle": "supply_demand_score",
    "technology_route": "technology_maturity_score",
    "physical_bom": "commercialization_score",
    "market_expectation": "transmission_score",
    "evidence_validation": "evidence_quality_score",
}

VALID_DIMENSION_STATUSES = {
    "known",
    "estimated",
    "proxy",
    "unknown",
    "contradicted",
}


def layer_node_id(template_id: str, layer_id: str) -> str:
    return f"{template_id}_{layer_id}"


def _validate_optional_score(name: str, value: Any) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric < 0 or numeric > 100:
        raise ValueError(f"{name} must be between 0 and 100")
    return numeric


def _dimension_row(
    *,
    template_id: str,
    node_id: str,
    dimension_id: str,
    as_of_date: date,
    configured: dict[str, Any],
) -> dict[str, Any]:
    status = str(configured.get("status") or "unknown")
    if status not in VALID_DIMENSION_STATUSES:
        raise ValueError(f"invalid dimension status: {status}")
    score = _validate_optional_score(
        f"{node_id}.{dimension_id}.score",
        configured.get("score"),
    )
    coverage_ratio = float(configured.get("coverage_ratio") or 0.0)
    if coverage_ratio < 0 or coverage_ratio > 1:
        raise ValueError("coverage_ratio must be between 0 and 1")
    confidence_score = _validate_optional_score(
        f"{node_id}.{dimension_id}.confidence_score",
        configured.get("confidence_score"),
    )
    return {
        "dimension_record_id": (
            f"{node_id}:{dimension_id}:{as_of_date.isoformat()}"
        ),
        "node_id": node_id,
        "chain_id": template_id,
        "template_id": template_id,
        "dimension_id": dimension_id,
        "as_of_date": as_of_date,
        "status": status,
        "score": score,
        "coverage_ratio": coverage_ratio,
        "confidence_score": confidence_score,
        "payload": dict(configured.get("payload") or {}),
        "evidence_ids": list(configured.get("evidence_ids") or []),
        "review_status": str(
            configured.get("review_status") or "pending_review"
        ),
    }


def _node_score_rows(
    nodes: list[dict[str, Any]],
    dimensions: list[dict[str, Any]],
    as_of_date: date,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for dimension in dimensions:
        by_node[dimension["node_id"]].append(dimension)

    rows: list[dict[str, Any]] = []
    for node in nodes:
        node_dimensions = by_node[node["node_id"]]
        factors = {
            NODE_FACTOR_BY_DIMENSION[item["dimension_id"]]: item["score"]
            for item in node_dimensions
        }
        result = score_node_attractiveness(factors, profile)
        evidence_ids = sorted(
            {
                str(evidence_id)
                for item in node_dimensions
                for evidence_id in item["evidence_ids"]
                if evidence_id
            }
        )
        ready = (
            result.score is not None
            and result.coverage_ratio >= 0.5
            and bool(evidence_ids)
        )
        rows.append(
            {
                "score_id": (
                    f"{node['node_id']}:{as_of_date.isoformat()}:{MODEL_VERSION}"
                ),
                "node_id": node["node_id"],
                "trade_date": as_of_date,
                "model_version": MODEL_VERSION,
                **factors,
                "total_score": result.score if ready else None,
                "coverage_ratio": result.coverage_ratio,
                "score_status": "ready" if ready else "insufficient_evidence",
                "score_detail": {
                    **result.detail,
                    "unpublished_candidate_score": result.score,
                    "requires_evidence": not bool(evidence_ids),
                },
                "evidence_ids": evidence_ids,
            }
        )
    return rows


def build_research_rows(
    template: dict[str, Any],
    as_of_date: date,
) -> dict[str, list[dict[str, Any]]]:
    template_id = str(template.get("template_id") or "")
    if not template_id:
        raise ValueError("template_id is required")

    profile = load_selection_v2_profile()
    validate_selection_v2_profile(profile)
    layers = sorted(
        template.get("layers") or [],
        key=lambda item: int(item.get("order") or 0),
    )
    nodes: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    for index, layer in enumerate(layers):
        layer_id = str(layer.get("layer_id") or "")
        node_id = layer_node_id(template_id, layer_id)
        parent_node_id = nodes[index - 1]["node_id"] if index else None
        node = {
            "node_id": node_id,
            "parent_node_id": parent_node_id,
            "layer_level": f"L{int(layer.get('order') or 0)}",
            "layer_name": str(layer.get("name") or layer_id),
            "display_name": str(layer.get("name") or layer_id),
            "policy_theme_id": None,
            "chain_id": template_id,
            "bom_node_id": node_id,
            "source_table": "industry_chain_templates",
            "source_id": f"{template_id}:{layer_id}",
            "keywords": list(layer.get("segments") or []),
            "metadata": {
                "template_id": template_id,
                "layer_id": layer_id,
                "definition": str(layer.get("definition") or ""),
                "key_questions": list(layer.get("key_questions") or []),
            },
        }
        nodes.append(node)
        configured_dimensions = layer.get("research_dimensions") or {}
        for dimension_id in EXPECTED_DIMENSIONS:
            dimensions.append(
                _dimension_row(
                    template_id=template_id,
                    node_id=node_id,
                    dimension_id=dimension_id,
                    as_of_date=as_of_date,
                    configured=dict(configured_dimensions.get(dimension_id) or {}),
                )
            )

    node_ids = {node["node_id"] for node in nodes}
    routes: list[dict[str, Any]] = []
    for configured in template.get("technology_routes") or []:
        node_id = str(configured.get("node_id") or "")
        if node_id not in node_ids:
            raise ValueError(f"route references unknown node: {node_id}")
        routes.append(
            {
                "route_id": str(configured["route_id"]),
                "chain_id": template_id,
                "node_id": node_id,
                "route_name": str(configured["route_name"]),
                "maturity_stage": str(
                    configured.get("maturity_stage") or "concept"
                ),
                "performance_metrics": dict(
                    configured.get("performance_metrics") or {}
                ),
                "manufacturing_difficulty": dict(
                    configured.get("manufacturing_difficulty") or {}
                ),
                "cost_trend": dict(configured.get("cost_trend") or {}),
                "substitute_route_ids": list(
                    configured.get("substitute_route_ids") or []
                ),
                "failure_conditions": list(
                    configured.get("failure_conditions") or []
                ),
                "evidence_ids": list(configured.get("evidence_ids") or []),
                "last_strong_evidence_date": configured.get(
                    "last_strong_evidence_date"
                ),
                "review_status": str(
                    configured.get("review_status") or "pending_review"
                ),
            }
        )

    edges: list[dict[str, Any]] = []
    for configured in template.get("transmission_edges") or []:
        from_node_id = str(configured.get("from_node_id") or "")
        to_node_id = str(configured.get("to_node_id") or "")
        if from_node_id not in node_ids or to_node_id not in node_ids:
            raise ValueError("transmission edge references unknown node")
        edges.append(
            {
                "edge_id": str(configured["edge_id"]),
                "chain_id": template_id,
                "from_node_id": from_node_id,
                "to_node_id": to_node_id,
                "flow_type": str(configured["flow_type"]),
                "transmission_logic": str(
                    configured.get("transmission_logic") or ""
                ),
                "transmission_strength": _validate_optional_score(
                    "transmission_strength",
                    configured.get("transmission_strength"),
                ),
                "transmission_lag_days": configured.get(
                    "transmission_lag_days"
                ),
                "failure_conditions": list(
                    configured.get("failure_conditions") or []
                ),
                "leading_metric_ids": list(
                    configured.get("leading_metric_ids") or []
                ),
                "evidence_ids": list(configured.get("evidence_ids") or []),
                "coverage_ratio": float(
                    configured.get("coverage_ratio") or 0.0
                ),
                "review_status": str(
                    configured.get("review_status") or "pending_review"
                ),
            }
        )

    return {
        "nodes": nodes,
        "dimensions": dimensions,
        "routes": routes,
        "edges": edges,
        "node_scores": _node_score_rows(
            nodes,
            dimensions,
            as_of_date,
            profile,
        ),
    }


def _mapping_node_id(template_id: str, keyword: str) -> str:
    if "灵巧手" in keyword or "末端" in keyword:
        layer_id = "core_product"
    elif "执行器" in keyword:
        layer_id = "integration"
    else:
        layer_id = "foundation"
    return layer_node_id(template_id, layer_id)


def _normalize_stock_code(value: Any) -> str:
    return str(value or "").split(".", 1)[0]


def build_derived_mapping(
    *,
    template_id: str,
    source: dict[str, Any],
    matched_keyword: str,
) -> dict[str, Any]:
    token = hashlib.sha1(
        f"{source['mapping_id']}:{matched_keyword}".encode("utf-8")
    ).hexdigest()[:12]
    return {
        "mapping_id": f"DEXH-{source['code']}-{token}",
        "code": _normalize_stock_code(source["code"]),
        "business_segment_id": source.get("business_segment_id"),
        "node_id": _mapping_node_id(template_id, matched_keyword),
        "theme_id": "future_industry_dexterous_hand",
        "chain_id": template_id,
        "tag_name": matched_keyword,
        "l1_l8_path": [
            {
                "level": "provenance",
                "derived_from_mapping_id": source["mapping_id"],
                "requires_original_evidence": True,
            }
        ],
        "revenue_ratio": None,
        "gross_profit_ratio": None,
        "confidence": 0.35,
        "status": "candidate",
        "evidence_ids": [],
    }


def derive_candidate_mappings(
    cur,
    template: dict[str, Any],
) -> list[dict[str, Any]]:
    rules = template.get("candidate_mapping_rules") or {}
    source_chain_ids = list(rules.get("source_chain_ids") or [])
    keywords = list(rules.get("required_business_keywords") or [])
    if not source_chain_ids or not keywords:
        return []
    cur.execute(
        """
        SELECT b.mapping_id, b.code, b.business_segment_id, b.tag_name,
               b.evidence_ids, s.segment_name
        FROM business_tag_mapping b
        LEFT JOIN company_business_segments s
          ON s.segment_id = b.business_segment_id
        WHERE b.chain_id = ANY(%s)
        ORDER BY b.code, b.mapping_id
        """,
        (source_chain_ids,),
    )
    rows = [dict(row) for row in cur.fetchall()]
    derived: dict[str, dict[str, Any]] = {}
    for source in rows:
        searchable = " ".join(
            str(value or "")
            for value in (source.get("tag_name"), source.get("segment_name"))
        )
        for keyword in keywords:
            if keyword not in searchable:
                continue
            item = build_derived_mapping(
                template_id=str(template["template_id"]),
                source=source,
                matched_keyword=keyword,
            )
            derived[item["mapping_id"]] = item
    return [derived[key] for key in sorted(derived)]


def _upsert_nodes(cur, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            INSERT INTO supply_chain_hierarchy_nodes (
                node_id, parent_node_id, layer_level, layer_name, display_name,
                policy_theme_id, chain_id, bom_node_id, source_table, source_id,
                keywords, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (node_id) DO UPDATE SET
                parent_node_id=EXCLUDED.parent_node_id,
                layer_level=EXCLUDED.layer_level,
                layer_name=EXCLUDED.layer_name,
                display_name=EXCLUDED.display_name,
                chain_id=EXCLUDED.chain_id,
                bom_node_id=EXCLUDED.bom_node_id,
                source_table=EXCLUDED.source_table,
                source_id=EXCLUDED.source_id,
                keywords=EXCLUDED.keywords,
                metadata=EXCLUDED.metadata,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                row["node_id"],
                row["parent_node_id"],
                row["layer_level"],
                row["layer_name"],
                row["display_name"],
                row["policy_theme_id"],
                row["chain_id"],
                row["bom_node_id"],
                row["source_table"],
                row["source_id"],
                Json(row["keywords"]),
                Json(row["metadata"]),
            ),
        )


def _upsert_dimensions(cur, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            INSERT INTO supply_chain_node_dimensions (
                dimension_record_id,node_id,chain_id,template_id,dimension_id,
                as_of_date,status,score,coverage_ratio,confidence_score,payload,
                evidence_ids,review_status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (node_id, dimension_id, as_of_date) DO UPDATE SET
                status=EXCLUDED.status,
                score=EXCLUDED.score,
                coverage_ratio=EXCLUDED.coverage_ratio,
                confidence_score=EXCLUDED.confidence_score,
                payload=EXCLUDED.payload,
                evidence_ids=EXCLUDED.evidence_ids,
                updated_at=CURRENT_TIMESTAMP
            WHERE supply_chain_node_dimensions.review_status <> 'approved'
            """,
            (
                row["dimension_record_id"],
                row["node_id"],
                row["chain_id"],
                row["template_id"],
                row["dimension_id"],
                row["as_of_date"],
                row["status"],
                row["score"],
                row["coverage_ratio"],
                row["confidence_score"],
                Json(row["payload"]),
                Json(row["evidence_ids"]),
                row["review_status"],
            ),
        )


def _upsert_routes(cur, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            INSERT INTO supply_chain_technology_routes (
                route_id,chain_id,node_id,route_name,maturity_stage,
                performance_metrics,manufacturing_difficulty,cost_trend,
                substitute_route_ids,failure_conditions,evidence_ids,
                last_strong_evidence_date,review_status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (route_id) DO UPDATE SET
                node_id=EXCLUDED.node_id,
                route_name=EXCLUDED.route_name,
                maturity_stage=EXCLUDED.maturity_stage,
                performance_metrics=EXCLUDED.performance_metrics,
                manufacturing_difficulty=EXCLUDED.manufacturing_difficulty,
                cost_trend=EXCLUDED.cost_trend,
                substitute_route_ids=EXCLUDED.substitute_route_ids,
                failure_conditions=EXCLUDED.failure_conditions,
                evidence_ids=EXCLUDED.evidence_ids,
                last_strong_evidence_date=EXCLUDED.last_strong_evidence_date,
                updated_at=CURRENT_TIMESTAMP
            WHERE supply_chain_technology_routes.review_status <> 'approved'
            """,
            (
                row["route_id"],
                row["chain_id"],
                row["node_id"],
                row["route_name"],
                row["maturity_stage"],
                Json(row["performance_metrics"]),
                Json(row["manufacturing_difficulty"]),
                Json(row["cost_trend"]),
                Json(row["substitute_route_ids"]),
                Json(row["failure_conditions"]),
                Json(row["evidence_ids"]),
                row["last_strong_evidence_date"],
                row["review_status"],
            ),
        )


def _upsert_edges(cur, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            INSERT INTO supply_chain_transmission_edges (
                edge_id,chain_id,from_node_id,to_node_id,flow_type,
                transmission_logic,transmission_strength,transmission_lag_days,
                failure_conditions,leading_metric_ids,evidence_ids,coverage_ratio,
                review_status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (edge_id) DO UPDATE SET
                transmission_logic=EXCLUDED.transmission_logic,
                transmission_strength=EXCLUDED.transmission_strength,
                transmission_lag_days=EXCLUDED.transmission_lag_days,
                failure_conditions=EXCLUDED.failure_conditions,
                leading_metric_ids=EXCLUDED.leading_metric_ids,
                evidence_ids=EXCLUDED.evidence_ids,
                coverage_ratio=EXCLUDED.coverage_ratio,
                updated_at=CURRENT_TIMESTAMP
            WHERE supply_chain_transmission_edges.review_status <> 'approved'
            """,
            (
                row["edge_id"],
                row["chain_id"],
                row["from_node_id"],
                row["to_node_id"],
                row["flow_type"],
                row["transmission_logic"],
                row["transmission_strength"],
                row["transmission_lag_days"],
                Json(row["failure_conditions"]),
                Json(row["leading_metric_ids"]),
                Json(row["evidence_ids"]),
                row["coverage_ratio"],
                row["review_status"],
            ),
        )


def _upsert_node_scores(cur, rows: list[dict[str, Any]]) -> None:
    columns = list(NODE_FACTOR_BY_DIMENSION.values())
    for row in rows:
        cur.execute(
            f"""
            INSERT INTO supply_chain_node_scores (
                score_id,node_id,trade_date,model_version,{','.join(columns)},
                total_score,coverage_ratio,score_status,score_detail,evidence_ids
            ) VALUES (
                %s,%s,%s,%s,{','.join(['%s'] * len(columns))},%s,%s,%s,%s,%s
            )
            ON CONFLICT (node_id, trade_date, model_version) DO UPDATE SET
                {','.join(f'{column}=EXCLUDED.{column}' for column in columns)},
                total_score=EXCLUDED.total_score,
                coverage_ratio=EXCLUDED.coverage_ratio,
                score_status=EXCLUDED.score_status,
                score_detail=EXCLUDED.score_detail,
                evidence_ids=EXCLUDED.evidence_ids
            """,
            (
                row["score_id"],
                row["node_id"],
                row["trade_date"],
                row["model_version"],
                *(row[column] for column in columns),
                row["total_score"],
                row["coverage_ratio"],
                row["score_status"],
                Json(row["score_detail"]),
                Json(row["evidence_ids"]),
            ),
        )


def _upsert_candidate_mappings(cur, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            INSERT INTO business_tag_mapping (
                mapping_id,code,business_segment_id,node_id,theme_id,chain_id,
                tag_name,l1_l8_path,revenue_ratio,gross_profit_ratio,confidence,
                status,evidence_ids
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (mapping_id) DO UPDATE SET code=EXCLUDED.code,
                updated_at=CURRENT_TIMESTAMP
            WHERE business_tag_mapping.status = 'candidate'
            """,
            (
                row["mapping_id"],
                row["code"],
                row["business_segment_id"],
                row["node_id"],
                row["theme_id"],
                row["chain_id"],
                row["tag_name"],
                Json(row["l1_l8_path"]),
                row["revenue_ratio"],
                row["gross_profit_ratio"],
                row["confidence"],
                row["status"],
                Json(row["evidence_ids"]),
            ),
        )


def materialize(
    pg_url: str,
    *,
    template_id: str,
    as_of_date: date,
    dry_run: bool,
) -> dict[str, Any]:
    template = get_industry_template(template_id)
    rows = build_research_rows(template, as_of_date)
    planned: dict[str, Any] = {
        "nodes": len(rows["nodes"]),
        "dimensions": len(rows["dimensions"]),
        "routes": len(rows["routes"]),
        "edges": len(rows["edges"]),
        "node_scores": len(rows["node_scores"]),
        "candidate_mappings": "requires_database_read",
    }
    if dry_run:
        return {
            "dry_run": True,
            "template_id": template_id,
            "as_of_date": as_of_date.isoformat(),
            "planned": planned,
        }

    with psycopg2.connect(pg_url, connect_timeout=5) as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cur:
            candidate_mappings = derive_candidate_mappings(cur, template)
            planned["candidate_mappings"] = len(candidate_mappings)
            _upsert_nodes(cur, rows["nodes"])
            _upsert_dimensions(cur, rows["dimensions"])
            _upsert_routes(cur, rows["routes"])
            _upsert_edges(cur, rows["edges"])
            _upsert_node_scores(cur, rows["node_scores"])
            _upsert_candidate_mappings(cur, candidate_mappings)
        connection.commit()
    return {
        "dry_run": False,
        "template_id": template_id,
        "as_of_date": as_of_date.isoformat(),
        "written": planned,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize supply-chain research V2 structures"
    )
    parser.add_argument("--template-id", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--pg-url", default=DEFAULT_DSN)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = materialize(
        args.pg_url,
        template_id=args.template_id,
        as_of_date=date.fromisoformat(args.as_of_date),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
