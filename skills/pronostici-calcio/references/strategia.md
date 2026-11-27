# Strategia: come sceglie le giocate uno scommettitore esperto

Queste regole decidono **quali** giocate entrano nelle schedine. I numeri vengono da `pronostici.py`; le regole li filtrano.

1. **Il mercato ne sa più di noi.** La probabilità di partenza è quella delle quote senza margine (90%), il modello pesa solo il 10%. Dove modello e mercato divergono di almeno 8 punti, la partita resta fuori.
2. **Mai contro il movimento delle quote.** Il report mostra come sono cambiate le probabilità dall'apertura a ora (`Movimento quote`, dati ESPN). Una giocata il cui lato ha perso più di 2 punti percentuali si scarta. Un calo grande, oltre 10 punti, segnala quasi sempre una notizia, come turnover o un infortunio: togli tutta la partita finché non la trovi.
3. **Poche partite, quote vere.** A parità di quota totale, meno giocate vuol dire meno margini del bookmaker che si sommano. Preferisci gli 1X2 e i totali, che hanno margini bassi, ai mercati speciali, che li hanno alti.
4. **Gioca dopo le formazioni.** Una multipla va piazzata prima che inizi la prima partita: costruiscila con partite che iniziano alla stessa ora e giocala nell'ora prima del fischio d'inizio.
5. **Confronta i bookmaker.** Gioca la selezione dove è pagata di più. Se il tuo book paga meno della quota stimata, scartala.
6. **Puntata fissa e piccola.** Punta l'1-2% del budget sulla schedina facile e meno sulle altre. Non rincorrere le perdite.
7. **Tieni il conto.** Annota ogni giocata: la quota presa, quella alla chiusura e l'esito. Se prendi spesso quote migliori della chiusura (CLV positivo) stai giocando bene, anche quando perdi.
8. **Nel live, riparti dalla partenza.** Aggiorna le probabilità pre-partita solo con minuto, punteggio ed espulsioni. Non correggerle con le statistiche di un solo tempo, come tiri e possesso. Nel test del 26/11 le previsioni all'intervallo corrette con i tiri in porta ne hanno prese 5 su 13 contro 8,6 attese: le squadre che avevano dominato il primo tempo hanno perso o subito la rimonta.

Promemoria onesto: nessuna schedina è sicura e tutte hanno un valore atteso negativo, a meno di trovare quote migliori di quelle eque. La schedina facile vince spesso ma paga poco.
