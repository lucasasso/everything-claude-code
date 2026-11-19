"""Three slips per round (facile, media, difficile) chosen across every market, not just 1X2."""

from __future__ import annotations

import math

from combo import all_selections, calibrated_matrix
from odds_tools import DEFAULT_MODEL_WEIGHT

# Typical Italian-book margin: low on 1X2 and totals, higher on combos and multigol.
MARGIN_SIMPLE, MARGIN_COMBO = 0.05, 0.09
DIVERGENCE_PENALTY = 0.5
TIERS = {
    "facile": {"p_min": 0.70, "p_max": 0.90, "min_leg_odds": 1.15, "target_odds": 2.2, "min_legs": 3, "max_legs": 5},
    "media": {"p_min": 0.55, "p_max": 0.76, "min_leg_odds": 1.28, "target_odds": 5.0, "min_legs": 4, "max_legs": 5},
    "difficile": {"p_min": 0.33, "p_max": 0.60, "min_leg_odds": 1.60, "target_odds": 20.0, "min_legs": 4, "max_legs": 6},
}


def _consensus(match: dict, market: str) -> dict:
    return next((mk.get("consenso") or {} for mk in match["mercati"] if mk["mercato"] == market), {})


def _fair_total(match: dict) -> tuple[float, float] | None:
    lines = [mk["mercato"] for mk in match["mercati"] if mk["mercato"].startswith("OU") and mk.get("consenso")]
    if not lines:
        return None
    best = "OU2.5" if "OU2.5" in lines else lines[0]
    line = float(best[2:])
    return line, _consensus(match, best)[f"Over {line}"]


def _divergence(match: dict) -> float:
    rows = next((mk["righe"] for mk in match["mercati"] if mk["mercato"] == "1X2"), [])
    return max((abs(r["p_modello"] - r["p_mercato"]) for r in rows if r["p_mercato"] is not None), default=0.10)


def _book_price(match: dict, selection: str) -> float | None:
    if not selection.startswith("Segno ") or len(selection) != 7:
        return None
    rows = next((mk["righe"] for mk in match["mercati"] if mk["mercato"] == "1X2"), [])
    return next((r["miglior_quota"] for r in rows if r["selezione"] == selection[-1]), None)


def match_selections(match: dict, rho: float, model_weight: float = DEFAULT_MODEL_WEIGHT) -> dict[str, float]:
    matrix = calibrated_matrix(match["modello"]["xg_home"], match["modello"]["xg_away"], rho,
                               _consensus(match, "1X2") or None, _fair_total(match), model_weight)
    return all_selections(matrix)


def build_three_slips(analysis: dict, model_weight: float = DEFAULT_MODEL_WEIGHT) -> dict:
    rho = analysis["modello"]["rho"]
    per_match = []
    for m in analysis["partite"]:
        sels = match_selections(m, rho, model_weight)
        per_match.append({"partita": m["partita"], "data": m["data"], "match": m, "selezioni": sels,
                          "divergenza": _divergence(m)})

    slips = {name: _build_tier(per_match, cfg) for name, cfg in TIERS.items()}
    previsioni = [_match_summary(pm) for pm in per_match]
    return {"previsioni": previsioni, "schedine": slips}


def _build_tier(per_match: list[dict], cfg: dict) -> dict:
    picks = []
    for pm in per_match:
        options = []
        for sel, p in pm["selezioni"].items():
            margin = MARGIN_COMBO if ("+" in sel or "Multigol" in sel) else MARGIN_SIMPLE
            book = _book_price(pm["match"], sel) or 1 / (p * (1 + margin))
            if cfg["p_min"] <= p <= cfg["p_max"] and book >= cfg["min_leg_odds"]:
                options.append((p, sel, book))
        if not options:
            continue
        p, sel, book = max(options)
        picks.append({"partita": pm["partita"], "selezione": sel, "prob": p, "quota_equa": round(1 / p, 2),
                      "quota_stimata": round(book, 2), "affidabilita": p - DIVERGENCE_PENALTY * pm["divergenza"]})

    picks.sort(key=lambda x: x["affidabilita"], reverse=True)
    legs: list[dict] = []
    for pick in picks:
        legs.append(pick)
        odds = math.prod(x["quota_stimata"] for x in legs)
        if len(legs) >= cfg["max_legs"] or (len(legs) >= cfg["min_legs"] and odds >= cfg["target_odds"]):
            break

    prob = math.prod(x["prob"] for x in legs) if legs else 0.0
    odds = math.prod(x["quota_stimata"] for x in legs) if legs else 0.0
    return {"selezioni": legs, "probabilita": prob, "quota_stimata": round(odds, 2),
            "ev_stimato": prob * odds - 1 if legs else None, "consiglio": _verdict(prob)}


