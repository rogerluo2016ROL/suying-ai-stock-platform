"""12-Model Fusion Screening Engine — V4.0 screening_top50.py wrapper.

Delegates to Kronos/tools/screening_top50.py for the full 50+ factor
scoring pipeline, adapted for service-layer PG data source.

Provides:
  - ScreeningTop50Engine: unified entry for all 7 modes
  - FusionScorer: LGBM + Linear weighted fusion
"""
import os, sys, logging

logger = logging.getLogger("kronos.screening_top50")

# Ensure Kronos tools are importable
_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
_kronos_tools = os.path.join(_PROJ, "Kronos", "tools")
_kronos_src = os.path.join(_PROJ, "Kronos", "src")
for p in [_kronos_tools, _kronos_src, _PROJ]:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)


class ScreeningTop50Engine:
    """V4.0 12-model fusion screening — 50+ factors, 7 modes.

    Modes: leader_auction, leader_scalp, intraday, short, long, all, chokepoint
    """

    def __init__(self, pg_url: str = None):
        self.pg_url = pg_url or os.environ.get(
            "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

    def run(self, mode: str = "all", top_n: int = 30, trade_date: str = None,
            lgbm_model=None, lgbm_cols=None) -> list[dict]:
        """Execute full screening pipeline.

        Returns: [{code, name, score, grade, reason, ...}, ...]
        """
        try:
            from screening_top50 import run_screening, get_fusion_scorer
        except ImportError:
            logger.warning("Kronos screening_top50 not available — using lightweight mode")
            return self._run_lightweight(mode, top_n, trade_date)

        if lgbm_model is None:
            try:
                lgbm_model, lgbm_cols = get_fusion_scorer()
            except Exception:
                pass

        picks = run_screening(
            mode=mode, top_n=top_n, method="fusion",
            lgbm_model=lgbm_model, lgbm_cols=lgbm_cols,
        )
        return picks[:top_n] if picks else []

    def _run_lightweight(self, mode: str, top_n: int, trade_date: str = None) -> list[dict]:
        """Lightweight fallback using PG materialized view."""
        import psycopg2
        conn = psycopg2.connect(self.pg_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT code, name, industry, gain_pct, composite_score
            FROM mv_daily_composite_ranking
            ORDER BY composite_score DESC LIMIT %s
        """, (top_n,))
        picks = []
        for r in cur.fetchall():
            picks.append({
                "code": r[0], "name": r[1], "industry": r[2],
                "gain_pct": float(r[3] or 0), "score": float(r[4] or 0),
                "grade": "B" if float(r[4] or 0) > 50 else "C",
                "reason": f"综合评分 {float(r[4] or 0):.0f}",
            })
        conn.close()
        return picks


class FusionScorer:
    """LGBM + Linear weighted fusion scorer."""

    def __init__(self):
        try:
            from screening_top50 import get_fusion_scorer
            self.model, self.cols = get_fusion_scorer()
        except Exception:
            self.model, self.cols = None, []

    def score(self, features: dict) -> float:
        if self.model is None:
            return 50.0
        import numpy as np
        feats = [features.get(c, 0) for c in self.cols]
        return float(self.model.predict(np.array([feats]))[0])
