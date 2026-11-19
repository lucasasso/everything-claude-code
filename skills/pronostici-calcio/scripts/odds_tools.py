"""Bookmaker-margin removal, market consensus, value bets and pricing-error detection."""

from __future__ import annotations

import statistics

from scipy.optimize import brentq

SHARP_BOOKS = ("Pinnacle", "Betfair Exchange")
AGGREGATE_BOOKS = ("Migliore quota", "Media mercato")
DEFAULT_MODEL_WEIGHT = 0.10  # backtests 2024-26: the market beats the model; more weight raised log-loss
MIN_EDGE = 0.03
OUTLIER_EDGE = 0.02  # flags a price at least 2% above the de-vigged consensus
DIVERGENCE = 0.08
OVERLAPPING_MARKETS = ("DC", "Risultato esatto")


def implied(odds: dict[str, float]) -> dict[str, float]:
    return {k: 1 / v for k, v in odds.items() if v and v > 1}


def overround(odds: dict[str, float]) -> float:
    return sum(implied(odds).values()) - 1


def devig(odds: dict[str, float], method: str = "power") -> dict[str, float]:
    """Fair probabilities without the bookmaker margin.

    `multiplicative` scales proportionally; `power` and `shin` correct the favourite-longshot
    bias (margins load more heavily on outsiders), which suits soccer 1X2 markets better.
    """
    raw = implied(odds)
    total = sum(raw.values())
    if len(raw) < 2 or total <= 0:
        return {}
    if method == "multiplicative" or total <= 1:
        return {k: v / total for k, v in raw.items()}
    if method == "power":
        k = brentq(lambda e: sum(p ** e for p in raw.values()) - 1, 1.0, 10.0)
        return {sel: p ** k for sel, p in raw.items()}
    if method == "shin":
        n = len(raw)

        def probs(z: float) -> dict[str, float]:
            return {s: ((z * z + 4 * (1 - z) * p * p / total) ** 0.5 - z) / (2 * (1 - z)) for s, p in raw.items()}

        z = brentq(lambda z: sum(probs(z).values()) - 1, 0.0, 0.4) if n > 1 else 0.0
        return probs(z)
    raise ValueError(f"Metodo di de-vig sconosciuto: {method!r}")


def market_consensus(books: dict[str, dict[str, float]]) -> tuple[dict[str, float], str]:
    """Fair probabilities from the sharpest available source, else the median of all books."""
    for sharp in SHARP_BOOKS:
        if sharp in books and len(books[sharp]) >= 2:
            return devig(books[sharp]), sharp
    fair = [devig(o) for b, o in books.items() if b not in AGGREGATE_BOOKS and len(o) >= 2]
    fair = [f for f in fair if f]
    if not fair:
        avg = books.get("Media mercato")
        return (devig(avg), "Media mercato") if avg else ({}, "nessuna")
    selections = set.intersection(*(set(f) for f in fair))
    med = {s: statistics.median(f[s] for f in fair) for s in selections}
    total = sum(med.values())
    return {s: p / total for s, p in med.items()}, f"mediana di {len(fair)} book"


def best_prices(books: dict[str, dict[str, float]]) -> dict[str, tuple[float, str]]:
    best: dict[str, tuple[float, str]] = {}
    for book, odds in books.items():
        if book in AGGREGATE_BOOKS:
            continue
        for sel, price in odds.items():
            if price and (sel not in best or price > best[sel][0]):
                best[sel] = (price, book)
    return best


def analyse_market(market: str, model: dict[str, float], books: dict[str, dict[str, float]],
                   model_weight: float = DEFAULT_MODEL_WEIGHT, fair_override: dict[str, float] | None = None) -> dict:
    """Compare model, market and every bookmaker for one market of one match.

    Double chance outcomes overlap, so their prices cannot be de-vigged on their own: pass the
    consensus derived from 1X2 as `fair_override`.
    """
    overlapping = market in OVERLAPPING_MARKETS
    if fair_override is not None:
        fair, source = fair_override, "derivato da 1X2"
    elif books and not overlapping:
        fair, source = market_consensus(books)
    else:
        fair, source = {}, "nessuna"
    best = best_prices(books)
    rows, alerts = [], []

    for sel, p_model in model.items():
        p_market = fair.get(sel)
        p_final = p_model if p_market is None else model_weight * p_model + (1 - model_weight) * p_market
        price, book = best.get(sel, (None, None))
        ev = p_final * price - 1 if price else None
        rows.append({"selezione": sel, "p_modello": p_model, "p_mercato": p_market, "p_finale": p_final,
                     "quota_equa": 1 / p_final if p_final > 0 else None, "miglior_quota": price,
                     "book": book, "ev": ev})

        if p_market is not None and abs(p_model - p_market) >= DIVERGENCE:
            alerts.append({"tipo": "DIVERGENZA MODELLO", "selezione": sel,
                           "dettaglio": f"modello {p_model:.0%} vs mercato {p_market:.0%}: verifica news/formazioni"})
        if p_market:
            for b, odds in books.items():
                if b in AGGREGATE_BOOKS or sel not in odds:
                    continue
                edge = odds[sel] * p_market - 1
                if edge >= OUTLIER_EDGE:
                    alerts.append({"tipo": "QUOTA FUORI LINEA", "selezione": sel, "book": b, "quota": odds[sel],
                                   "dettaglio": f"{b} paga {odds[sel]:.2f}, quota equa di mercato {1 / p_market:.2f} (+{edge:.1%})"})

    full_cover = not overlapping and all(s in best for s in model) and len(model) >= 2
    if full_cover:
        book_sum = sum(1 / best[s][0] for s in model)
        if book_sum < 1:
            alerts.append({"tipo": "SUREBET", "selezione": " / ".join(model), "dettaglio":
                           f"somma 1/quota = {book_sum:.3f}: profitto garantito {1 / book_sum - 1:.1%} puntando su "
                           + ", ".join(f"{s} @{best[s][0]} ({best[s][1]})" for s in model)})
    margins = {b: overround(o) for b, o in books.items()
               if not overlapping and b not in AGGREGATE_BOOKS and len(o) == len(model)}
    return {"mercato": market, "fonte_mercato": source, "consenso": fair, "righe": rows, "allerte": alerts,
            "margini": {b: round(m, 4) for b, m in margins.items()}}


def kelly_stake(prob: float, odds: float, fraction: float = 0.25, cap: float = 0.02) -> float:
    """Fractional Kelly stake as a share of bankroll, capped."""
    b = odds - 1
    if b <= 0:
        return 0.0
    full = (prob * b - (1 - prob)) / b
    return max(0.0, min(cap, full * fraction))
