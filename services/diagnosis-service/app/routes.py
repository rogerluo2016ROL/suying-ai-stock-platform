"""Diagnosis API routes — 6 endpoints covering AC-12.1~12.7.

All endpoints authenticated (all roles can access per PRD).

Endpoints:
  1. POST /api/v1/diagnosis/analyze        — Run 5-dimension diagnosis (AC-12.1~12.4)
  2. POST /api/v1/diagnosis/compare        — Compare 2-5 stocks side-by-side (AC-12.6)
  3. GET  /api/v1/diagnosis/report/{code}  — Get latest report for a stock (AC-12.5)
  4. GET  /api/v1/diagnosis/report/{code}/pdf — Export report as PDF (AC-12.5)
  5. GET  /api/v1/diagnosis/history        — List diagnosis history (AC-12.7)
  6. GET  /api/v1/diagnosis/history/{id}   — Get single history record (AC-12.7)
"""

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import require_role, security
from app.diagnosis_engine import diagnose as run_diagnosis
from app.schemas import (
    DiagnosisAnalyzeRequest,
    DiagnosisCompareRequest,
    DiagnosisCompareResponse,
    DiagnosisHistoryItem,
    DiagnosisReport,
    ErrorResponse,
    PaginatedDiagnosisHistory,
)

logger = logging.getLogger("diagnosis-service.routes")

router = APIRouter(prefix="/api/v1/diagnosis", tags=["diagnosis"])

# All four roles can access diagnosis (AC-12 constraint: 所有角色可见)
ALL_ROLES = ("admin", "internal_analyst", "external_analyst", "user")

# C2 fix: detect Playwright availability for PDF chart rendering
PLAYWRIGHT_AVAILABLE = os.environ.get("PLAYWRIGHT_AVAILABLE", "").lower() in ("1", "true", "yes")
if not PLAYWRIGHT_AVAILABLE:
    try:
        from playwright.async_api import async_playwright
        PLAYWRIGHT_AVAILABLE = True
    except ImportError:
        PLAYWRIGHT_AVAILABLE = False
logger.info("Playwright available for PDF rendering: %s", PLAYWRIGHT_AVAILABLE)


