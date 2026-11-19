"""Special markets: corners, cards, shots on target, halves, HT/FT, handicaps, odd/even, scorers.

Counts (corners, cards, shots on target) use the same time-weighted team model as goals, fitted on
league matches, with a negative binomial per side when the data are over-dispersed. Half-time
markets split the market-calibrated expected goals with the league's first-half share.
"""

from __future__ import annotations

import math
import re
from datetime import date

import numpy as np
from scipy.stats import nbinom, poisson

from combo import calibrated_rates
from common import canonical_team
from model import fit

COUNT_STATS = {
    "Corner": lambda m: m.get("corners"),
    "Cartellini": lambda m: (m["cards"][0] + m["cards"][2], m["cards"][1] + m["cards"][3])
    if m.get("cards") and None not in m["cards"] else None,
    "Tiri in porta": lambda m: m.get("sot"),
}
LINES = {
    "Corner": {"tot": (7.5, 8.5, 9.5, 10.5, 11.5), "team": (2.5, 3.5, 4.5, 5.5, 6.5)},
    "Cartellini": {"tot": (2.5, 3.5, 4.5, 5.5), "team": (0.5, 1.5, 2.5)},
    "Tiri in porta": {"tot": (6.5, 7.5, 8.5, 9.5, 10.5), "team": (2.5, 3.5, 4.5, 5.5)},
}
MAX_COUNT = 40
HALF_GRID = 8
MAX_SCORER_SHARE = 0.6
PRIOR_APPEARANCES = 3
"""Goalless appearances added to every scorer, so a hot streak over few games is not taken at face value."""
_LEADER_RE = re.compile(r"Matches:\s*(\d+),\s*Goals:\s*(\d+)")


class CountModel:
    def __init__(self, *, name: str, team_model, shape: float | None) -> None:
        self.name = name
        self.team_model = team_model
        self.shape = shape
        """Negative binomial shape per side; None means Poisson (no over-dispersion)."""

    def side_pmf(self, mean: float) -> np.ndarray:
        n = np.arange(MAX_COUNT + 1)
        if self.shape is None:
            return poisson.pmf(n, mean)
        return nbinom.pmf(n, self.shape, self.shape / (self.shape + mean))

    def markets(self, home: str, away: str, comp: str) -> dict[str, float]:
        lam, mu = self.team_model.expected_goals(home, away, comp)
        ph, pa = self.side_pmf(lam), self.side_pmf(mu)
        total = np.convolve(ph, pa)[: MAX_COUNT + 1]
        joint = np.outer(ph, pa)
        name, out = self.name, {}
        for line in LINES[name]["tot"]:
            over = float(total[int(line) + 1:].sum())
            out[f"{name} Over {line}"], out[f"{name} Under {line}"] = over, 1 - over
        for line in LINES[name]["team"]:
            h_over, a_over = float(ph[int(line) + 1:].sum()), float(pa[int(line) + 1:].sum())
            out[f"{name} Casa Over {line}"], out[f"{name} Casa Under {line}"] = h_over, 1 - h_over
            out[f"{name} Ospite Over {line}"], out[f"{name} Ospite Under {line}"] = a_over, 1 - a_over
        out[f"{name} 1X2: 1"] = float(np.tril(joint, -1).sum())
        out[f"{name} 1X2: X"] = float(np.trace(joint))
        out[f"{name} 1X2: 2"] = float(np.triu(joint, 1).sum())
        return out

    def expected(self, home: str, away: str, comp: str) -> tuple[float, float]:
        return self.team_model.expected_goals(home, away, comp)


def fit_count_models(matches: list[dict], as_of: date, league: str = "I1") -> dict[str, CountModel]:
    models = {}
    for name, getter in COUNT_STATS.items():
        rows = []
        for m in matches:
            values = getter(m) if m["comp"] == league else None
            if values and None not in values:
                rows.append({"date": m["date"], "comp": league, "home": m["home"], "away": m["away"],
                             "hg": int(values[0]), "ag": int(values[1])})
        team_model = fit(rows, as_of=as_of, goals_weight=1.0)
        team_model.rho = 0.0
        models[name] = CountModel(name=name, team_model=team_model, shape=_side_shape(team_model, rows, league))
    return models


def _side_shape(team_model, rows: list[dict], league: str) -> float | None:
    """Method-of-moments NB shape from residuals of the fitted means (both sides pooled)."""
    num = den = 0.0
    for r in rows:
        if r["home"] not in team_model.index or r["away"] not in team_model.index:
            continue
        lam, mu = team_model.expected_goals(r["home"], r["away"], league)
        for y, m in ((r["hg"], lam), (r["ag"], mu)):
            num += (y - m) ** 2 - m
            den += m * m
    inv_shape = num / den if den else 0.0
    return None if inv_shape <= 1e-3 else 1 / inv_shape


