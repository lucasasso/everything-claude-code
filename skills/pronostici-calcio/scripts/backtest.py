"""Walk-forward backtest: refit weekly, predict the next week, compare with closing odds."""

from __future__ import annotations

import math
from datetime import date, timedelta

from fetch_data import load_fd_results
from model import fit
from odds_tools import devig

WARMUP_WEEKS = 5
SELECTIONS = ("1", "X", "2")


def _outcome(m: dict) -> str:
    return "1" if m["hg"] > m["ag"] else "2" if m["hg"] < m["ag"] else "X"


def run_backtest(league: str, season: str, model_weight: float, min_edge: float) -> dict:
    """Weekly walk-forward on one season.

    Reports 1X2 log-loss for the model, the opening and closing market and the blend, and the
    line-shopping strategy the skill recommends: back the best opening price when it beats the
    de-vigged opening consensus by `min_edge`. Closing-line value (CLV) is the less noisy measure of edge.
    """
    end_of_season = date(2000 + int(season[2:]), 6, 30)
    matches = load_fd_results(end_of_season, seasons_back=1)
    target = sorted((m for m in matches if m["comp"] == league and m["date"] >= date(end_of_season.year - 1, 7, 1)),
                    key=lambda m: m["date"])
    if not target:
        raise ValueError(f"Nessuna partita per {league} stagione {season}")

    week = target[0]["date"] + timedelta(weeks=WARMUP_WEEKS)
    ll = {"modello": 0.0, "mercato_apertura": 0.0, "mercato_chiusura": 0.0, "combinato_apertura": 0.0}
    n, bets, profit, clv = 0, 0, 0.0, 0.0
    while week <= target[-1]["date"]:
        upcoming = [m for m in target if week <= m["date"] < week + timedelta(days=7)]
        if upcoming:
            model = fit(matches, as_of=week)
            for m in upcoming:
                opening = m["opening"].get("Media mercato", {}).get("1X2")
                closing = m["closing"].get("Media mercato", {}).get("1X2")
                best = m["opening"].get("Migliore quota", {}).get("1X2")
                if not (opening and closing) or m["home"] not in model.index or m["away"] not in model.index:
                    continue
                p_model = model.predict(m["home"], m["away"], league)["markets"]["1X2"]
                p_open, p_close = devig(opening), devig(closing)
                p_blend = {s: model_weight * p_model[s] + (1 - model_weight) * p_open[s] for s in SELECTIONS}
                result = _outcome(m)
                for name, probs in (("modello", p_model), ("mercato_apertura", p_open),
                                    ("mercato_chiusura", p_close), ("combinato_apertura", p_blend)):
                    ll[name] -= math.log(max(probs[result], 1e-9))
                n += 1
                for s in SELECTIONS if best else ():
                    if best[s] * p_blend[s] - 1 >= min_edge:
                        bets += 1
                        profit += (best[s] - 1) if s == result else -1
                        clv += best[s] * p_close[s] - 1
        week += timedelta(days=7)

    return {
        "lega": league, "stagione": season, "partite_valutate": n,
        "log_loss_medio": {k: round(v / n, 4) for k, v in ll.items()} if n else {},
        "line_shopping": {"scommesse": bets, "profitto_unita": round(profit, 2),
                          "roi": round(profit / bets, 4) if bets else None,
                          "clv_medio": round(clv / bets, 4) if bets else None},
        "nota": "Log-loss più basso = previsioni migliori. CLV positivo = hai preso quote migliori della chiusura, "
                "il segnale più affidabile di un vantaggio reale; il ROI di una sola stagione ha varianza altissima. "
                "'Migliore quota' è il massimo tra molti bookmaker: con un solo conto i risultati sono peggiori.",
    }
