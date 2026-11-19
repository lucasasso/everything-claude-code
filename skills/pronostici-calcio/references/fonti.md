# Fonti dei dati

| Fonte | Cosa fornisce | Chiave |
|---|---|---|
| [football-data.co.uk](https://www.football-data.co.uk/data.php) | Risultati, xG, tiri, corner e cartellini di 11 campionati (Serie A, Premier League, Liga, Bundesliga, Ligue 1, Eredivisie, Portogallo, Belgio, Turchia, Grecia, Scozia). Quote d'apertura e di chiusura di 8 bookmaker, oltre a massimo e media. `fixtures.csv` contiene le quote delle prossime partite. | No |
| ESPN (API pubblica non ufficiale) | Calendari di Serie A, Champions, Europa League e Conference League, risultati europei, forma (ultime 5), classifiche, marcatori e assistman, quote DraftKings. | No |
| [The Odds API](https://the-odds-api.com) | Quote attuali di molti bookmaker europei (Pinnacle, Betfair, Unibet, William Hill…) su 1X2 e Over/Under, per Serie A e Champions. Il piano gratuito ha circa 500 richieste al mese. | `ODDS_API_KEY` |
| WebSearch | Notizie, probabili formazioni, squalifiche (vedi [news-e-aggiustamenti.md](news-e-aggiustamenti.md)). | No |

I dati scaricati restano in cache in `~/.cache/pronostici-calcio/` (cambia la cartella con `PRONOSTICI_DATA`). La stagione in corso si aggiorna ogni 6 ore, quelle passate ogni 30 giorni.

## Collegare il modello alla Champions

Le squadre di campionati diversi giocano raramente tra loro. Il modello stima tutti gli 11 campionati e le coppe europee insieme, così le partite europee mettono le forze di tutti i campionati sulla stessa scala.

Le squadre di campionati non coperti (Norvegia, Repubblica Ceca, Austria, Ucraina, Azerbaigian…) si stimano solo dalle partite europee. Restano vicine alla media e le loro previsioni sono meno affidabili.

Se un nome non viene riconosciuto, lo script avvisa e salta la partita. In quel caso aggiungi un alias in `scripts/common.py`, nel dizionario `ALIASES`.

## Quote del tuo bookmaker (`--quote file.csv`)

```csv
partita,mercato,selezione,quota,bookmaker
Atalanta - Inter,1X2,1,4.75,Snai
Atalanta - Inter,1X2,X,4.10,Snai
Atalanta - Inter,1X2,2,1.65,Snai
Atalanta - Inter,OU2.5,Over 2.5,1.62,Snai
Atalanta - Inter,OU2.5,Under 2.5,2.25,Snai
Atalanta - Inter,GG/NG,GG,1.60,Snai
Atalanta - Inter,GG/NG,NG,2.20,Snai
Atalanta - Inter,DC,X2,1.18,Snai
```

- `partita` va scritta "Casa - Ospite", con spazio, trattino, spazio.
- I mercati validi sono `1X2`, `DC`, `GG/NG`, `OU1.5`, `OU2.5` e `OU3.5`.
- Le selezioni sono `1`, `X`, `2`, `1X`, `X2`, `12`, `GG`, `NG`, `Over 2.5` e `Under 2.5`.
- La virgola decimale (`1,65`) va bene.
- Gli esiti della doppia chance si sovrappongono, quindi la sua quota equa si ricava dal consenso 1X2.
- Per GG/NG con un solo book, il "mercato" è quel book senza il suo margine. È un riferimento debole: tratta l'EV come un indizio, non come una prova.

## Impostare la chiave The Odds API

In una sessione cloud di Claude Code usa il form sicuro per le credenziali, per l'host `api.the-odds-api.com`. In locale scrivi `export ODDS_API_KEY=...`. Non incollare mai la chiave nella chat.