def first_half_shares(matches: list[dict], league: str = "I1") -> tuple[float, float]:
    """Share of home and away goals scored before half-time in the league."""
    rows = [m for m in matches if m["comp"] == league and m.get("ht") and None not in m["ht"]]
    hg, ag = sum(m["hg"] for m in rows), sum(m["ag"] for m in rows)
    h1, a1 = sum(m["ht"][0] for m in rows), sum(m["ht"][1] for m in rows)
    return (h1 / hg if hg else 0.45, a1 / ag if ag else 0.45)


def half_markets(lam: float, mu: float, share_home: float, share_away: float) -> dict[str, float]:
    """Half-time, second-half and HT/FT markets with independent Poisson halves."""
    g = np.arange(HALF_GRID + 1)
    first = np.outer(poisson.pmf(g, lam * share_home), poisson.pmf(g, mu * share_away))
    second = np.outer(poisson.pmf(g, lam * (1 - share_home)), poisson.pmf(g, mu * (1 - share_away)))
    first, second = first / first.sum(), second / second.sum()
    out: dict[str, float] = {}
    for label, m in (("1T", first), ("2T", second)):
        hg, ag = np.indices(m.shape)
        out[f"{label} Segno 1"] = float(m[hg > ag].sum())
        out[f"{label} Segno X"] = float(m[hg == ag].sum())
        out[f"{label} Segno 2"] = float(m[hg < ag].sum())
        for line in (0.5, 1.5, 2.5):
            over = float(m[hg + ag > line].sum())
            out[f"{label} Over {line}"], out[f"{label} Under {line}"] = over, 1 - over
        out[f"{label} GG"] = float(m[(hg > 0) & (ag > 0)].sum())

    h1, a1, h2, a2 = np.meshgrid(g, g, g, g, indexing="ij")
    weight = first[h1, a1] * second[h2, a2]
    ht, ft = _sign(h1, a1), _sign(h1 + h2, a1 + a2)
    for s1 in "1X2":
        for s2 in "1X2":
            out[f"Parziale/Finale {s1}/{s2}"] = float(weight[(ht == s1) & (ft == s2)].sum())
    goals1, goals2 = h1 + a1, h2 + a2
    out["Tempo con più gol: 1T"] = float(weight[goals1 > goals2].sum())
    out["Tempo con più gol: 2T"] = float(weight[goals1 < goals2].sum())
    out["Tempo con più gol: pari"] = float(weight[goals1 == goals2].sum())
    out["Casa segna in entrambi i tempi"] = float(weight[(h1 > 0) & (h2 > 0)].sum())
    out["Ospite segna in entrambi i tempi"] = float(weight[(a1 > 0) & (a2 > 0)].sum())
    out["Casa vince almeno un tempo"] = float(weight[(h1 > a1) | (h2 > a2)].sum())
    out["Ospite vince almeno un tempo"] = float(weight[(a1 > h1) | (a2 > h2)].sum())
    out["Casa vince entrambi i tempi"] = float(weight[(h1 > a1) & (h2 > a2)].sum())
    out["Ospite vince entrambi i tempi"] = float(weight[(a1 > h1) & (a2 > h2)].sum())
    return out


def extra_goal_markets(matrix: np.ndarray) -> dict[str, float]:
    hg, ag = np.indices(matrix.shape)
    total, diff = hg + ag, hg - ag
    out = {"Pari": float(matrix[total % 2 == 0].sum()), "Dispari": float(matrix[total % 2 == 1].sum()),
           "Casa vince a zero": float(matrix[(diff > 0) & (ag == 0)].sum()),
           "Ospite vince a zero": float(matrix[(diff < 0) & (hg == 0)].sum())}
    for h in (1, 2):
        out[f"Handicap 1 (-{h})"] = float(matrix[diff > h].sum())
        out[f"Handicap 2 (-{h})"] = float(matrix[-diff > h].sum())
    for side, goals in (("Casa", hg), ("Ospite", ag)):
        for lo, hi in ((1, 2), (1, 3), (2, 3)):
            out[f"Multigol {side} {lo}-{hi}"] = float(matrix[(goals >= lo) & (goals <= hi)].sum())
    return out


