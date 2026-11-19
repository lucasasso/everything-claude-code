"""Every market a slip can use (combo, multigol, team goals) from one market-calibrated score matrix.

The model alone is less accurate than the market, so the score matrix is first re-fitted to the
market's 1X2 and over/under prices; correlated outcomes (sign + goals) then stay consistent.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize

from model import MAX_GOALS, score_matrix

SIGNS = ("1", "X", "2", "1X", "X2", "12")
MULTIGOL = ((1, 2), (1, 3), (2, 3), (2, 4), (3, 5), (1, 4), (2, 5))
COMBO_GOALS = ("Over 1.5", "Under 3.5", "Over 2.5", "Under 2.5", "GG", "NG", "Multigol 1-3", "Multigol 2-4")


def _sign_mask(shape: tuple[int, int], sign: str) -> np.ndarray:
    hg, ag = np.indices(shape)
    parts = {"1": hg > ag, "X": hg == ag, "2": hg < ag}
    mask = np.zeros(shape, dtype=bool)
    for ch in sign:
        mask |= parts[ch]
    return mask


def _goal_masks(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    hg, ag = np.indices(shape)
    total = hg + ag
    masks = {}
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        masks[f"Over {line}"] = total > line
        masks[f"Under {line}"] = total < line
    masks["GG"], masks["NG"] = (hg > 0) & (ag > 0), (hg == 0) | (ag == 0)
    for lo, hi in MULTIGOL:
        masks[f"Multigol {lo}-{hi}"] = (total >= lo) & (total <= hi)
    for line in (0.5, 1.5):
        masks[f"Casa Over {line}"], masks[f"Ospite Over {line}"] = hg > line, ag > line
        masks[f"Casa Under {line}"], masks[f"Ospite Under {line}"] = hg < line, ag < line
    return masks


def all_selections(matrix: np.ndarray) -> dict[str, float]:
    """Probability of every single and combo selection."""
    shape = matrix.shape
    goals = _goal_masks(shape)
    out = {f"Segno {s}": float(matrix[_sign_mask(shape, s)].sum()) for s in SIGNS}
    out.update({name: float(matrix[mask].sum()) for name, mask in goals.items()})
    for s in SIGNS:
        for g in COMBO_GOALS:
            out[f"{s} + {g}"] = float(matrix[_sign_mask(shape, s) & goals[g]].sum())
    return out


def calibrated_rates(lam: float, mu: float, rho: float, fair_1x2: dict | None,
                     fair_total: tuple[float, float] | None) -> tuple[float, float]:
    """Expected goals that reproduce the market's 1X2 (and over/under, when known)."""
    if not fair_1x2:
        return lam, mu
    hg, ag = np.indices((MAX_GOALS + 1, MAX_GOALS + 1))

    def loss(x: np.ndarray) -> float:
        m = score_matrix(math.exp(x[0]), math.exp(x[1]), rho)
        err = (m[hg > ag].sum() - fair_1x2["1"]) ** 2 + (m[hg < ag].sum() - fair_1x2["2"]) ** 2
        if fair_total:
            line, p_over = fair_total
            err += (m[hg + ag > line].sum() - p_over) ** 2
        return float(err)

    x = minimize(loss, np.log([lam, mu]), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-10}).x
    return math.exp(x[0]), math.exp(x[1])


def calibrated_matrix(lam: float, mu: float, rho: float, fair_1x2: dict | None,
                      fair_total: tuple[float, float] | None, model_weight: float) -> np.ndarray:
    """Re-fit expected goals to the market, then blend with the model matrix."""
    model_matrix = score_matrix(lam, mu, rho)
    if not fair_1x2:
        return model_matrix
    market_matrix = score_matrix(*calibrated_rates(lam, mu, rho, fair_1x2, fair_total), rho)
    return model_weight * model_matrix + (1 - model_weight) * market_matrix
