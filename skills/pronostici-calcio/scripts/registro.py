"""Prediction ledger: every proposed selection, its probability and price, and how it settled.

One CSV row per leg. Legs that share a `schedina` name form one slip. Live legs record the minute
and the score when they were proposed, so "scores again" selections settle against that score.
"""

from __future__ import annotations

import csv
import math
import os
import re
from datetime import date, datetime
from pathlib import Path

from common import ESPN_BASE, canonical_team, http_json

SKILL_DIR = Path(__file__).resolve().parent.parent
FIELDS = ["id", "registrata", "schedina", "lega", "data", "partita", "selezione", "prob", "quota",
          "minuto", "punteggio", "esito", "finale"]
SIGNS = {"1", "X", "2", "1X", "X2", "12"}
CALIBRATION_BINS = ((0.0, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01))


def ledger_path() -> Path:
    return Path(os.environ.get("PRONOSTICI_REGISTRO", SKILL_DIR / "registro" / "registro.csv"))


def load() -> list[dict]:
    path = ledger_path()
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def save(rows: list[dict]) -> None:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)


def add(entries: list[dict]) -> int:
    """Append legs. Each needs schedina, lega (ESPN slug), data (YYYY-MM-DD), partita, selezione, prob, quota."""
    rows = load()
    next_id = max((int(r["id"]) for r in rows), default=0) + 1
    now = datetime.now().isoformat(timespec="minutes")
    for e in entries:
        missing = [k for k in ("schedina", "lega", "data", "partita", "selezione", "prob", "quota") if e.get(k) in (None, "")]
        if missing:
            raise ValueError(f"Giocata incompleta, mancano {missing}: {e}")
        prob, quota = float(e["prob"]), float(e["quota"])
        if not 0 < prob < 1 or quota <= 1:
            raise ValueError(f"Probabilità {prob} o quota {quota} non valide per {e['partita']} {e['selezione']}")
        date.fromisoformat(e["data"])
        rows.append({**{k: e.get(k, "") for k in FIELDS}, "id": next_id, "registrata": e.get("registrata") or now,
                     "prob": f"{prob:.4f}", "quota": f"{quota:.2f}", "minuto": e.get("minuto", 0),
                     "punteggio": e.get("punteggio", "0-0")})
        next_id += 1
    save(rows)
    return len(entries)


def settle(selection: str, final: tuple[int, int], at_registration: tuple[int, int] = (0, 0)) -> bool | None:
    """True/False for a selection given the final score; None when the score alone cannot decide it."""
    s = selection.strip()
    s = s[len("Segno "):] if s.startswith("Segno ") else s
    if " + " in s:
        parts = [settle(p, final, at_registration) for p in s.split(" + ")]
        return None if None in parts else all(parts)

    hg, ag = final
    total = hg + ag
    if s in SIGNS:
        outcome = "1" if hg > ag else "2" if hg < ag else "X"
        return outcome in s
    if m := re.fullmatch(r"(Over|Under) (\d+\.5)", s):
        return total > float(m[2]) if m[1] == "Over" else total < float(m[2])
    if s in ("GG", "NG"):
        both = hg > 0 and ag > 0
        return both if s == "GG" else not both
    if m := re.fullmatch(r"(Casa|Ospite) (Over|Under) (\d+\.5)", s):
        goals = hg if m[1] == "Casa" else ag
        return goals > float(m[3]) if m[2] == "Over" else goals < float(m[3])
    if m := re.fullmatch(r"(Casa|Ospite) segna( nel 2T| ancora)?", s):
        side = 0 if m[1] == "Casa" else 1
        return final[side] > (at_registration[side] if m[2] else 0)
    if m := re.fullmatch(r"Handicap ([12]) \(-(\d+)\)", s):
        margin = hg - ag if m[1] == "1" else ag - hg
        return margin > int(m[2])
    if m := re.fullmatch(r"(Casa|Ospite) vince a zero", s):
        return (hg > ag and ag == 0) if m[1] == "Casa" else (ag > hg and hg == 0)
    if m := re.fullmatch(r"Multigol (?:(Casa|Ospite) )?(\d+)-(\d+)", s):
        goals = total if not m[1] else hg if m[1] == "Casa" else ag
        return int(m[2]) <= goals <= int(m[3])
    return None