def scorer_markets(leaders: dict[str, list[str]], home: str, away: str, rates: tuple[float, float],
                   goals_per_game: dict[str, float | None]) -> dict[str, float]:
    """Anytime-scorer chance for each team's top scorers, assuming they start.

    Share of team goals per appearance times the team's expected goals: a rough estimate that
    ignores penalties, minutes and lineup news.
    """
    out = {}
    for i, espn_team in enumerate(list(leaders)[:2]):
        team = canonical_team(espn_team, {home, away})
        side = 0 if team == home else 1 if team == away else i
        team_rate, gpg = rates[side], goals_per_game.get(home if side == 0 else away)
        if not gpg:
            continue
        for row in leaders[espn_team]:
            parsed = _LEADER_RE.search(row) if row.startswith("Goals:") else None
            if not parsed:
                continue
            apps, goals = int(parsed.group(1)), int(parsed.group(2))
            if apps == 0 or goals < 2:
                continue
            share = min(MAX_SCORER_SHARE, goals / (apps + PRIOR_APPEARANCES) / gpg)
            name = row.split(":", 1)[1].split("(")[0].strip()
            out[f"Marcatore: {name}"] = 1 - math.exp(-share * team_rate)
    return out


def special_selections(match: dict, rho: float, counts: dict[str, CountModel], shares: tuple[float, float],
                       fair_1x2: dict | None, fair_total: tuple[float, float] | None,
                       matrix: np.ndarray) -> dict[str, float]:
    home, away = match["partita"].split(" - ", 1)
    lam, mu = calibrated_rates(match["modello"]["xg_home"], match["modello"]["xg_away"], rho, fair_1x2, fair_total)
    out: dict[str, float] = {}
    for model in counts.values():
        try:
            out.update(model.markets(home, away, "I1"))
        except KeyError:
            continue
    out.update(half_markets(lam, mu, *shares))
    out.update(extra_goal_markets(matrix))
    gpg = {s["squadra"]: (s.get("totale") or {}).get("gol_fatti") for s in match.get("statistiche", [])}
    out.update(scorer_markets((match.get("contesto") or {}).get("leaders", {}), home, away, (lam, mu), gpg))
    return out


def _sign(h: np.ndarray, a: np.ndarray) -> np.ndarray:
    return np.where(h > a, "1", np.where(h == a, "X", "2"))


CATEGORIES = (
    ("Calci d'angolo", ("Corner",)),
    ("Cartellini", ("Cartellini",)),
    ("Tiri in porta", ("Tiri in porta",)),
    ("Primo e secondo tempo", ("1T ", "2T ", "Tempo con più gol")),
    ("Parziale/Finale", ("Parziale/Finale",)),
    ("Tempi e squadre", ("Casa segna", "Ospite segna", "Casa vince", "Ospite vince")),
    ("Handicap e multigol squadra", ("Handicap", "Multigol Casa", "Multigol Ospite")),
    ("Pari/Dispari", ("Pari", "Dispari")),
    ("Marcatori", ("Marcatore",)),
)


def top_by_category(selections: dict[str, float], per_category: int = 3) -> dict[str, list[tuple[str, float]]]:
    """Most likely selections per category, preferring those a bookmaker prices above about 1.08."""
    out = {}
    for label, prefixes in CATEGORIES:
        items = [(k, p) for k, p in selections.items() if k.startswith(prefixes)]
        if not items:
            continue
        playable = [x for x in items if x[1] <= 0.92] or items
        keep = playable if label in ("Marcatori",) else sorted(playable, key=lambda x: -x[1])[:per_category]
        out[label] = sorted(keep, key=lambda x: -x[1])
    return out


def render_specials(rows: list[dict], competition: str) -> str:
    from schedine import margin_for

    lines = [f"# Mercati speciali — {competition}", "",
             "Probabilità stimate dal modello (corner, cartellini e tiri dalle medie di squadra; tempi e marcatori "
             "dai gol attesi calibrati sul mercato). Quota equa = 1/probabilità; giocare solo se il book paga di più.", ""]
    for r in rows:
        lines += [f"## {r['partita']}", "", " · ".join(f"{k} attesi {v[0]:.1f}–{v[1]:.1f}" for k, v in r["attesi"].items()), "",
                  "| Categoria | Giocata | Prob. | Quota equa | Quota stimata |", "|---|---|---|---|---|"]
        for label, items in r["top"].items():
            for sel, p in items:
                est = 1 / (p * (1 + margin_for(sel)))
                lines.append(f"| {label} | {sel} | {p:.0%} | {1 / p:.2f} | {est:.2f} |")
        lines.append("")
    return "\n".join(lines)
