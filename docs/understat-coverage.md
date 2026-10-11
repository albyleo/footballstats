# Copertura Understat

L'acquisizione manuale usa gli endpoint JSON pubblici utilizzati dal sito
[Understat](https://understat.com/). Non richiede le chiavi Sportmonks o
API-Football. Non è un'API contrattuale con disponibilità garantita: formato,
accessibilità e copertura possono cambiare.

```powershell
.\.venv\Scripts\python.exe scripts\fetch_understat.py --season 2026 --max-requests 10
```

Una richiesta per elenco campionato, una per partita non ancora salvata.
Cache su disco, scrittura atomica, nessun retry automatico, richieste distanziate
di un secondo. Al raggiungimento del budget si interrompe; ripetere il comando
riusa i file già scaricati. Per aggiornare gli elenchi usare `--refresh-leagues`;
`--refresh-matches` riscarica esplicitamente anche i dettagli già presenti e
serve per correzioni del provider. Il budget è **per esecuzione**, non condiviso.
Nessuno scheduler è stato attivato. Il sito non importa questo downloader.

I file restano sotto `data/providers/understat/`, esclusi da Git e Vercel.
Contengono URL di origine, istante di acquisizione e risposta originale.

## Definizioni e controlli

- I giocatori provengono dai roster **per partita**, non dai totali stagionali.
- Minuti, gol, assist, gialli e tiri sono i campi espliciti del roster.
- Tiri in porta: conteggio degli eventi `Goal` e `SavedShot`, solo se la lista
  completa dei tiri coincide con il totale dichiarato del giocatore e tutti
  gli esiti sono riconosciuti. In caso contrario il dato è assente.
- Falli individuali, indisponibilità e infortuni non vengono inventati.
- Understat non alimenta i gol del primo tempo: il minuto da solo non permette
  di identificare con certezza il periodo nel recupero. Restano i valori
  `HTHG/HTAG` dei CSV, dove disponibili.
- Se i gol individuali e gli autogol non riconciliano il risultato finale,
  **tutti i giocatori di quella partita vengono esclusi**. La partita conserva
  il risultato dell'elenco, e un avviso visibile spiega l'esclusione.

L'archivio PostgreSQL conserva le osservazioni distinte per provider, inclusi
gli originali CSV. Il report riconcilia una sola volta la stessa partita
usando campionato, stagione, data, entrambe le squadre e risultato finale.
Le equivalenze dei nomi sono esplicite, senza similarità automatica. I campi
CSV integrano quelli Understat, mantenendo la provenienza. In caso di conflitto
FT resta il CSV e viene esclusa la partita Understat con un avviso.
Chi analizza direttamente le tabelle sorgente non deve sommare due provider:
usare `understat_stats.merge_sources` per ottenere lo stesso campione del sito.

## Verifica dell'11 ottobre 2026

| Campionato | Partite | Partite con giocatori | Giocatori con minuti | Partite con HT |
|---|---:|---:|---:|---:|
| Serie A | 53 | 53 | 452 | 50 |
| Premier League | 56 | 56 | 430 | 50 |
| La Liga | 73 | 72 | 465 | 69 |

Ultima partita presente nei tre elenchi: **10 ottobre 2026**. Questo non
significa che ogni metrica sia aggiornata a quella data: HT, falli e corner
dei CSV restano al 20 settembre. Copertura per metrica mostrata nel sito.

Partita Understat `30804`, Villarreal–Deportivo La Coruna: dati individuali
esclusi per incoerenza con il risultato. Nessuna correzione numerica ipotizzata.
Il campione complessivo riconciliato conta 283 partite, inclusa la copertura
Sportmonks preesistente; le tabelle grezze contengono più righe per le fonti
sovrapposte. Nessun abbonamento o nuova chiave necessari per questa acquisizione.

Dopo la pubblicazione del backend con la riconciliazione delle fonti:

```powershell
.\.venv\Scripts\python.exe scripts\supabase_data.py dry-run
.\.venv\Scripts\python.exe scripts\supabase_data.py import
```

L'importazione salva osservazioni persistenti, non una cache che scade.
Non importare queste fonti nel vecchio backend senza riconciliazione: mostrerebbe
le stesse partite due volte.
