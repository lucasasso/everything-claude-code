"""Time-weighted Dixon-Coles model fitted on goals blended with xG.

log(lambda_home) = mu + home_adv[comp] + attack[home] + defence[away]
log(lambda_away) = mu                  + attack[away] + defence[home]

`defence` is the tendency to concede (higher = worse). Ridge shrinkage keeps teams
with few matches (small European clubs, newly promoted sides) close to average.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import poisson

HALF_LIFE_DAYS = 180.0
GOALS_WEIGHT = 0.4  # target = 0.4 * goals + 0.6 * xG when xG is available
RIDGE = 0.15
MAX_GOALS = 10
MAX_ADJUSTMENT = 0.25


class TeamModel:
    def __init__(self, *, teams: list[str], mu: float, home_adv: dict[str, float], attack: np.ndarray,
                 defence: np.ndarray, rho: float, fitted_on: date) -> None:
        self.teams = teams
        self.index = {t: i for i, t in enumerate(teams)}
        self.mu = mu
        self.home_adv = home_adv
        self.attack = attack
        self.defence = defence
        self.rho = rho
        self.fitted_on = fitted_on

    def expected_goals(self, home: str, away: str, comp: str, adjustments: dict | None = None) -> tuple[float, float]:
        for team in (home, away):
            if team not in self.index:
                raise KeyError(f"Squadra sconosciuta per il modello: {team!r}. Aggiungi un alias in common.ALIASES.")
        h, a = self.index[home], self.index[away]
        adv = self.home_adv.get(comp, float(np.mean(list(self.home_adv.values()))))
        lam = math.exp(self.mu + adv + self.attack[h] + self.defence[a])
        mu = math.exp(self.mu + self.attack[a] + self.defence[h])

        adj = adjustments or {}
        home_adj, away_adj = adj.get(home, {}), adj.get(away, {})
        lam *= (1 + _clip(home_adj.get("attacco", 0))) * (1 + _clip(away_adj.get("difesa", 0)))
        mu *= (1 + _clip(away_adj.get("attacco", 0))) * (1 + _clip(home_adj.get("difesa", 0)))
        return lam, mu

    def score_matrix(self, lam: float, mu: float) -> np.ndarray:
        goals = np.arange(MAX_GOALS + 1)
        matrix = np.outer(poisson.pmf(goals, lam), poisson.pmf(goals, mu))
        rho = self.rho
        matrix[0, 0] *= 1 - lam * mu * rho
        matrix[0, 1] *= 1 + lam * rho
        matrix[1, 0] *= 1 + mu * rho
        matrix[1, 1] *= 1 - rho
        return matrix / matrix.sum()

    def predict(self, home: str, away: str, comp: str, adjustments: dict | None = None) -> dict:
        lam, mu = self.expected_goals(home, away, comp, adjustments)
        return {"xg_home": round(lam, 2), "xg_away": round(mu, 2), "markets": markets_from_matrix(self.score_matrix(lam, mu))}

    def ratings(self) -> list[dict]:
        rows = [{"team": t, "attacco": float(self.attack[i]), "difesa": float(self.defence[i]),
                 "forza": float(self.attack[i] - self.defence[i])} for t, i in self.index.items()]
        return sorted(rows, key=lambda r: r["forza"], reverse=True)


def _clip(value: float) -> float:
    return max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, float(value)))


def markets_from_matrix(m: np.ndarray) -> dict:
    """Probabilities for the markets the slip builder understands."""
    n = m.shape[0]
    hg, ag = np.indices(m.shape)
    total = hg + ag
    p1, px, p2 = float(np.tril(m, -1).sum()), float(np.trace(m)), float(np.triu(m, 1).sum())
    out = {
        "1X2": {"1": p1, "X": px, "2": p2},
        "DC": {"1X": p1 + px, "X2": px + p2, "12": p1 + p2},
        "GG/NG": {"GG": float(m[1:, 1:].sum()), "NG": float(1 - m[1:, 1:].sum())},
    }
    for line in (1.5, 2.5, 3.5):
        over = float(m[total > line].sum())
        out[f"OU{line}"] = {f"Over {line}": over, f"Under {line}": 1 - over}
    flat = sorted(((float(m[i, j]), f"{i}-{j}") for i in range(n) for j in range(n)), reverse=True)
    out["Risultato esatto"] = {score: p for p, score in flat[:6]}
    return out


def fit(matches: list[dict], as_of: date, half_life: float = HALF_LIFE_DAYS, goals_weight: float = GOALS_WEIGHT,
        domestic_comps: tuple[str, ...] | None = None) -> TeamModel:
    """Fit on matches played before `as_of`. Each match: date, comp, home, away, hg, ag, hxg, axg.

    Team strength = league offset + team deviation. Ridge shrinks each team towards its own
    league, and European matches pin the league offsets, so a Belgian or Norwegian side is not
    rated like an average Serie A team just because it dominates at home.
    """
    played = [m for m in matches if m["date"] < as_of]
    if not played:
        raise ValueError("Nessuna partita disponibile per stimare il modello.")
    teams = sorted({m["home"] for m in played} | {m["away"] for m in played})
    comps = sorted({m["comp"] for m in played})
    t_idx, c_idx = {t: i for i, t in enumerate(teams)}, {c: i for i, c in enumerate(comps)}
    team_league = _home_leagues(played, teams, domestic_comps)
    leagues = sorted(set(team_league))
    lg_of = np.array([leagues.index(team_league[i]) for i in range(len(teams))])
    n, k, nl = len(teams), len(comps), len(leagues)

    home = np.array([t_idx[m["home"]] for m in played])
    away = np.array([t_idx[m["away"]] for m in played])
    comp = np.array([c_idx[m["comp"]] for m in played])
    hg = np.array([m["hg"] for m in played], dtype=float)
    ag = np.array([m["ag"] for m in played], dtype=float)
    yh = np.array([_target(m["hg"], m.get("hxg"), goals_weight) for m in played])
    ya = np.array([_target(m["ag"], m.get("axg"), goals_weight) for m in played])
    age = np.array([(as_of - m["date"]).days for m in played], dtype=float)
    w = np.exp(-math.log(2) / half_life * age)
    ridge = RIDGE * w.sum() / n
    sizes = (1, k, nl, nl, n, n)
    cuts = np.cumsum(sizes)[:-1]

    def strengths(p: np.ndarray) -> tuple:
        mu, adv, latt, ldef, att, dfc = np.split(p, cuts)
        return mu[0], adv, latt[lg_of] + att, ldef[lg_of] + dfc, latt, ldef, att, dfc

    def loss(p: np.ndarray) -> tuple[float, np.ndarray]:
        mu, adv, a_tot, d_tot, latt, ldef, att, dfc = strengths(p)
        log_l = mu + adv[comp] + a_tot[home] + d_tot[away]
        log_m = mu + a_tot[away] + d_tot[home]
        lam, lmu = np.exp(log_l), np.exp(log_m)
        value = (-np.sum(w * (yh * log_l - lam + ya * log_m - lmu))
                 + ridge * (att @ att + dfc @ dfc) + ridge * 1e-3 * (latt @ latt + ldef @ ldef))
        rl, rm = -w * (yh - lam), -w * (ya - lmu)
        g_att = np.bincount(home, rl, n) + np.bincount(away, rm, n)
        g_def = np.bincount(away, rl, n) + np.bincount(home, rm, n)
        grad = np.concatenate([
            [rl.sum() + rm.sum()], np.bincount(comp, rl, k),
            np.bincount(lg_of, g_att, nl) + 2e-3 * ridge * latt, np.bincount(lg_of, g_def, nl) + 2e-3 * ridge * ldef,
            g_att + 2 * ridge * att, g_def + 2 * ridge * dfc,
        ])
        return value, grad

    x0 = np.zeros(sum(sizes))
    x0[0], x0[1:1 + k] = math.log(1.3), 0.2
    params = minimize(loss, x0, jac=True, method="L-BFGS-B").x
    mu, adv, a_tot, d_tot, *_ = strengths(params)

    lam = np.exp(mu + adv[comp] + a_tot[home] + d_tot[away])
    lmu = np.exp(mu + a_tot[away] + d_tot[home])
    rho = _fit_rho(hg, ag, lam, lmu, w)
    return TeamModel(teams=teams, mu=float(mu), home_adv=dict(zip(comps, map(float, adv))),
                     attack=a_tot, defence=d_tot, rho=rho, fitted_on=as_of)


def _home_leagues(played: list[dict], teams: list[str], domestic_comps: tuple[str, ...] | None) -> list[str]:
    """Each team's domestic league; teams seen only in European cups share the 'altro' league."""
    counts: dict[str, dict[str, int]] = {t: {} for t in teams}
    for m in played:
        if domestic_comps is None or m["comp"] in domestic_comps:
            for t in (m["home"], m["away"]):
                counts[t][m["comp"]] = counts[t].get(m["comp"], 0) + 1
    return [max(counts[t], key=counts[t].get) if counts[t] else "altro" for t in teams]


def _target(goals: int, xg: float | None, goals_weight: float) -> float:
    return float(goals) if xg is None else goals_weight * goals + (1 - goals_weight) * xg


def _fit_rho(hg: np.ndarray, ag: np.ndarray, lam: np.ndarray, mu: np.ndarray, w: np.ndarray) -> float:
    def neg_ll(rho: float) -> float:
        tau = np.ones_like(lam)
        tau = np.where((hg == 0) & (ag == 0), 1 - lam * mu * rho, tau)
        tau = np.where((hg == 0) & (ag == 1), 1 + lam * rho, tau)
        tau = np.where((hg == 1) & (ag == 0), 1 + mu * rho, tau)
        tau = np.where((hg == 1) & (ag == 1), 1 - rho, tau)
        return -float(np.sum(w * np.log(np.clip(tau, 1e-9, None))))

    return float(minimize_scalar(neg_ll, bounds=(-0.2, 0.1), method="bounded").x)
