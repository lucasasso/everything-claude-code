#!/usr/bin/env python3
"""Pronostici Serie A / Champions League: model, odds comparison, pricing errors, slip.

Esempi:
  python3 pronostici.py giornata --comp serie-a --dal 2026-11-21 --al 2026-11-23
  python3 pronostici.py giornata --comp champions --dal 2026-11-24 --al 2026-11-25 --news news.json --quote snai.csv
  python3 pronostici.py schedina --analisi pronostici/serie-a-2026-11-21/analisi.json --bankroll 50
  python3 pronostici.py tre-schedine --analisi pronostici/serie-a-2026-11-21/analisi.json
  python3 pronostici.py speciali --analisi pronostici/serie-a-2026-11-21/analisi.json
  python3 pronostici.py registro importa --file giocate.json
  python3 pronostici.py registro aggiorna
  python3 pronostici.py statistiche --squadra Inter
  python3 pronostici.py classifica-forza --top 30
  python3 pronostici.py backtest --lega I1 --stagione 2526
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from common import COMPETITIONS, FD_LEAGUES, canonical_team, write_json
from fetch_data import espn_fixtures, espn_match_context, load_european_results, load_fd_results
from model import fit
from odds_tools import DEFAULT_MODEL_WEIGHT, analyse_market
from report import render
from combo import all_selections, calibrated_matrix
from schedine import _consensus as consensus_1x2_market
from schedine import _fair_total as fair_total_line
from schedine import build_three_slips
from speciali import fit_count_models, first_half_shares, render_specials, special_selections, top_by_category
from schedine import render as render_three
from slip import build_slip
from sources import collect_odds
from stats import team_stats

log = logging.getLogger("pronostici")


def load_training(as_of: date) -> list[dict]:
    domestic = load_fd_results(as_of, seasons_back=1)
    known = {m["home"] for m in domestic} | {m["away"] for m in domestic}
    european = load_european_results(as_of, known, years_back=1)
    log.info("Partite di campionato: %d, partite europee: %d", len(domestic), len(european))
    return domestic + european


def season_start(day: date) -> date:
    return date(day.year if day.month >= 7 else day.year - 1, 7, 1)


def _load_news(path: Path | None, known: set[str]) -> dict:
    if not path:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {canonical_team(team, known): values for team, values in raw.items()}


def _analyse_markets(model_markets: dict, market_odds: dict, model_weight: float) -> list[dict]:
    one_x_two = analyse_market("1X2", model_markets["1X2"], market_odds.get("1X2", {}), model_weight)
    fair = one_x_two["consenso"]
    dc_fair = ({"1X": fair["1"] + fair["X"], "X2": fair["X"] + fair["2"], "12": fair["1"] + fair["2"]}
               if {"1", "X", "2"} <= set(fair) else None)
    out = [one_x_two]
    for name, probs in model_markets.items():
        if name != "1X2":
            override = dc_fair if name == "DC" else None
            out.append(analyse_market(name, probs, market_odds.get(name, {}), model_weight, override))
    return out


def cmd_giornata(args: argparse.Namespace) -> None:
    comp = COMPETITIONS[args.comp]
    start = date.fromisoformat(args.dal) if args.dal else date.today()
    end = date.fromisoformat(args.al) if args.al else start + timedelta(days=3)

    matches = load_training(start)
    model = fit(matches, as_of=start, domestic_comps=FD_LEAGUES)
    known = set(model.teams)
    fixtures = espn_fixtures(comp["espn"], start, end, known)
    if not fixtures:
        sys.exit(f"Nessuna partita {comp['label']} trovata tra {start} e {end}.")
    odds, sources = collect_odds(args.comp, comp["fd"], fixtures, known, Path(args.quote) if args.quote else None)
    news = _load_news(Path(args.news) if args.news else None, known)
    since = season_start(start)
    domestic = [m for m in matches if m["comp"] in FD_LEAGUES]
    model_comp = comp["fd"] or comp["espn"]

    analysed = []
    for fx in fixtures:
        home, away = fx["home"], fx["away"]
        try:
            pred = model.predict(home, away, model_comp, news)
        except KeyError as exc:
            log.warning("%s — partita saltata", exc)
            continue
        try:
            context = espn_match_context(fx["league"], fx["id"])
        except Exception as exc:  # context is optional; the prediction stands without it
            log.warning("Contesto ESPN non disponibile per %s-%s: %s", home, away, exc)
            context = {}
        market_odds = odds.get((home, away), {})
        for book, book_markets in context.pop("odds", {}).items():
            for name, prices in book_markets.items():
                market_odds.setdefault(name, {}).setdefault(book, prices)
        if market_odds and "ESPN/DraftKings" not in sources:
            sources.append("ESPN/DraftKings")
        markets = _analyse_markets(pred["markets"], market_odds, args.peso_modello)
        analysed.append({
            "partita": f"{home} - {away}", "data": fx["kickoff"], "id_espn": fx["id"], "modello": pred,
            "mercati": markets, "contesto": context,
            "statistiche": [team_stats(domestic, t, since) for t in (home, away)],
            "aggiustamenti_news": {t: news[t] for t in (home, away) if t in news},
        })

    analysis = {"competizione": comp["label"], "dal": str(start), "al": str(end), "peso_modello": args.peso_modello,
                "fonti_quote": sources, "modello": {"aggiornato": str(model.fitted_on), "rho": model.rho},
                "partite": analysed}
    out_dir = Path(args.out or f"pronostici/{args.comp}-{start}")
    write_json(out_dir / "analisi.json", analysis)
    slip = build_slip(analysis, bankroll=args.bankroll, min_edge=args.min_edge)
    write_json(out_dir / "schedina.json", slip)
    (out_dir / "report.md").write_text(render(analysis, slip), encoding="utf-8")
    print(f"Analisi: {out_dir / 'analisi.json'}\nSchedina: {out_dir / 'schedina.json'}\nReport: {out_dir / 'report.md'}")


def cmd_schedina(args: argparse.Namespace) -> None:
    path = Path(args.analisi)
    analysis = json.loads(path.read_text(encoding="utf-8"))
    slip = build_slip(analysis, bankroll=args.bankroll, min_edge=args.min_edge, min_prob=args.min_prob, max_legs=args.max_legs)
    write_json(path.parent / "schedina.json", slip)
    (path.parent / "report.md").write_text(render(analysis, slip), encoding="utf-8")
    print((path.parent / "report.md").read_text(encoding="utf-8"))


def cmd_tre_schedine(args: argparse.Namespace) -> None:
    path = Path(args.analisi)
    analysis = json.loads(path.read_text(encoding="utf-8"))
    result = build_three_slips(analysis, args.peso_modello)
    write_json(path.parent / "tre_schedine.json", result)
    text = render_three(result, analysis["competizione"])
    (path.parent / "tre_schedine.md").write_text(text, encoding="utf-8")
    print(text)


def cmd_speciali(args: argparse.Namespace) -> None:
    path = Path(args.analisi)
    analysis = json.loads(path.read_text(encoding="utf-8"))
    start = date.fromisoformat(analysis["dal"])
    comp_key = next(k for k, c in COMPETITIONS.items() if c["label"] == analysis["competizione"])
    leagues = (COMPETITIONS[comp_key]["fd"],) if COMPETITIONS[comp_key]["fd"] else FD_LEAGUES
    model_comp = COMPETITIONS[comp_key]["fd"] or COMPETITIONS[comp_key]["espn"]
    league_matches = load_fd_results(start, seasons_back=1, leagues=leagues)
    counts = fit_count_models(league_matches, start, leagues)
    shares = first_half_shares(league_matches, leagues)
    rho = analysis["modello"]["rho"]

    rows = []
    for m in analysis["partite"]:
        home, away = m["partita"].split(" - ", 1)
        fair_1x2, fair_total = consensus_1x2_market(m, "1X2") or None, fair_total_line(m)
        matrix = calibrated_matrix(m["modello"]["xg_home"], m["modello"]["xg_away"], rho, fair_1x2, fair_total,
                                   args.peso_modello)
        selections = {**all_selections(matrix),
                      **special_selections(m, rho, counts, shares, fair_1x2, fair_total, matrix, model_comp)}
        expected = {}
        for name, cm in counts.items():
            try:
                expected[name] = cm.expected(home, away, model_comp)
            except KeyError:
                continue
        rows.append({"partita": m["partita"], "data": m["data"], "attesi": expected, "selezioni": selections,
                     "top": top_by_category(selections)})

    write_json(path.parent / "speciali.json", rows)
    text = render_specials(rows, analysis["competizione"])
    (path.parent / "speciali.md").write_text(text, encoding="utf-8")
    print(text)


def cmd_registro(args: argparse.Namespace) -> None:
    import registro

    if args.azione == "importa":
        entries = json.loads(Path(args.file).read_text(encoding="utf-8"))
        print(f"Registrate {registro.add(entries)} giocate in {registro.ledger_path()}")
    elif args.azione == "aggiorna":
        print(f"Chiuse {registro.update()} giocate con i risultati finali")
    elif args.azione == "esito":
        registro.set_outcome(args.id, args.esito)
        print(f"Giocata {args.id}: {args.esito}")
    print(json.dumps(registro.summary(), indent=2, ensure_ascii=False))


def cmd_statistiche(args: argparse.Namespace) -> None:
    today = date.today()
    matches = load_fd_results(today, seasons_back=0)
    known = {m["home"] for m in matches} | {m["away"] for m in matches}
    team = canonical_team(args.squadra, known)
    print(json.dumps(team_stats(matches, team, season_start(today)), indent=2, ensure_ascii=False))


def cmd_forza(args: argparse.Namespace) -> None:
    model = fit(load_training(date.today()), as_of=date.today(), domestic_comps=FD_LEAGUES)
    for i, r in enumerate(model.ratings()[:args.top], 1):
        print(f"{i:3d}. {r['team']:<22} forza {r['forza']:+.2f}  attacco {r['attacco']:+.2f}  difesa {r['difesa']:+.2f}")


def cmd_backtest(args: argparse.Namespace) -> None:
    from backtest import run_backtest

    print(json.dumps(run_backtest(args.lega, args.stagione, args.peso_modello, args.min_edge), indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("giornata", help="analizza le partite di una giornata")
    g.add_argument("--comp", choices=sorted(COMPETITIONS), required=True)
    g.add_argument("--dal", help="data inizio YYYY-MM-DD (default oggi)")
    g.add_argument("--al", help="data fine YYYY-MM-DD (default +3 giorni)")
    g.add_argument("--quote", help="CSV con quote del tuo bookmaker (partita,mercato,selezione,quota,bookmaker)")
    g.add_argument("--news", help="JSON con aggiustamenti da news (vedi references/news-e-aggiustamenti.md)")
    g.add_argument("--peso-modello", type=float, default=DEFAULT_MODEL_WEIGHT)
    g.add_argument("--min-edge", type=float, default=0.03)
    g.add_argument("--bankroll", type=float, default=100.0)
    g.add_argument("--out")
    g.set_defaults(func=cmd_giornata)

    s = sub.add_parser("schedina", help="ricostruisce la schedina da un'analisi")
    s.add_argument("--analisi", required=True)
    s.add_argument("--bankroll", type=float, default=100.0)
    s.add_argument("--min-edge", type=float, default=0.03)
    s.add_argument("--min-prob", type=float, default=0.30)
    s.add_argument("--max-legs", type=int, default=4)
    s.set_defaults(func=cmd_schedina)

    t = sub.add_parser("tre-schedine", help="schedina facile, media e difficile su tutti i mercati e le combo")
    t.add_argument("--analisi", required=True)
    t.add_argument("--peso-modello", type=float, default=DEFAULT_MODEL_WEIGHT)
    t.set_defaults(func=cmd_tre_schedine)

    sp = sub.add_parser("speciali", help="corner, cartellini, tiri in porta, tempi, parziale/finale, marcatori")
    sp.add_argument("--analisi", required=True)
    sp.add_argument("--peso-modello", type=float, default=DEFAULT_MODEL_WEIGHT)
    sp.set_defaults(func=cmd_speciali)

    rg = sub.add_parser("registro", help="registro delle previsioni: importa, aggiorna, esito, riepilogo")
    rg.add_argument("azione", choices=["importa", "aggiorna", "esito", "riepilogo"])
    rg.add_argument("--file", help="JSON con le giocate da importare (per importa)")
    rg.add_argument("--id", type=int, help="id della giocata (per esito)")
    rg.add_argument("--esito", choices=["vinta", "persa"], help="esito manuale (per esito)")
    rg.set_defaults(func=cmd_registro)

    st = sub.add_parser("statistiche", help="statistiche stagionali di una squadra")
    st.add_argument("--squadra", required=True)
    st.set_defaults(func=cmd_statistiche)

    f = sub.add_parser("classifica-forza", help="ranking del modello su tutti i campionati")
    f.add_argument("--top", type=int, default=30)
    f.set_defaults(func=cmd_forza)

    b = sub.add_parser("backtest", help="valuta il modello su una stagione passata")
    b.add_argument("--lega", default="I1", choices=FD_LEAGUES)
    b.add_argument("--stagione", default="2526", help="codice football-data, es. 2526")
    b.add_argument("--peso-modello", type=float, default=DEFAULT_MODEL_WEIGHT)
    b.add_argument("--min-edge", type=float, default=0.03)
    b.set_defaults(func=cmd_backtest)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
