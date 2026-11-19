"""Team statistics from football-data.co.uk match rows (current season)."""

from __future__ import annotations

from datetime import date


def _avg(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def team_stats(matches: list[dict], team: str, since: date) -> dict:
    """Per-game averages and recent form for one team, split home/away."""
    rows = sorted((m for m in matches if m["date"] >= since and team in (m["home"], m["away"])), key=lambda m: m["date"])
    if not rows:
        return {"squadra": team, "partite": 0}

    def side(m: dict) -> dict:
        home = m["home"] == team
        gf, ga = (m["hg"], m["ag"]) if home else (m["ag"], m["hg"])
        xgf, xga = (m.get("hxg"), m.get("axg")) if home else (m.get("axg"), m.get("hxg"))
        i, j = (0, 1) if home else (1, 0)
        shots, sot, corners = m.get("shots") or (None, None), m.get("sot") or (None, None), m.get("corners") or (None, None)
        cards = m.get("cards") or (None, None, None, None)
        return {"home": home, "gf": gf, "ga": ga, "xgf": xgf, "xga": xga, "tiri": shots[i], "tiri_sub": shots[j],
                "in_porta": sot[i], "corner": corners[i], "gialli": cards[i], "rossi": cards[2 + i],
                "res": "V" if gf > ga else "P" if gf < ga else "N",
                "label": f"{m['date']:%d/%m} {m['home']} {m['hg']}-{m['ag']} {m['away']}"}

    data = [side(m) for m in rows]

    def summary(items: list[dict]) -> dict:
        if not items:
            return {}
        return {"partite": len(items), "punti_media": round(sum(3 if x["res"] == "V" else x["res"] == "N" for x in items) / len(items), 2),
                "gol_fatti": _avg([x["gf"] for x in items]), "gol_subiti": _avg([x["ga"] for x in items]),
                "xg_fatti": _avg([x["xgf"] for x in items]), "xg_subiti": _avg([x["xga"] for x in items]),
                "tiri": _avg([x["tiri"] for x in items]), "tiri_concessi": _avg([x["tiri_sub"] for x in items]),
                "tiri_in_porta": _avg([x["in_porta"] for x in items]), "corner": _avg([x["corner"] for x in items]),
                "gialli": _avg([x["gialli"] for x in items]), "rossi_totali": sum(x["rossi"] or 0 for x in items),
                "clean_sheet": sum(x["ga"] == 0 for x in items), "gg": sum(x["gf"] > 0 and x["ga"] > 0 for x in items),
                "over25": sum(x["gf"] + x["ga"] > 2 for x in items)}

    last5 = data[-5:]
    return {
        "squadra": team, "totale": summary(data), "casa": summary([x for x in data if x["home"]]),
        "trasferta": summary([x for x in data if not x["home"]]), "ultime5": summary(last5),
        "forma": "".join(x["res"] for x in last5), "ultime_partite": [x["label"] for x in last5],
        # Goals minus xG: large positive values usually regress (finishing luck), negative ones recover.
        "delta_gol_xg": round(sum(x["gf"] for x in data) - sum(x["xgf"] or 0 for x in data), 1)
        if all(x["xgf"] is not None for x in data) else None,
    }
