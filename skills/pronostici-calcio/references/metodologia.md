# Metodologia

## 1. Modello delle squadre (Dixon-Coles)

I gol di ciascuna squadra seguono una distribuzione di Poisson:

- `log λ_casa = μ + vantaggio_casa[competizione] + attacco[casa] + difesa[ospite]`
- `log λ_ospite = μ + attacco[ospite] + difesa[casa]`

La stima avviene così:

- **Obiettivo misto**: 40% gol reali e 60% xG, quando gli xG ci sono. Gli xG sono meno rumorosi dei gol e convergono prima.
- **Peso nel tempo**: le partite contano meno man mano che invecchiano, con un'emivita di 180 giorni.
- **Shrinkage (ridge)**: le squadre con poche partite, come le neopromosse o i club europei minori, restano vicine alla media.
- **Correzione di Dixon-Coles (ρ)** sui punteggi bassi (0-0, 1-0, 0-1, 1-1), stimata sui gol reali.
- **Stima congiunta** di 11 campionati più Champions, Europa League e Conference League, per due stagioni. Le partite europee mettono tutti i campionati sulla stessa scala di forza.

Dalla matrice dei punteggi (0-10 gol per squadra) derivano i mercati 1X2, doppia chance, Over/Under 1.5/2.5/3.5, GG/NG e risultato esatto.

Le notizie entrano come aggiustamenti moltiplicativi su λ, limitati a ±25% (vedi [news-e-aggiustamenti.md](news-e-aggiustamenti.md)).

## 2. Togliere il margine (de-vig)

`1/quota` sommato su tutti gli esiti dà più di 1. L'eccedenza è il margine del bookmaker. Per ricavare probabilità eque ci sono tre metodi:

- **moltiplicativo**: scala tutte le probabilità nella stessa proporzione;
- **power** (il default): eleva le probabilità a un esponente `k` tale che la somma faccia 1. Toglie più margine agli sfavoriti, e questo corregge il favourite-longshot bias tipico del calcio;
- **Shin**: un modello di insider trading, con risultati simili al power.

Il **consenso di mercato** usa la fonte migliore disponibile: Pinnacle, poi Betfair Exchange, poi la mediana dei book senza margine. Per la doppia chance il consenso si ricava dall'1X2.

## 3. Probabilità finale e valore

- `p_finale = peso × p_modello + (1 − peso) × p_mercato`. Il peso di default è 0.10.
- `EV = p_finale × quota − 1`. Una giocata è di valore se l'EV è almeno del 3% (`--min-edge`).
- La puntata segue il **Kelly frazionato**: un quarto di Kelly, con un massimo del 2% del bankroll per le singole e dell'1% per la multipla.
- Ogni partita entra in schedina una sola volta, con la giocata a EV più alto. Così si evitano giocate correlate sulla stessa partita.
- Restano fuori il risultato esatto (varianza troppo alta) e le quote fuori dall'intervallo 1.30–6.00.

## 4. Errori di quota

| Allerta | Regola | Come leggerla |
|---|---|---|
| QUOTA FUORI LINEA | La quota del book supera di almeno il 2% la quota equa di consenso | È il segnale più concreto: prendi la quota migliore. Controlla però che la partita sia la stessa e che i limiti di puntata lo permettano. Le quote palesemente sbagliate possono essere annullate dal regolamento del book. |
| SUREBET | La somma di 1/miglior quota sugli esiti è sotto 1 | Il profitto è garantito solo se riesci a piazzare tutte le puntate prima che le quote cambino. I book limitano i conti che le sfruttano. |
| DIVERGENZA MODELLO | Modello e mercato differiscono di almeno 8 punti percentuali | Quasi sempre è un'informazione che il modello non ha. Cerca le notizie prima di considerarla un'occasione. |

## 5. Backtest (Serie A, aggiornamento settimanale, 1X2)

Sono stati misurati con `python3 pronostici.py backtest` il 19/11/2026. Le partite valutate sono circa 340 per stagione, dalla sesta settimana in poi.

| Stagione | Log-loss modello | Mercato in apertura | Mercato in chiusura | Combinato (peso 0.10) |
|---|---|---|---|---|
| 2024-25 | 0.967 | 0.934 | 0.933 | 0.936 |
| 2025-26 | 1.001 | 0.980 | 0.977 | 0.981 |

Strategia "miglior quota oltre il consenso d'apertura di almeno il 2%":

| Stagione | Giocate | ROI | CLV medio |
|---|---|---|---|
| 2024-25 | 111 | −19.3% | −0.7% |
| 2025-26 | 46 | −14.7% | +3.2% |

Cosa dicono i numeri, senza abbellimenti:

- Il mercato è più preciso del modello. Mescolarli non migliora le previsioni rispetto al mercato da solo, per questo il peso del modello è basso.
- La caccia alla quota migliore non ha prodotto profitti in queste due stagioni. Il CLV è vicino a zero, quindi non c'è un vantaggio dimostrato.
- Il valore pratico della skill sta altrove:
  - le probabilità di tutti i mercati sulla stessa scala;
  - i book del tuo conto confrontati con il consenso, per non accettare quote peggiori di quelle eque;
  - le divergenze, che indicano dove cercare notizie;
  - la disciplina: puntate piccole e nessuna giocata forzata.
- Lo strato delle notizie, che è il giudizio dell'agente, non è coperto da questi backtest.

Rilancia il backtest dopo ogni modifica del modello e aggiorna questa tabella.
