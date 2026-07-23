"""人工审核入口(PG 审核门)集成测试。

验证 `_review_business_tag_evidence` 在同一事务内设置
`SET LOCAL app.supply_chain_review_action = 'manual'` 并补齐
reviewer/review_note/reviewed_at 审计字段后,能够通过 alembic 033
安装的 `guard_supply_chain_manual_review` 触发器,把证据事件与
stage_tracking 同步置为 approved。

PG 不可用时整个模块自动 skip。
"""
import os
import sys
import uuid
from pathlib import Path

import pytest

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _SERVICE_ROOT.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "packages" / "kronos-factors"))
sys.path.insert(0, str(_SERVICE_ROOT))

os.environ.setdefault("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

psycopg2 = pytest.importorskip("psycopg2")

PG_URL = os.environ["KRONOS_PG_URL"]


def _pg_available() -> bool:
    try:
        conn = psycopg2.connect(PG_URL, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL 不可用,跳过审核门集成测试")


def test_review_business_tag_evidence_approve_passes_review_gate():
    from app.domains.screening.service import (
        BusinessTagEvidenceReviewRequest,
        _review_business_tag_evidence,
    )

    suffix = uuid.uuid4().hex[:8].upper()
    mapping_id = f"TEST-REVIEW-GATE-{suffix}"
    event_id = f"TEST-EVT-{suffix}"
    code = "000001.SZ"

    conn = psycopg2.connect(PG_URL)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO business_tag_mapping (mapping_id, code, tag_name, confidence, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (mapping_id, code, "审核门测试标签", 0.5, "pending_review"),
        )
        cur.execute(
            """
            INSERT INTO business_tag_evidence_events (
                event_id, mapping_id, code, event_date, source_type, source_id,
                title, excerpt, evidence_type, impact_dimensions, confidence,
                review_status, stage_before, stage_after
            )
            VALUES (%s, %s, %s, CURRENT_DATE, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                event_id,
                mapping_id,
                code,
                "manual",
                "test-review-gate",
                "审核门测试证据",
                "审核门测试证据摘要",
                "customer_validation",
                '["growth"]',
                0.8,
                "pending_review",
                "{}",
                '{"research_stage": "R3", "commercialization_stage": "C2"}',
            ),
        )

        # main 侧契约要求显式 reviewer/note(min_length=1);
        # 阶段写入由请求 stage_after 驱动 (evidence_review_repository: decision==approved and stage_after)
        result = _review_business_tag_evidence(
            event_id,
            BusinessTagEvidenceReviewRequest(
                review_status="approved",
                reviewer="pytest",
                note="审核门回归测试",
                stage_after={"research_stage": "R3", "commercialization_stage": "C2"},
            ),
        )
        assert result["review_status"] == "approved"
        assert result["stage_updated"] is True

        cur.execute(
            """
            SELECT review_status, reviewer, review_note, reviewed_at
            FROM business_tag_evidence_events
            WHERE event_id = %s
            """,
            (event_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "approved"
        assert row[1] and str(row[1]).strip(), "reviewer 必须非空(审核门审计字段)"
        assert row[2] and str(row[2]).strip(), "review_note 必须非空(审核门审计字段)"
        assert row[3] is not None, "reviewed_at 必须非空(审核门审计字段)"

        cur.execute(
            """
            SELECT review_status, research_stage, commercialization_stage
            FROM business_tag_stage_tracking
            WHERE source_event_id = %s
            """,
            (event_id,),
        )
        stage_row = cur.fetchone()
        assert stage_row is not None, "approve 后应写入 stage_tracking"
        assert stage_row[0] == "approved"
        assert stage_row[1] == "R3"
        assert stage_row[2] == "C2"
    finally:
        cur.execute("DELETE FROM business_tag_stage_tracking WHERE mapping_id = %s", (mapping_id,))
        cur.execute("DELETE FROM business_tag_evidence_events WHERE mapping_id = %s", (mapping_id,))
        cur.execute("DELETE FROM business_tag_mapping WHERE mapping_id = %s", (mapping_id,))
        conn.close()
