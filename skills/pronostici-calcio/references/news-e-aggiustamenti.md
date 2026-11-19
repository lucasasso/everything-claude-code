# Notizie della settimana e aggiustamenti

Il modello vede solo risultati e xG. Le notizie gli dicono cosa cambia **in questa** partita. Traduci ogni notizia verificata in un aggiustamento piccolo e motivato.

## Checklist per ogni squadra

Cerca con WebSearch, usando query in italiano e la data della settimana. Esempi:

- `probabili formazioni <Casa> <Ospite>`
- `<Squadra> infortunati squalificati`
- `<Squadra> conferenza stampa allenatore`
- `<Squadra> notizie oggi`

Fonti utili:

- Gazzetta, Corriere dello Sport, Tuttosport, Sky Sport;
- Fantacalcio.it per le probabili formazioni e gli indisponibili;
- i siti ufficiali dei club e la Lega Serie A per le squalifiche del Giudice Sportivo;
- UEFA.com per la Champions.

| Area | Cosa cercare |
|---|---|
| Indisponibili | Infortuni e squalifiche di titolari. Pesa il ruolo: il centravanti titolare o il portiere contano più di un terzino di riserva. |
| Formazioni | Probabili undici, ballottaggi, rientri. Confermale con le formazioni ufficiali circa un'ora prima. |
| Calendario | Partita di coppa 3 giorni prima o dopo, rischio turnover, viaggi lunghi, sosta per le nazionali appena finita (giocatori rientrati stanchi o infortunati). |
| Panchina | Esonero o nuovo allenatore (spesso c'è un rimbalzo a breve), allenatore sotto pressione. |
| Società | Stipendi non pagati, penalizzazioni, cambio di proprietà, mercato di gennaio, contestazioni dei tifosi, spogliatoio diviso. |
| Motivazioni | Derby, scontro salvezza, qualificazione europea già decisa o impossibile, ultima giornata del girone. |
| Contesto | Meteo estremo (pioggia forte e vento abbassano i gol), campo pesante, porte chiuse o curva squalificata. |
| Arbitro | Solo per i mercati sui cartellini. Non cambia i gol attesi. |

## Tabella degli aggiustamenti

`attacco` cambia i gol che la squadra segna. `difesa` cambia i gol che subisce, quindi un numero positivo vuol dire che subisce di più. Lo script limita ogni valore a ±25%.

| Notizia | Aggiustamento indicativo |
|---|---|
| Manca il miglior attaccante (oltre il 30% dei gol o degli xG) | attacco −8% / −12% |
| Mancano due titolari offensivi | attacco −10% / −15% |
| Manca il portiere titolare (riserva molto più debole) | difesa +5% / +8% |
| Mancano due o più difensori titolari | difesa +6% / +10% |
| Turnover pesante annunciato (5 o più cambi) | attacco −8%, difesa +8% |
| Coppa tre giorni prima con trasferta lunga | attacco −3%, difesa +3% |
| Nuovo allenatore (prime 2-3 partite) | attacco +3% (effetto incerto, usa con prudenza) |
| Crisi societaria grave, stipendi non pagati | attacco −5%, difesa +5% |
| Nessuna motivazione (obiettivo già raggiunto) | attacco −5%, difesa +5% |
| Pioggia forte o vento forte | attacco −5% per entrambe |

Non sommare notizie che si sovrappongono: il turnover include già alcune assenze. Il mercato spesso ha già incorporato le notizie note da giorni. Se la quota si è già mossa nella direzione della notizia, l'aggiustamento serve a capire la partita, non è un vantaggio.

## Formato di `news.json`

```json
{
  "Inter": {"attacco": -0.10, "difesa": 0.0, "motivo": "Lautaro squalificato (Giudice Sportivo, 18/11)", "fonti": ["https://..."]},
  "Atalanta": {"attacco": 0.0, "difesa": 0.06, "motivo": "Out Djimsiti e Hien (Gazzetta, 20/11)", "fonti": ["https://..."]}
}
```

- Le chiavi sono i nomi delle squadre. Vanno bene le grafie ESPN o italiane, perché lo script le normalizza.
- `motivo` e `fonti` finiscono nel report. Compilali sempre.
- Aggiungi solo le squadre con notizie rilevanti.
