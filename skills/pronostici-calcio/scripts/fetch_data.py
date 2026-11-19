"""Data loaders: football-data.co.uk (results, xG, odds) and ESPN (fixtures, European results, form)."""

from __future__ import annotations

import csv
import io
import urllib.error
from datetime import date, datetime, timedelta

from common import (
    ESPN_BASE,
    EUROPEAN_ESPN,
    FD_LEAGUES,
    canonical_team,
    http_get,
    http_json,
    season_code,
)

FD_RESULTS_URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
FD_FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

# football-data.co.uk column prefixes -> bookmaker label (pre-match and closing "C" variants).
FD_BOOKS = {
    "B365": "Bet365", "BW": "Bwin", "BV": "BetVictor", "PP": "Paddy Power", "SKB": "Skybet",
    "BFD": "Betfred", "BFE": "Betfair Exchange", "PS": "Pinnacle", "WH": "William Hill",
    "Max": "Migliore quota", "Avg": "Media mercato",
}


def _num(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _fd_date(value: str) -> date:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised football-data date: {value!r}")


def _read_csv(url: str, cache_hours: float) -> list[dict]:
    try:
        raw = http_get(url, cache_hours=cache_hours)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        raise
    text = raw.decode("utf-8-sig", errors="replace")
    return [row for row in csv.DictReader(io.StringIO(text)) if row.get("HomeTeam")]


def fd_odds(row: dict, closing: bool = False) -> dict:
    """Extract every 1X2 / over-under 2.5 price in a football-data row, keyed by bookmaker."""
    tag = "C" if closing else ""
    books: dict[str, dict] = {}
    for prefix, label in FD_BOOKS.items():
        h, d, a = (_num(row.get(f"{prefix}{tag}{s}")) for s in "HDA")
        over, under = _num(row.get(f"{prefix}{tag}>2.5")), _num(row.get(f"{prefix}{tag}<2.5"))
        entry = {}
        if h and d and a:
            entry["1X2"] = {"1": h, "X": d, "2": a}
        if over and under:
            entry["OU2.5"] = {"Over 2.5": over, "Under 2.5": under}
        if entry:
            books[label] = entry
    return books


def load_fd_results(day: date, seasons_back: int = 1, leagues: tuple[str, ...] = FD_LEAGUES) -> list[dict]:
    """Finished domestic matches with goals, xG and closing odds."""
    matches = []
    for back in range(seasons_back + 1):
        code = season_code(day - timedelta(days=365 * back))
        cache = 6 if back == 0 else 24 * 30
        for league in leagues:
            for row in _read_csv(FD_RESULTS_URL.format(season=code, league=league), cache):
                hg, ag = _num(row.get("FTHG")), _num(row.get("FTAG"))
                if hg is None or ag is None:
                    continue
                matches.append({
                    "date": _fd_date(row["Date"]), "comp": league, "home": row["HomeTeam"].strip(),
                    "away": row["AwayTeam"].strip(), "hg": int(hg), "ag": int(ag),
                    "hxg": _num(row.get("HxG")), "axg": _num(row.get("AxG")),
                    "ht": (_num(row.get("HTHG")), _num(row.get("HTAG"))),
                    "fouls": (_num(row.get("HF")), _num(row.get("AF"))),
                    "shots": (_num(row.get("HS")), _num(row.get("AS"))),
                    "sot": (_num(row.get("HST")), _num(row.get("AST"))),
                    "corners": (_num(row.get("HC")), _num(row.get("AC"))),
                    "cards": (_num(row.get("HY")), _num(row.get("AY")), _num(row.get("HR")), _num(row.get("AR"))),
                    "closing": fd_odds(row, closing=True), "opening": fd_odds(row),
                })
    return matches


def load_fd_fixtures(league: str = "I1") -> list[dict]:
    """Upcoming matches with current odds (published by football-data a few days before kick-off)."""
    return [
        {"date": _fd_date(r["Date"]), "home": r["HomeTeam"].strip(), "away": r["AwayTeam"].strip(),
         "referee": r.get("Referee", ""), "odds": fd_odds(r)}
        for r in _read_csv(FD_FIXTURES_URL, cache_hours=2)
        if r.get("Div") == league
    ]


def american_to_decimal(value: str | float | None) -> float | None:
    if value in (None, ""):
        return None
    us = float(str(value).replace("+", ""))
    if us == 0:
        return None
    return round(1 + us / 100, 3) if us > 0 else round(1 + 100 / abs(us), 3)


def _espn_odds(competition: dict) -> dict:
    odds = (competition.get("odds") or [{}])[0]
    if not odds:
        return {}
    home = american_to_decimal((odds.get("homeTeamOdds") or {}).get("moneyLine"))
    away = american_to_decimal((odds.get("awayTeamOdds") or {}).get("moneyLine"))
    draw = american_to_decimal((odds.get("drawOdds") or {}).get("moneyLine"))
    entry = {}
    if home and draw and away:
        entry["1X2"] = {"1": home, "X": draw, "2": away}
    line, over, under = odds.get("overUnder"), odds.get("overOdds"), odds.get("underOdds")
    if line and over and under:
        entry[f"OU{line}"] = {f"Over {line}": american_to_decimal(over), f"Under {line}": american_to_decimal(under)}
    provider = (odds.get("provider") or {}).get("name", "ESPN")
    return {provider: entry} if entry else {}


def _espn_events(league: str, dates_param: str, cache_hours: float) -> list[dict]:
    url = f"{ESPN_BASE}/{league}/scoreboard?dates={dates_param}&limit=1000"
    try:
        return http_json(url, cache_hours=cache_hours).get("events", [])
    except urllib.error.HTTPError:
        return []


def _parse_event(event: dict, league: str, known: set[str] | None) -> dict:
    comp = event["competitions"][0]
    sides = {c["homeAway"]: c for c in comp["competitors"]}
    status = comp.get("status", {}).get("type", {})
    return {
        "id": event["id"], "league": league, "kickoff": event["date"],
        "date": datetime.fromisoformat(event["date"].replace("Z", "+00:00")).date(),
        "home": canonical_team(sides["home"]["team"]["displayName"], known),
        "away": canonical_team(sides["away"]["team"]["displayName"], known),
        "home_espn": sides["home"]["team"]["displayName"], "away_espn": sides["away"]["team"]["displayName"],
        "completed": bool(status.get("completed")),
        "hg": int(sides["home"].get("score") or 0), "ag": int(sides["away"].get("score") or 0),
        "odds": _espn_odds(comp),
    }


def espn_fixtures(league: str, start: date, end: date, known: set[str] | None = None) -> list[dict]:
    """Fixtures between two dates (inclusive), one request per day: ESPN rejects most ranges."""
    out, day = [], start
    while day <= end:
        for ev in _espn_events(league, day.strftime("%Y%m%d"), cache_hours=1):
            out.append(_parse_event(ev, league, known))
        day += timedelta(days=1)
    return out


def load_european_results(day: date, known: set[str], years_back: int = 1) -> list[dict]:
    """Finished UEFA club matches: they tie the domestic leagues onto one strength scale."""
    results = []
    for league in EUROPEAN_ESPN:
        for year in range(day.year - years_back, day.year + 1):
            cache = 6 if year == day.year else 24 * 30
            for ev in _espn_events(league, str(year), cache_hours=cache):
                match = _parse_event(ev, league, known)
                if match["completed"] and match["date"] < day:
                    results.append({**match, "comp": league, "hxg": None, "axg": None})
    return results


def espn_match_context(league: str, event_id: str) -> dict:
    """Form, top scorers/assists and standings for one match from the ESPN summary endpoint."""
    data = http_json(f"{ESPN_BASE}/{league}/summary?event={event_id}", cache_hours=3)
    form = {
        g["team"]["displayName"]: [f"{e.get('gameResult')} {e.get('score')} vs {e.get('opponent', {}).get('displayName', '?')}"
                                   for e in g.get("events", [])[:5]]
        for g in data.get("lastFiveGames", [])
    }
    leaders = {}
    for team in data.get("leaders", []):
        rows = []
        for cat in team.get("leaders", []):
            for item in cat.get("leaders", [])[:3]:
                rows.append(f"{cat.get('displayName')}: {item['athlete']['displayName']} ({item.get('displayValue')})")
        leaders[team["team"]["displayName"]] = rows
    table = []
    for group in (data.get("standings") or {}).get("groups", []):
        for entry in group.get("standings", {}).get("entries", []):
            stats = {s["name"]: s.get("displayValue") for s in entry.get("stats", [])}
            table.append({"team": entry["team"], "pts": stats.get("points"), "gp": stats.get("gamesPlayed"),
                          "rank": stats.get("rank"), "gd": stats.get("pointDifferential")})
    odds = _espn_odds({"odds": data.get("pickcenter") or data.get("odds") or []})
    return {"form": form, "leaders": leaders, "standings": table, "odds": odds}