def update(today: date | None = None) -> int:
    """Settle open legs from ESPN final scores. Returns how many legs were settled."""
    today = today or date.today()
    rows = load()
    open_rows = [r for r in rows if not r["esito"] and date.fromisoformat(r["data"]) <= today]
    finals: dict[tuple[str, str], list[tuple[str, str, int, int]]] = {}
    settled = 0
    for r in open_rows:
        key = (r["lega"], r["data"])
        if key not in finals:
            finals[key] = _espn_finals(*key)
        home, _, away = r["partita"].partition(" - ")
        match = _find(finals[key], home, away)
        if not match:
            continue
        hg, ag = match
        reg = tuple(int(x) for x in (r.get("punteggio") or "0-0").split("-"))
        result = settle(r["selezione"], (hg, ag), reg)
        r["finale"] = f"{hg}-{ag}"
        if result is not None:
            r["esito"] = "vinta" if result else "persa"
            settled += 1
    save(rows)
    return settled


def set_outcome(leg_id: int, outcome: str) -> None:
    if outcome not in ("vinta", "persa"):
        raise ValueError(f"Esito non valido: {outcome!r} (usa vinta o persa)")
    rows = load()
    for r in rows:
        if int(r["id"]) == leg_id:
            r["esito"] = outcome
            save(rows)
            return
    raise KeyError(f"Nessuna giocata con id {leg_id}")


def summary(rows: list[dict] | None = None) -> dict:
    """Hits against expectation, Brier score and log loss per leg; results and flat-stake profit per slip."""
    rows = load() if rows is None else rows
    legs = [r for r in rows if r["esito"] in ("vinta", "persa")]
    out = {"giocate_registrate": len(rows), "giocate_chiuse": len(legs)}
    if not legs:
        return out

    def stats(items: list[dict]) -> dict:
        p = [float(r["prob"]) for r in items]
        y = [r["esito"] == "vinta" for r in items]
        return {"giocate": len(items), "vinte": sum(y), "attese": round(sum(p), 1),
                "brier": round(sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / len(p), 3),
                "log_loss": round(-sum(math.log(pi if yi else 1 - pi) for pi, yi in zip(p, y)) / len(p), 3)}

    out["tutte"] = stats(legs)
    unique = {(r["data"], r["partita"], r["selezione"], r.get("minuto") or "0"): r for r in legs}
    out["previsioni_uniche"] = stats(list(unique.values()))
    out["pre_partita"] = stats([r for r in legs if int(r.get("minuto") or 0) == 0]) if any(
        int(r.get("minuto") or 0) == 0 for r in legs) else {}
    out["live"] = stats([r for r in legs if int(r.get("minuto") or 0) > 0]) if any(
        int(r.get("minuto") or 0) > 0 for r in legs) else {}
    out["calibrazione"] = {f"{lo:.0%}-{min(hi, 1):.0%}": stats(b) for lo, hi in CALIBRATION_BINS
                           if (b := [r for r in legs if lo <= float(r["prob"]) < hi])}

    slips: dict[str, list[dict]] = {}
    for r in rows:
        slips.setdefault(r["schedina"], []).append(r)
    closed = {name: ls for name, ls in slips.items() if all(r["esito"] in ("vinta", "persa") for r in ls)}
    won = [n for n, ls in closed.items() if all(r["esito"] == "vinta" for r in ls)]
    profit = sum(math.prod(float(r["quota"]) for r in closed[n]) for n in won) - len(closed)
    out["schedine"] = {"chiuse": len(closed), "vinte": len(won),
                       "attese": round(sum(math.prod(float(r["prob"]) for r in ls) for ls in closed.values()), 1),
                       "profitto_unita": round(profit, 2), "roi": round(profit / len(closed), 3) if closed else None,
                       "vinte_elenco": won}
    return out


def _espn_finals(league: str, day: str) -> list[tuple[str, str, int, int]]:
    data = http_json(f"{ESPN_BASE}/{league}/scoreboard?dates={day.replace('-', '')}", cache_hours=1)
    out = []
    for e in data.get("events", []):
        c = e["competitions"][0]
        if not c.get("status", {}).get("type", {}).get("completed"):
            continue
        sides = {x["homeAway"]: x for x in c["competitors"]}
        out.append((sides["home"]["team"]["displayName"], sides["away"]["team"]["displayName"],
                    int(sides["home"]["score"]), int(sides["away"]["score"])))
    return out


def _find(finals: list[tuple[str, str, int, int]], home: str, away: str) -> tuple[int, int] | None:
    known = {home, away}
    for h, a, hg, ag in finals:
        if canonical_team(h, known) == canonical_team(home, known) and canonical_team(a, known) == canonical_team(away, known):
            return hg, ag
    return None