# ═══════════════════════════════════════════════════════════════════════════
# 1. POST /analyze — Run 5-dimension diagnosis (AC-12.1~12.4)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/analyze",
    response_model=DiagnosisReport,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid stock code"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        500: {"model": ErrorResponse, "description": "Diagnosis failed"},
    },
)
async def analyze_stock(
    body: DiagnosisAnalyzeRequest,
    user: dict = Depends(require_role(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Run a complete five-dimension diagnosis for a single stock.

    Dimensions and weights (ADR-005):
    - 技术面 40% — 25-factor composite score
    - 资金面 25% — Northbound/margin/leaderboard/main-force flow
    - 基本面 20% — PE percentile/ROE/revenue growth/debt ratio
    - AI预测 10% — Kronos 30-day forecast
    - 情绪面 5% — News sentiment + research ratings

    Returns comprehensive report with overall score (0-100), recommendation grade
    (强烈买入/买入/持有/减仓/卖出), five dimension sub-scores, key support/resistance
    levels, and risk warnings.
    """
    code = body.code.strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stock code is required",
        )

    # Basic validation: 6-digit numeric code
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stock code format. Expected 6-digit code (e.g. 000001)",
        )

    # Extract JWT token for Kronos auth (C3 fix)
    auth_token = credentials.credentials if credentials else None

    # Check if stock exists in the database
    result = await db.execute(
        sa_text("SELECT 1 FROM stocks WHERE code = :code"),
        {"code": code},
    )
    if result.fetchone() is None:
        # Try daily_kline as fallback
        result = await db.execute(
            sa_text("SELECT 1 FROM daily_kline WHERE code = :code LIMIT 1"),
            {"code": code},
        )
        if result.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stock code '{code}' not found in database",
            )

    try:
        report = await run_diagnosis(
            code, db, force_refresh=body.force_refresh, auth_token=auth_token,
        )

        # Persist diagnosis history (AC-12.7)
        try:
            await db.execute(
                sa_text(
                    "INSERT INTO diagnosis_history (user_id, code, overall_score, grade, "
                    "recommendation, report, created_at) "
                    "VALUES (:user_id, :code, :score, :grade, :rec, :report, :created_at)"
                ),
                {
                    "user_id": str(user["id"]),
                    "code": code,
                    "score": report.overall_score,
                    "grade": report.grade,
                    "rec": report.recommendation.value,
                    "report": json.dumps(report.model_dump(), default=str),
                    "created_at": datetime.now(timezone.utc),
                },
            )
            await db.commit()
        except Exception as e:
            logger.warning("Failed to persist diagnosis history: %s", e)
            await db.rollback()

        return report

    except Exception as e:
        logger.error("Diagnosis failed for %s: %s", code, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Diagnosis failed",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. POST /compare — Compare 2-5 stocks side-by-side (AC-12.6)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/compare",
    response_model=DiagnosisCompareResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
async def compare_stocks(
    body: DiagnosisCompareRequest,
    user: dict = Depends(require_role(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Compare 2-5 stocks with side-by-side five-dimension diagnosis.

    Returns per-stock reports, overall ranking, and a per-dimension comparison matrix.
    Optional `dimensions` parameter filters which dimensions to compare.
    """
    codes = [c.strip() for c in body.codes]
    if len(codes) < 2 or len(codes) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requires 2-5 stock codes for comparison",
        )

    # Validate all codes are 6-digit
    for code in codes:
        if not code.isdigit() or len(code) != 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid stock code: {code}",
            )

    # Extract JWT token for Kronos auth (C3 fix)
    auth_token = credentials.credentials if credentials else None

    # Run all diagnoses concurrently
    import asyncio

    async def diagnose_one(code: str):
        try:
            return await run_diagnosis(
                code, db, force_refresh=body.force_refresh, auth_token=auth_token,
            )
        except Exception as e:
            logger.warning("Compare: diagnosis failed for %s: %s", code, e)
            return None

    results = await asyncio.gather(*[diagnose_one(c) for c in codes])
    reports = [r for r in results if r is not None]

    if len(reports) < 2:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Too few successful diagnoses to compare",
        )

    # Build ranking by overall score
    ranking = [
        {
            "rank": i + 1,
            "code": r.code,
            "overall_score": r.overall_score,
            "grade": r.grade,
            "recommendation": r.recommendation.value,
        }
        for i, r in enumerate(sorted(reports, key=lambda x: x.overall_score, reverse=True))
    ]

    # Build dimension comparison matrix
    dimension_comparison = {}
    all_dims = ["technical", "capital_flow", "fundamental", "ai_predict", "sentiment"]
    dim_names = {
        "technical": "技术面",
        "capital_flow": "资金面",
        "fundamental": "基本面",
        "ai_predict": "AI预测",
        "sentiment": "情绪面",
    }
    requested_dims = body.dimensions if body.dimensions else all_dims

    for dim_key in requested_dims:
        if dim_key not in all_dims:
            continue
        dim_comparison = []
        for r in reports:
            d = r.dimensions.get(dim_key)
            if d:
                dim_comparison.append({
                    "code": r.code,
                    "score": d.score,
                    "grade": d.grade,
                    "signals": d.signals,
                })
        if dim_comparison:
            dimension_comparison[dim_names.get(dim_key, dim_key)] = dim_comparison

    return DiagnosisCompareResponse(
        stocks=reports,
        ranking=ranking,
        dimension_comparison=dimension_comparison,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. GET /report/{code} — Get latest report for a stock (AC-12.5)
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/report/{code}",
    response_model=DiagnosisReport,
    responses={
        404: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
async def get_report(
    code: str,
    user: dict = Depends(require_role(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Retrieve the most recent diagnosis report for a stock.

    Returns the latest cached/persisted report without re-running the diagnosis.
    To force a fresh diagnosis, use POST /analyze with force_refresh=true.
    """
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid stock code")

    # Query latest from history
    result = await db.execute(
        sa_text(
            "SELECT report FROM diagnosis_history "
            "WHERE code = :code ORDER BY created_at DESC LIMIT 1"
        ),
        {"code": code},
    )
    row = result.fetchone()
    if row:
        report_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return report_data

    # No cached report — run fresh diagnosis
    auth_token = credentials.credentials if credentials else None
    try:
        report = await run_diagnosis(code, db, auth_token=auth_token)
        return report
    except Exception as e:
        logger.exception("Failed to generate report for %s", code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate report",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. GET /report/{code}/pdf — Export report as PDF (AC-12.5)
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/report/{code}/pdf",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF diagnosis report",
        },
        404: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
async def export_report_pdf(
    code: str,
    user: dict = Depends(require_role(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Export the diagnosis report as a PDF document.

    Per ADR-005 Decision 2: uses Playwright headless Chrome to render
    the frontend report page as PDF when PLAYWRIGHT_AVAILABLE=true.
    Falls back to a simple HTML report when Playwright is unavailable
    (known limitation — charts will be static placeholders).
    """
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid stock code")

    # Get the report data
    auth_token = credentials.credentials if credentials else None
    report_data = None
    try:
        result = await db.execute(
            sa_text(
                "SELECT report FROM diagnosis_history "
                "WHERE code = :code ORDER BY created_at DESC LIMIT 1"
            ),
            {"code": code},
        )
        row = result.fetchone()
        if row:
            report_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except Exception as e:
        logger.warning("diagnosis_history query failed for %s: %s — falling back to fresh diagnosis", code, e)
        await db.rollback()

    if report_data is None:
        report = await run_diagnosis(code, db, auth_token=auth_token)
        report_data = report.model_dump()

    # C2 fix: check Playwright availability
    if PLAYWRIGHT_AVAILABLE:
        try:
            pdf_bytes = await _generate_pdf_playwright(code, report_data)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="diagnosis_{code}_{datetime.now(timezone.utc).strftime("%Y%m%d")}.pdf"',
                },
            )
        except Exception as e:
            logger.warning("Playwright PDF generation failed for %s: %s, falling back to HTML", code, e)

    # Degraded mode: return HTML report (known limitation — no chart rendering)
    html_content = _build_report_html(code, report_data)
    degraded_html = _build_degraded_html(html_content, code)
    return Response(
        content=degraded_html.encode("utf-8"),
        media_type="text/html",
        headers={
            "Content-Disposition": f'inline; filename="diagnosis_{code}_{datetime.now(timezone.utc).strftime("%Y%m%d")}.html"',
            "X-Diagnosis-Pdf-Degraded": "true",
            "X-Degraded-Reason": "Playwright unavailable - charts rendered as static placeholders",
        },
    )


async def _generate_pdf_playwright(code: str, report_data: dict) -> bytes:
    """Generate PDF using Playwright headless Chrome (ADR-005 Decision 2)."""
    import asyncio

    # Build an HTML page that renders the diagnosis report
    html = _build_report_html(code, report_data)

    # Try Playwright
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("Playwright not installed")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            format="A4",
            margin={"top": "15mm", "bottom": "15mm", "left": "13mm", "right": "13mm"},
            print_background=True,
        )
        await browser.close()
        return pdf_bytes


def _build_degraded_html(html: str, code: str) -> str:
    """Wrap HTML report with degradation banner (C2 fix — known limitation).

    Adds a visible banner noting that charts are rendered as static placeholders
    because Playwright is unavailable.
    """
    banner = f"""
    <div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;
                padding:12px 20px;margin:16px 0;font-size:14px;color:#92400e;">
      <strong>Known Limitation:</strong> Charts (K-line, radar) are rendered as static
      placeholders because Playwright headless Chrome is unavailable in this environment.
      For full chart rendering, set <code>PLAYWRIGHT_AVAILABLE=true</code> and ensure
      <code>playwright</code> is installed with <code>playwright install chromium</code>.
    </div>
    """
    # Insert banner right after <body>
    html = html.replace("<body>", f"<body>\n{banner}")
    return html


async def _generate_pdf_playwright(code: str, report_data: dict) -> bytes:
    """Generate PDF using Playwright headless Chrome (ADR-005 Decision 2).

    Renders the HTML report (with inline chart placeholders) as A4 PDF.
    For full JavaScript chart rendering, the frontend diagnosis page URL
    should be used instead (per ADR-005 Decision 2 original intent).
    """
    from playwright.async_api import async_playwright

    html = _build_report_html(code, report_data)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            format="A4",
            margin={"top": "15mm", "bottom": "15mm", "left": "13mm", "right": "13mm"},
            print_background=True,
        )
        await browser.close()
        return pdf_bytes


def _build_report_html(code: str, report_data: dict) -> str:
    """Build a professional HTML report page from diagnosis data."""
    r = report_data
    dims = r.get("dimensions", {})
    dim_order = [
        ("technical", "技术面"),
        ("capital_flow", "资金面"),
        ("fundamental", "基本面"),
        ("ai_predict", "AI预测"),
        ("sentiment", "情绪面"),
    ]

    def dim_row(key, label):
        d = dims.get(key, {})
        score = d.get("score", 0)
        grade = d.get("grade", "-")
        signals = d.get("signals") or []
        color = "#22c55e" if score >= 70 else "#f59e0b" if score >= 50 else "#ef4444"
        sigs_html = "".join(f'<span class="tag">{s}</span>' for s in signals[:3])
        return f"""
        <tr>
          <td style="font-weight:600">{label}</td>
          <td>
            <div style="background:#e5e7eb;border-radius:6px;height:18px;width:200px">
              <div style="background:{color};height:18px;border-radius:6px;width:{score}%"></div>
            </div>
          </td>
          <td style="font-weight:700;color:{color}">{score:.0f}</td>
          <td>{grade}</td>
          <td>{sigs_html}</td>
        </tr>"""

    levels = r.get("key_levels", {})
    warnings = r.get("risk_warnings", [])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>个股诊断报告 — {code}</title>
<style>
  body {{ font-family: "PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif; color:#1f2937; max-width:900px; margin:0 auto; padding:30px 20px; }}
  h1 {{ color:#1e3a5f; border-bottom:3px solid #2563eb; padding-bottom:10px; }}
  .hero {{ background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%); color:#fff; padding:20px 30px; border-radius:12px; margin:20px 0; display:flex; align-items:center; gap:40px; }}
  .hero-score {{ text-align:center; }}
  .hero-score .num {{ font-size:48px; font-weight:800; }}
  .hero-score .label {{ font-size:14px; opacity:.85; }}
  .hero-grade {{ font-size:24px; font-weight:700; }}
  table {{ width:100%; border-collapse:collapse; margin:15px 0; }}
  th {{ background:#f3f4f6; padding:10px 12px; text-align:left; font-size:14px; }}
  td {{ padding:10px 12px; border-bottom:1px solid #e5e7eb; font-size:14px; }}
  .tag {{ display:inline-block; background:#dbeafe; color:#1e40af; padding:2px 8px; border-radius:4px; font-size:12px; margin:2px; }}
  .warn {{ background:#fef2f2; color:#b91c1c; padding:8px 12px; border-radius:6px; margin:6px 0; font-size:13px; }}
  .levels {{ display:flex; gap:20px; }}
  .level-card {{ background:#f9fafb; border:1px solid #e5e7eb; border-radius:8px; padding:14px 18px; flex:1; text-align:center; }}
  .level-card .val {{ font-size:20px; font-weight:700; color:#2563eb; }}
  .level-card .label {{ font-size:12px; color:#6b7280; }}
  .rec {{ padding:10px 24px; border-radius:8px; font-weight:700; font-size:18px; display:inline-block; }}
  .rec-buy {{ background:#dcfce7; color:#166534; }}
  .rec-sell {{ background:#fef2f2; color:#b91c1c; }}
  .rec-hold {{ background:#fef9c3; color:#854d0e; }}
</style>
</head>
<body>
<h1>📊 个股诊断报告</h1>
<div style="color:#6b7280">股票代码: {code} | 生成时间: {r.get('created_at', '')}</div>

<div class="hero">
  <div class="hero-score">
    <div class="num">{r.get('overall_score', 0):.0f}</div>
    <div class="label">综合评分 / 100</div>
  </div>
  <div>
    <div class="hero-grade">等级: {r.get('grade', '-')}</div>
    <div class="rec rec-{'buy' if '买入' in str(r.get('recommendation','')) else 'sell' if '卖出' in str(r.get('recommendation','')) or '减仓' in str(r.get('recommendation','')) else 'hold'}">{r.get('recommendation', '-')}</div>
    <div style="margin-top:8px;font-size:13px;opacity:.9">{r.get('recommendation_reason', '')}</div>
  </div>
</div>

<h2>📈 五维评分明细</h2>
<table>
  <tr><th>维度</th><th>评分条</th><th>分数</th><th>等级</th><th>关键信号</th></tr>
  {''.join(dim_row(k, l) for k, l in dim_order)}
</table>

<h2>🎯 关键价位</h2>
<div class="levels">
  <div class="level-card"><div class="label">支撑位</div><div class="val">{levels.get('support', '-')}</div></div>
  <div class="level-card"><div class="label">阻力位</div><div class="val">{levels.get('resistance', '-')}</div></div>
  <div class="level-card"><div class="label">止损位</div><div class="val">{levels.get('stop_loss', '-')}</div></div>
</div>

{f'<h2>⚠️ 风险提示</h2>' + ''.join(f'<div class="warn">• {w}</div>' for w in warnings) if warnings else ''}
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════
# 5. GET /history — List diagnosis history (AC-12.7)
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/history",
    response_model=PaginatedDiagnosisHistory,
    responses={401: {"model": ErrorResponse}},
)
async def get_diagnosis_history(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    code: Optional[str] = Query(None, description="Filter by stock code"),
    user: dict = Depends(require_role(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Query diagnosis history with optional filtering and pagination (AC-12.7).

    Results are ordered by created_at descending (most recent first).
    Supports filtering by stock code and pagination.
    """
    # Build query
    where_clauses = ["1=1"]
    params = {}

    if code:
        where_clauses.append("code = :code")
        params["code"] = code

    where_sql = " AND ".join(where_clauses)

    # Count total
    count_result = await db.execute(
        sa_text(f"SELECT COUNT(*) FROM diagnosis_history WHERE {where_sql}"),
        params,
    )
    total = count_result.fetchone()[0]

    # Fetch page
    offset = (page - 1) * page_size
    list_result = await db.execute(
        sa_text(
            f"SELECT id, user_id, code, overall_score, grade, recommendation, report, created_at "
            f"FROM diagnosis_history WHERE {where_sql} "
            f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = list_result.fetchall()

    items = [
        DiagnosisHistoryItem(
            id=row[0],
            user_id=str(row[1]),
            code=row[2],
            overall_score=float(row[3]),
            grade=row[4],
            recommendation=row[5],
            report=json.loads(row[6]) if isinstance(row[6], str) else row[6],
            created_at=row[7],
        )
        for row in rows
    ]

    total_pages = max(1, math.ceil(total / page_size))

    return PaginatedDiagnosisHistory(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. GET /history/{id} — Get single history record (AC-12.7)
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/history/{record_id}",
    response_model=DiagnosisHistoryItem,
    responses={
        404: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
async def get_diagnosis_history_detail(
    record_id: int,
    user: dict = Depends(require_role(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single diagnosis history record by ID (AC-12.7)."""
    result = await db.execute(
        sa_text(
            "SELECT id, user_id, code, overall_score, grade, recommendation, report, created_at "
            "FROM diagnosis_history WHERE id = :id"
        ),
        {"id": record_id},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnosis history record #{record_id} not found",
        )

    return DiagnosisHistoryItem(
        id=row[0],
        user_id=str(row[1]),
        code=row[2],
        overall_score=float(row[3]),
        grade=row[4],
        recommendation=row[5],
        report=json.loads(row[6]) if isinstance(row[6], str) else row[6],
        created_at=row[7],
    )
