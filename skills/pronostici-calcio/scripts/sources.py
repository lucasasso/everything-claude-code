"""Collects bookmaker odds for a fixture from every available source and merges them."""

from __future__ import annotations

import csv
import os
import urllib.error
from pathlib import Path

from common import canonical_team, http_json
from fetch_data import load_fd_fixtures

ODDS_API_URL = ("https://api.the-odds-api.com/v4/sports/{sport}/odds"
                "?regions=eu,uk&markets=h2h,totals&oddsFormat=decimal&apiKey={key}")
ODDS_API_SPORTS = {"serie-a": "soccer_italy_serie_a", "champions": "soccer_uefa_champs_league"}


def _merge(target: dict, home: str, away: str, books: dict) -> None:
    """target[(home, away)][market][book] = {selection: odds}"""
    slot = target.setdefault((home, away), {})
    for book, markets in books.items():
        for market, odds in markets.items():
            slot.setdefault(market, {})[book] = odds


def fd_fixture_odds(fd_league: str | None, known: set[str]) -> dict:
    out: dict = {}
    if not fd_league:
        return out
    for fx in load_fd_fixtures(fd_league):
        _merge(out, canonical_team(fx["home"], known), canonical_team(fx["away"], known), fx["odds"])
    return out


def odds_api_odds(comp: str, known: set[str]) -> dict:
    """The Odds API (needs ODDS_API_KEY; the free tier allows ~500 requests a month)."""
    key = os.environ.get("ODDS_API_KEY")
    if not key or comp not in ODDS_API_SPORTS:
        return {}
    try:
        events = http_json(ODDS_API_URL.format(sport=ODDS_API_SPORTS[comp], key=key), cache_hours=1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"The Odds API ha risposto {exc.code}: controlla ODDS_API_KEY e il credito residuo") from exc

    out: dict = {}
    for ev in events:
        home, away = canonical_team(ev["home_team"], known), canonical_team(ev["away_team"], known)
        books: dict = {}
        for bm in ev.get("bookmakers", []):
            entry: dict = {}
            for mk in bm.get("markets", []):
                if mk["key"] == "h2h":
                    sel = {o["name"]: o["price"] for o in mk["outcomes"]}
                    if {ev["home_team"], ev["away_team"], "Draw"} <= set(sel):
                        entry["1X2"] = {"1": sel[ev["home_team"]], "X": sel["Draw"], "2": sel[ev["away_team"]]}
                elif mk["key"] == "totals":
                    for o in mk["outcomes"]:
                        line = o.get("point")
                        entry.setdefault(f"OU{line}", {})[f"{o['name']} {line}"] = o["price"]
            if entry:
                books[bm["title"]] = entry
        _merge(out, home, away, books)
    return out


def manual_odds(path: Path, known: set[str]) -> dict:
    """User-supplied odds (e.g. Snai, Sisal, Eurobet). CSV columns: partita,mercato,selezione,quota,bookmaker.

    partita is "Casa - Ospite"; mercato is one of 1X2, DC, GG/NG, OU1.5, OU2.5, OU3.5;
    selezione uses the labels 1/X/2, 1X/X2/12, GG/NG, "Over 2.5"/"Under 2.5".
    """
    out: dict = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            home, _, away = row["partita"].partition(" - ")
            if not away:
                raise ValueError(f"Formato partita non valido (usa 'Casa - Ospite'): {row['partita']!r}")
            price = float(row["quota"].replace(",", "."))
            if price <= 1:
                raise ValueError(f"Quota non valida {price} per {row['partita']}")
            key = (canonical_team(home, known), canonical_team(away, known))
            out.setdefault(key, {}).setdefault(row["mercato"].strip(), {}).setdefault(
                row["bookmaker"].strip(), {})[row["selezione"].strip()] = price
    return out


def collect_odds(comp: str, fd_league: str | None, fixtures: list[dict], known: set[str],
                 manual: Path | None = None) -> tuple[dict, list[str]]:
    """Return {(home, away): {market: {book: {selection: odds}}}} and a list of sources used."""
    merged: dict = {}
    used = []
    for fx in fixtures:
        if fx["odds"]:
            _merge(merged, fx["home"], fx["away"], fx["odds"])
    if any(fx["odds"] for fx in fixtures):
        used.append("ESPN/DraftKings")
    for name, loader in (("football-data.co.uk", lambda: fd_fixture_odds(fd_league, known)),
                         ("The Odds API", lambda: odds_api_odds(comp, known))):
        extra = loader()
        if extra:
            used.append(name)
        for key, markets in extra.items():
            for market, books in markets.items():
                merged.setdefault(key, {}).setdefault(market, {}).update(books)
    if manual:
        for key, markets in manual_odds(manual, known).items():
            for market, books in markets.items():
                merged.setdefault(key, {}).setdefault(market, {}).update(books)
        used.append(f"manuale ({manual.name})")
    return merged, used
