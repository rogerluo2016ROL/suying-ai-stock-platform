from collections import defaultdict
from dataclasses import asdict, dataclass
import numpy as np
from scipy.stats import spearmanr

@dataclass(frozen=True)
class CrossSectionIC:
    rank_ic: float
    observations: int

def compute_cross_section_ic(scores: np.ndarray, returns: np.ndarray) -> CrossSectionIC:
    scores = np.asarray(scores, dtype=float); returns = np.asarray(returns, dtype=float)
    mask = np.isfinite(scores) & np.isfinite(returns)
    if mask.sum() < 2:
        return CrossSectionIC(0.0, int(mask.sum()))
    if len(np.unique(scores[mask])) < 2 or len(np.unique(returns[mask])) < 2:
        return CrossSectionIC(0.0, int(mask.sum()))
    value = spearmanr(scores[mask], returns[mask]).statistic
    return CrossSectionIC(float(value) if np.isfinite(value) else 0.0, int(mask.sum()))


def evaluate_factor_rows(rows, *, min_periods=20, min_per_day=30, min_observations=500):
    """Evaluate observed factor snapshots against future adjusted returns."""
    by_factor_date = defaultdict(lambda: defaultdict(list))
    numeric_records = []
    usable_rows = 0
    for row in rows:
        future_return = row.get("future_return")
        factors = row.get("factors") or {}
        if future_return is None or not factors:
            continue
        usable_rows += 1
        numeric_records.append({str(k): float(v) for k, v in factors.items() if isinstance(v, (int, float))})
        for name, score in factors.items():
            if isinstance(score, (int, float)):
                by_factor_date[str(name)][str(row["trade_date"])].append((score, future_return))

    reports = []
    for name, periods in sorted(by_factor_date.items()):
        period_ics = []
        observations = 0
        pooled = []
        for _, pairs in sorted(periods.items()):
            if len(pairs) < min_per_day:
                continue
            ic = compute_cross_section_ic(
                np.asarray([p[0] for p in pairs]), np.asarray([p[1] for p in pairs])
            )
            period_ics.append(ic.rank_ic)
            observations += ic.observations
            pooled.extend(pairs)
        if len(period_ics) < min_periods or observations < min_observations:
            continue
        values = np.asarray(period_ics, dtype=float)
        std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        pooled.sort(key=lambda pair: pair[0])
        bucket = max(1, len(pooled) // 10)
        deciles = [
            float(np.mean([p[1] for p in pooled[i * bucket:(i + 1) * bucket]]))
            for i in range(10) if pooled[i * bucket:(i + 1) * bucket]
        ]
        reports.append({
            "factor_name": name, "rank_ic": float(values.mean()),
            "icir": float(values.mean() / std) if std else 0.0,
            "periods": len(period_ics), "observations": observations, "deciles": deciles,
        })
    correlations = []
    factor_names = sorted({name for record in numeric_records for name in record})
    for index, left in enumerate(factor_names):
        for right in factor_names[index + 1:]:
            pairs = [(record[left], record[right]) for record in numeric_records if left in record and right in record]
            if len(pairs) >= 2:
                correlation = compute_cross_section_ic(
                    np.asarray([p[0] for p in pairs]), np.asarray([p[1] for p in pairs])
                ).rank_ic
                correlations.append({"left": left, "right": right, "rank_correlation": correlation,
                                     "observations": len(pairs)})
    status = "ready" if reports else "insufficient_data"
    trade_dates = sorted({str(row["trade_date"]) for row in rows if row.get("trade_date") is not None})
    return {
        "status": status, "observations": usable_rows, "factors": reports,
        "window_start": trade_dates[0] if trade_dates else None,
        "window_end": trade_dates[-1] if trade_dates else None,
        "correlations": correlations,
        "deciles": [{"factor_name": report["factor_name"], "returns": report["deciles"]} for report in reports],
        "missing_requirements": [] if reports else [
            f"at_least_{min_periods}_periods", f"at_least_{min_per_day}_stocks_per_period",
            f"at_least_{min_observations}_observations",
        ],
    }
