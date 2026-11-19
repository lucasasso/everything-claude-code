"""Builds the betting slip (schedina) from a round analysis."""

from __future__ import annotations

import math

from odds_tools import kelly_stake

SKIP_MARKETS = ("Risultato esatto",)
MIN_ODDS, MAX_ODDS = 1.30, 6.0


def _candidates(analysis: dict, min_edge: float, min_prob: float) -> list[dict]:
    picks = []
    for match in analysis["partite"]:
        for market in match["mercati"]:
            if market["mercato"] in SKIP_MARKETS:
                continue
            for row in market["righe"]:
                price, ev = row["miglior_quota"], row["ev"]
                if price is None or ev is None or row["p_mercato"] is None:
                    continue
                if ev >= min_edge and row["p_finale"] >= min_prob and MIN_ODDS <= price <= MAX_ODDS:
                    picks.append({"partita": match["partita"], "mercato": market["mercato"], **row})
    return picks


def build_slip(analysis: dict, *, bankroll: float = 100.0, min_edge: float = 0.03, min_prob: float = 0.30,
               max_legs: int = 4, kelly_fraction: float = 0.25) -> dict:
    """Value singles (one per match), a multiple from the safest value picks, and the most likely outcomes."""
    best_per_match: dict[str, dict] = {}
    for pick in _candidates(analysis, min_edge, min_prob):
        current = best_per_match.get(pick["partita"])
        if current is None or pick["ev"] > current["ev"]:
            best_per_match[pick["partita"]] = pick

    singles = []
    for pick in sorted(best_per_match.values(), key=lambda p: p["ev"], reverse=True):
        stake = kelly_stake(pick["p_finale"], pick["miglior_quota"], fraction=kelly_fraction)
        singles.append({**pick, "puntata": round(stake * bankroll, 2), "puntata_pct": round(stake * 100, 2)})

    legs = sorted((p for p in best_per_match.values() if p["p_finale"] >= 0.5),
                  key=lambda p: p["p_finale"], reverse=True)[:max_legs]
    multiple = None
    if len(legs) >= 2:
        odds = math.prod(p["miglior_quota"] for p in legs)
        prob = math.prod(p["p_finale"] for p in legs)
        multiple = {"selezioni": legs, "quota_totale": round(odds, 2), "probabilita": prob, "ev": prob * odds - 1,
                    "puntata": round(kelly_stake(prob, odds, fraction=kelly_fraction, cap=0.01) * bankroll, 2)}

    likely = []
    for match in analysis["partite"]:
        for market in match["mercati"]:
            if market["mercato"] == "1X2":
                top = max(market["righe"], key=lambda r: r["p_finale"])
                likely.append({"partita": match["partita"], "segno": top["selezione"], "p_finale": top["p_finale"],
                               "quota": top["miglior_quota"]})
    return {"singole_valore": singles, "multipla": multiple, "esiti_piu_probabili": likely,
            "parametri": {"bankroll": bankroll, "min_edge": min_edge, "min_prob": min_prob, "kelly": kelly_fraction}}
