"""Diagnosis API routes — 5-dimension analysis + Kronos prediction visualization."""

from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/api/v1/diagnosis", tags=["diagnosis"])


@router.post("/analyze")
async def analyze_stock(code: str):
    """Run 5-dimension stock diagnosis.

    Dimensions: 📊Technical(40%) + 💰Capital(25%) + 📈Fundamental(20%)
              + 🤖AI-Predict(10%) + 🎯Sentiment(5%)
    """
    if not code:
        raise HTTPException(status_code=400, detail="Stock code required")

    return {
        "code": code,
        "overall_score": 78,
        "grade": "B+",
        "recommendation": "BUY",
        "dimensions": {
            "technical":    {"score": 7.8, "weight": 0.40, "grade": "A"},
            "capital_flow": {"score": 8.2, "weight": 0.25, "grade": "A"},
            "fundamental":  {"score": 6.5, "weight": 0.20, "grade": "B"},
            "ai_predict":   {"score": 7.0, "weight": 0.10, "grade": "B", "pred_return": 15.8},
            "sentiment":    {"score": 5.5, "weight": 0.05, "grade": "C"},
        },
        "kronos_prediction": {
            "pred_30d_close": 15.80,
            "pred_return_pct": 17.0,
            "max_drawdown_pct": -4.2,
            "trend": "📈 上升 (第8天加速)",
            "inflection_days": [8, 18],
        },
        "key_levels": {"support": 12.50, "resistance": 16.80, "stop_loss": 11.80},
        "risk_warnings": ["高位获利盘抛压", "板块轮动风险"],
        "message": "Diagnosis endpoint ready. Data will populate with DB connection.",
    }


@router.get("/report/{code}")
async def get_report(code: str, format: str = Query("json", description="json/pdf")):
    """Get diagnosis report for a stock."""
    return {
        "code": code,
        "format": format,
        "report_url": f"/reports/diagnosis_{code}.{format}",
        "status": "endpoint_ready",
    }


@router.post("/compare")
async def compare_stocks(
    codes: list[str],
    dimensions: list[str] = Query(None, description="Dimensions to compare"),
):
    """Compare multiple stocks side-by-side."""
    if len(codes) > 5:
        raise HTTPException(status_code=400, detail="Max 5 stocks for comparison")
    return {
        "codes": codes,
        "dimensions": dimensions or ["technical", "capital_flow", "fundamental", "ai_predict"],
        "comparison": [],
        "status": "endpoint_ready",
    }
