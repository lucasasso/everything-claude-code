"""Shared helpers: cached HTTP, paths, team-name normalisation."""

from __future__ import annotations

import difflib
import gzip
import hashlib
import json
import os
import time
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

DATA_DIR = Path(os.environ.get("PRONOSTICI_DATA", Path.home() / ".cache" / "pronostici-calcio"))
CACHE_DIR = DATA_DIR / "http"
USER_AGENT = "pronostici-calcio/1.0"
DEFAULT_CACHE_HOURS = 6.0

# Leagues fitted jointly so that Champions League opponents share one strength scale.
FD_LEAGUES = ("I1", "E0", "SP1", "D1", "F1", "N1", "P1", "B1", "T1", "G1", "SC0")

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
COMPETITIONS = {
    "serie-a": {"espn": "ita.1", "fd": "I1", "label": "Serie A"},
    "champions": {"espn": "uefa.champions", "fd": None, "label": "Champions League"},
}
EUROPEAN_ESPN = ("uefa.champions", "uefa.europa", "uefa.europa.conf")

# ESPN/bookmaker spellings -> football-data.co.uk spellings.
ALIASES = {
    "internazionale": "Inter", "inter milan": "Inter", "fc internazionale milano": "Inter",
    "ac milan": "Milan", "as roma": "Roma", "ss lazio": "Lazio", "ssc napoli": "Napoli",
    "hellas verona": "Verona", "borussia dortmund": "Dortmund", "manchester city": "Man City",
    "manchester united": "Man United", "paris saint-germain": "Paris SG", "psg": "Paris SG",
    "atletico madrid": "Ath Madrid", "athletic club": "Ath Bilbao", "real betis": "Betis",
    "feyenoord rotterdam": "Feyenoord", "fc porto": "Porto", "sporting cp": "Sp Lisbon",
    "sporting lisbon": "Sp Lisbon", "sl benfica": "Benfica", "sc braga": "Sp Braga",
    "vfb stuttgart": "Stuttgart", "bayer leverkusen": "Leverkusen", "eintracht frankfurt": "Ein Frankfurt",
    "borussia monchengladbach": "M'gladbach", "bayern munich": "Bayern Munich", "fc bayern munchen": "Bayern Munich",
    "tottenham hotspur": "Tottenham", "newcastle united": "Newcastle", "nottingham forest": "Nott'm Forest",
    "wolverhampton wanderers": "Wolves", "olympique de marseille": "Marseille", "olympique lyonnais": "Lyon",
    "as monaco": "Monaco", "stade brestois 29": "Brest", "psv eindhoven": "PSV Eindhoven", "az alkmaar": "AZ Alkmaar",
    "club brugge": "Club Brugge", "royal antwerp": "Antwerp", "celtic": "Celtic", "rangers": "Rangers",
    "olympiacos": "Olympiakos", "aek athens": "AEK", "paok salonika": "PAOK", "fenerbahce": "Fenerbahce",
    "galatasaray": "Galatasaray", "besiktas": "Besiktas", "rb leipzig": "RB Leipzig",
    "1. fc heidenheim 1846": "Heidenheim", "ajax amsterdam": "Ajax", "braga": "Sp Braga",
    "brighton & hove albion": "Brighton", "celta vigo": "Celta", "heart of midlothian": "Hearts",
    "kaa gent": "Gent", "nec nijmegen": "Nijmegen", "racing genk": "Genk", "rayo vallecano": "Vallecano",
    "real sociedad": "Sociedad", "sint-truidense": "St Truiden", "stade rennais": "Rennes",
    "union st.-gilloise": "St. Gilloise", "vitória de guimaraes": "Guimaraes", "fc twente": "Twente",
    "fc utrecht": "Utrecht", "go ahead eagles": "Go Ahead Eagles", "aston villa": "Aston Villa",
}


def http_get(url: str, *, cache_hours: float = DEFAULT_CACHE_HOURS, headers: dict | None = None) -> bytes:
    """GET with an on-disk cache; transparently handles gzip bodies."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = CACHE_DIR / hashlib.sha1(url.encode()).hexdigest()
    if key.exists() and time.time() - key.stat().st_mtime < cache_hours * 3600:
        return key.read_bytes()

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    key.write_bytes(body)
    return body


def http_json(url: str, **kwargs) -> dict:
    return json.loads(http_get(url, **kwargs))


def season_code(day: date) -> str:
    """football-data.co.uk season folder, e.g. 2026-11-19 -> '2627'."""
    start = day.year if day.month >= 7 else day.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def _fold(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace(".", " ").split())


def canonical_team(name: str, known: set[str] | None = None) -> str:
    """Map any spelling to the football-data.co.uk name when one can be found."""
    folded = _fold(name)
    if folded in _FOLDED_ALIASES:
        return _FOLDED_ALIASES[folded]
    if not known:
        return name.strip()

    by_fold = {_fold(k): k for k in known}
    if folded in by_fold:
        return by_fold[folded]
    for prefix in ("fc ", "ac ", "as ", "ss ", "us ", "sc ", "afc ", "cf "):
        if folded.startswith(prefix) and folded[len(prefix):] in by_fold:
            return by_fold[folded[len(prefix):]]
    match = difflib.get_close_matches(folded, list(by_fold), n=1, cutoff=0.82)
    return by_fold[match[0]] if match else name.strip()


_FOLDED_ALIASES = {_fold(k): v for k, v in ALIASES.items()}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