def _verdict(prob: float) -> str:
    if prob >= 0.30:
        return "GIOCA (puntata piccola)"
    if prob >= 0.12:
        return "FACOLTATIVA (puntata minima)"
    return "NON GIOCARE (solo per divertimento, cifra simbolica)"


def _match_summary(pm: dict) -> dict:
    s = pm["selezioni"]

    def best(prefixes: tuple[str, ...], exclude_plus: bool = True) -> tuple[str, float]:
        cands = [(p, k) for k, p in s.items() if k.startswith(prefixes) and (not exclude_plus or "+" not in k)]
        p, k = max(cands)
        return k, p

    sign = max(((s[f"Segno {x}"], f"Segno {x}") for x in "1X2"))
    dc = max(((s[f"Segno {x}"], f"Segno {x}") for x in ("1X", "X2", "12")))
    ou = max(((s[k], k) for k in ("Over 2.5", "Under 2.5")))
    gg = max(((s[k], k) for k in ("GG", "NG")))
    mg = best(("Multigol",))
    combos = [(p, k) for k, p in s.items() if "+" in k and 0.45 <= p <= 0.75]
    combo = max(combos) if combos else max((p, k) for k, p in s.items() if "+" in k)
    return {"partita": pm["partita"], "segno": (sign[1], sign[0]), "doppia_chance": (dc[1], dc[0]),
            "under_over": (ou[1], ou[0]), "gol_nogol": (gg[1], gg[0]), "multigol": mg, "combo": (combo[1], combo[0]),
            "divergenza": pm["divergenza"]}


def render(result: dict, competition: str) -> str:
    lines = [f"# Tre schedine — {competition}", "",
             "Probabilità dal modello calibrato sulle quote di mercato (90% mercato, 10% modello). "
             "La quota stimata applica un margine tipico dei book italiani: confrontala con la tua app.", ""]
    labels = {"facile": "Facile", "media": "Media", "difficile": "Difficile"}
    for name, slip in result["schedine"].items():
        lines += [f"## Schedina {labels[name]} — {slip['consiglio']}", "",
                  "| Partita | Giocata | Prob. | Quota equa | Quota stimata |", "|---|---|---|---|---|"]
        lines += [f"| {x['partita']} | {x['selezione']} | {x['prob']:.0%} | {x['quota_equa']:.2f} | {x['quota_stimata']:.2f} |"
                  for x in slip["selezioni"]]
        ev = "–" if slip["ev_stimato"] is None else f"{slip['ev_stimato']:+.0%}"
        lines += ["", f"Probabilità che passi: **{slip['probabilita']:.0%}** · quota totale stimata **{slip['quota_stimata']:.2f}** "
                  f"· valore atteso stimato {ev}", ""]
    lines += ["## Previsione partita per partita", "",
              "| Partita | Segno | Doppia chance | U/O 2.5 | GG/NG | Multigol | Combo |", "|---|---|---|---|---|---|---|"]
    for p in result["previsioni"]:
        cells = [f"{p[k][0].replace('Segno ', '')} {p[k][1]:.0%}" for k in
                 ("segno", "doppia_chance", "under_over", "gol_nogol", "multigol", "combo")]
        lines.append(f"| {p['partita']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
