---
name: pronostici-calcio
description: Analizza le partite di Serie A e Champions League per prevederle e comporre la schedina di ogni giornata. Stima le probabilità con un modello Dixon-Coles su gol e xG, confronta le quote di più bookmaker togliendo il margine, e segnala gli errori di quota (prezzi fuori linea, surebet, divergenze modello-mercato). Usa le statistiche di squadre e giocatori e le notizie della settimana fuori dal campo (infortuni, squalifiche, turnover, crisi societarie). Usala quando l'utente chiede pronostici, una schedina, quote di valore, value bet o analisi pre-partita.
metadata:
  version: 1.0.0
  language: it
---

# Pronostici Serie A e Champions League

Tu sei l'analista: unisci i numeri dello script con le notizie della settimana, poi presenti una schedina onesta. Il modello da solo **non** batte il mercato (vedi i backtest in [references/metodologia.md](references/metodologia.md)). Il valore aggiunto viene da tre cose: confrontare molti bookmaker, leggere le notizie prima che le quote si muovano, e non forzare le giocate.

Script: `scripts/pronostici.py` (Python 3.10+, `numpy`, `scipy`; installa con `pip install numpy scipy` se mancano). Lancia ogni comando dalla cartella `scripts/`.

## Flusso per ogni giornata

### 1. Individua le partite

- Serie A: il weekend della giornata (di solito da venerdì a lunedì).
- Champions: martedì e mercoledì della giornata (a volte anche giovedì).
- Se l'utente non dà le date, usa la giornata successiva a oggi. Lo script legge il calendario ESPN, quindi basta un intervallo largo (`--dal`/`--al`).

### 2. Prima analisi, senza news

```bash
python3 pronostici.py -v giornata --comp serie-a --dal 2026-11-21 --al 2026-11-23
python3 pronostici.py -v giornata --comp champions --dal 2026-11-24 --al 2026-11-25
```

Lo script produce `analisi.json`, `schedina.json` e `report.md` in `pronostici/<comp>-<data>/`. Nel report trovi, per ogni partita:

- gol attesi;
- probabilità 1X2, doppia chance, Over/Under 1.5, 2.5 e 3.5, GG/NG e risultati esatti;
- le statistiche delle due squadre (forma, gol e xG fatti e subiti, tiri, gol meno xG);
- i marcatori e gli assistman (ESPN);
- il confronto con le quote.

### 3. Notizie della settimana (fuori dal campo)

Per ogni partita cerca sul web e compila `news.json`. Segui la checklist e la tabella degli aggiustamenti in [references/news-e-aggiustamenti.md](references/news-e-aggiustamenti.md):

- infortunati, squalificati, diffidati, probabili formazioni;
- turnover per coppe o nazionali, stanchezza, viaggi;
- cambio di allenatore, crisi societarie, problemi di stipendi, penalizzazioni, contestazioni;
- motivazioni (derby, salvezza, qualificazione già ottenuta), meteo, campo.

Cita la fonte e la data di ogni notizia. Una notizia non verificata non entra in `news.json`.

### 4. Quote del bookmaker dell'utente

Le fonti automatiche sono queste:

- ESPN/DraftKings, sempre;
- football-data.co.uk per la Serie A (8 bookmaker, Pinnacle o Betfair Exchange compresi, pubblicate 2-3 giorni prima);
- The Odds API, se è impostata `ODDS_API_KEY`.

Se l'utente gioca su un bookmaker italiano (Snai, Sisal, Eurobet, Goldbet, Lottomatica, Bet365.it…), chiedigli di incollare le quote. Salvale in un CSV con il formato descritto in [references/fonti.md](references/fonti.md). Rilevare un errore di quota sul **suo** conto è l'uso più concreto della skill.

### 5. Analisi finale e schedina

```bash
python3 pronostici.py giornata --comp serie-a --dal 2026-11-21 --al 2026-11-23 --news news.json --quote snai.csv --bankroll 50
python3 pronostici.py schedina --analisi pronostici/serie-a-2026-11-21/analisi.json --bankroll 50 --min-edge 0.03
```

### 6. Presenta il risultato

Rispondi in italiano con:

1. **Errori di quota** in testa, perché sono il segnale più concreto:
   - QUOTA FUORI LINEA: un book paga più della quota equa di consenso;
   - SUREBET: coprendo tutti gli esiti su book diversi il guadagno è garantito;
   - DIVERGENZA MODELLO: modello e mercato non concordano. Spiegala con le news o dichiarala non spiegata.
2. **Schedina**: singole di valore con quota, book, probabilità, EV e puntata (Kelly frazionato), poi la multipla se ha senso.
   - Spiega che la multipla moltiplica anche il margine del bookmaker.
3. **Esiti più probabili**, distinti dalle giocate di valore. Una quota bassa su un esito probabile non è valore.
4. **Motivazioni** in 1-2 righe per giocata: numeri del modello più notizie, con le fonti.
5. **Avvertenza** breve: sono stime, niente è sicuro, gioca solo cifre che puoi perdere. In Italia c'è il Telefono Verde Nazionale per i problemi da gioco d'azzardo: 800 558822.

## Regole

- Non inventare quote, formazioni o notizie. Se un dato manca, scrivi che manca.
- Non promettere vincite e non chiamare "sicura" nessuna giocata.
- Se nessuna giocata supera la soglia, dillo: "questa giornata non giocare" è una risposta valida.
- Il peso del modello è basso (`--peso-modello 0.10`) perché nei backtest il mercato è più preciso. Aumentalo solo se l'utente lo chiede e spiegagli il rischio.
- Una divergenza forte tra modello e mercato di solito è un'informazione che il modello non ha, come un infortunio o il turnover. Cercala prima di considerarla un'occasione.
- Per una squadra appena promossa o con pochi dati, il modello è meno affidabile: dillo.
- Aggiorna la valutazione di una partita quando escono le formazioni ufficiali (circa un'ora prima).

## Altri comandi

```bash
python3 pronostici.py statistiche --squadra Inter            # statistiche stagionali, casa/trasferta, forma
python3 pronostici.py classifica-forza --top 40              # ranking unico di tutti i campionati principali
python3 pronostici.py backtest --lega I1 --stagione 2526     # verifica la precisione su una stagione passata
```

I test offline si lanciano dalla cartella della skill con `python3 -m pytest tests -q`.

## Riferimenti

- [references/metodologia.md](references/metodologia.md): modello, de-vig, valore, Kelly, risultati dei backtest.
- [references/news-e-aggiustamenti.md](references/news-e-aggiustamenti.md): checklist delle notizie e formato di `news.json`.
- [references/fonti.md](references/fonti.md): fonti dei dati, chiave The Odds API, formato del CSV delle quote.
