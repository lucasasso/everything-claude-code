"""Markdown rendering of a round analysis and its slip."""

from __future__ import annotations

from odds_tools import market_move

KEY_MARKETS = ("1X2", "DC", "OU2.5", "GG/NG")


def _pct(p: float | None) -> str:
    return "–" if p is None else f"{p:.0%}"


def _odd(o: float | None) -> str:
    return "–" if o is None else f"{o:.2f}"


def render(analysis: dict, slip: dict) -> str:
    lines = [f"# Pronostici {analysis['competizione']} — {analysis['dal']} / {analysis['al']}", "",
             f"Modello aggiornato al {analysis['modello']['aggiornato']} · rho {analysis['modello']['rho']:.3f} · "
             f"peso modello vs mercato {analysis['peso_modello']:.0%} · fonti quote: {', '.join(analysis['fonti_quote']) or 'nessuna'}", ""]

    lines += _render_slip(slip)
    lines += ["", "## Errori di quota e anomalie", ""]
    alerts = [(m["partita"], a) for m in analysis["partite"] for mk in m["mercati"] for a in mk["allerte"]]
    if alerts:
        lines += [f"- **{a['tipo']}** · {p} · {a['selezione']}: {a['dettaglio']}" for p, a in alerts]
    else:
        lines.append("Nessuna anomalia sopra soglia.")

    lines += ["", "## Analisi partita per partita", ""]
    for m in analysis["partite"]:
        lines += _render_match(m)
    lines += ["", "---", "_Le probabilità sono stime, non certezze. Il margine dei bookmaker rende negativa l'attesa "
              "di chi scommette senza un vantaggio reale. Gioca solo con importi che puoi permetterti di perdere; "
              "aiuto: Telefono Verde Nazionale per le problematiche del gioco d'azzardo 800 558822 (ISS)._"]
    return "\n".join(lines)


def _render_slip(slip: dict) -> list[str]:
    out = ["## Schedina", "", "### Singole di valore (EV positivo)", ""]
    if slip["singole_valore"]:
        out += ["| Partita | Mercato | Esito | Quota | Book | Prob. | EV | Puntata |", "|---|---|---|---|---|---|---|---|"]
        out += [f"| {s['partita']} | {s['mercato']} | {s['selezione']} | {_odd(s['miglior_quota'])} | {s['book']} | "
                f"{_pct(s['p_finale'])} | {s['ev']:+.1%} | {s['puntata']:.2f} ({s['puntata_pct']}%) |" for s in slip["singole_valore"]]
    else:
        out.append("Nessuna giocata supera la soglia di valore: questa giornata il consiglio è non forzare.")

    mult = slip["multipla"]
    out += ["", "### Multipla (selezioni di valore più probabili)", ""]
    if mult:
        out += [f"- {s['partita']}: **{s['selezione']}** ({s['mercato']}) @ {_odd(s['miglior_quota'])}" for s in mult["selezioni"]]
        out.append(f"- Quota totale **{mult['quota_totale']}**, probabilità stimata {_pct(mult['probabilita'])}, "
                   f"EV {mult['ev']:+.1%}, puntata suggerita {mult['puntata']:.2f}")
    else:
        out.append("Meno di due selezioni con valore e probabilità ≥ 50%: multipla non consigliata.")

    out += ["", "### Esiti più probabili 1X2 (non necessariamente di valore)", "",
            "| Partita | Segno | Prob. | Miglior quota |", "|---|---|---|---|"]
    out += [f"| {x['partita']} | {x['segno']} | {_pct(x['p_finale'])} | {_odd(x['quota'])} |" for x in slip["esiti_piu_probabili"]]
    return out


def _render_match(m: dict) -> list[str]:
    out = [f"### {m['partita']} — {m['data']}", "",
           f"Gol attesi: {m['modello']['xg_home']} – {m['modello']['xg_away']}"]
    moves = market_move((m.get("contesto") or {}).get("movimento") or {})
    if moves:
        out.append("Movimento quote (apertura → ora): " + "; ".join(
            f"{mk} " + ", ".join(f"{sel} {d * 100:+.0f}pp" for sel, d in sels.items()) for mk, sels in moves.items()))
    adj = m.get("aggiustamenti_news")
    if adj:
        out.append("Aggiustamenti news: " + "; ".join(f"{t}: {v.get('motivo', '')} (att {v.get('attacco', 0):+.0%}, "
                                                       f"dif {v.get('difesa', 0):+.0%})" for t, v in adj.items()))
    for team_stats in m.get("statistiche", []):
        tot = team_stats.get("totale") or {}
        if tot:
            out.append(f"- **{team_stats['squadra']}** forma {team_stats.get('forma', '')} · gol {tot['gol_fatti']}/{tot['gol_subiti']} "
                       f"· xG {tot['xg_fatti']}/{tot['xg_subiti']} · tiri {tot['tiri']} · gol−xG {team_stats.get('delta_gol_xg')}")
    for team, rows in (m.get("contesto") or {}).get("leaders", {}).items():
        if rows:
            out.append(f"- Leader {team}: " + "; ".join(rows[:4]))
    out += ["", "| Mercato | Esito | Modello | Mercato | Finale | Quota equa | Miglior quota | EV |", "|---|---|---|---|---|---|---|---|"]
    for mk in m["mercati"]:
        if mk["mercato"] not in KEY_MARKETS:
            continue
        for r in mk["righe"]:
            ev = "–" if r["ev"] is None else f"{r['ev']:+.1%}"
            out.append(f"| {mk['mercato']} | {r['selezione']} | {_pct(r['p_modello'])} | {_pct(r['p_mercato'])} | "
                       f"{_pct(r['p_finale'])} | {_odd(r['quota_equa'])} | {_odd(r['miglior_quota'])} {r['book'] or ''} | {ev} |")
    exact = next((mk for mk in m["mercati"] if mk["mercato"] == "Risultato esatto"), None)
    if exact:
        out.append("\nRisultati esatti più probabili: " + ", ".join(f"{r['selezione']} ({_pct(r['p_modello'])})" for r in exact["righe"][:4]))
    return out + [""]
