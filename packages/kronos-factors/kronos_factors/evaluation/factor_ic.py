from dataclasses import dataclass
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
    value = spearmanr(scores[mask], returns[mask]).statistic
    return CrossSectionIC(float(value) if np.isfinite(value) else 0.0, int(mask.sum()))
