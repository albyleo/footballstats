# Premium Analytics — anteprima gratuita

La pagina `/premium` offre analisi descrittive su dati già archiviati. Durante l'anteprima è accessibile a tutti: non sono attivi abbonamenti, pagamenti o autenticazione Premium.

## Funzioni

1. **Casa / trasferta:** medie separate per campo, con copertura esplicita, per xG, gol, tiri e altre metriche disponibili. Gol subiti e tiri concessi sono disponibili per le squadre.
2. **Schede squadra e giocatore:** grafico partita per partita, medie mobili 5/10 e confronto con la stagione caricata. I giocatori sono distinti anche per squadra e stagione.
3. **Confronto diretto:** due profili dello stesso campionato e stagione, con gli stessi filtri. Avversari, minuti e numerosità dei campioni possono differire; non è una correzione per difficoltà del calendario.
4. **Qualità dei tiri:** xG per tiro, percentuale di tiri in porta e, per le squadre, xG per tiro concesso.
5. **Frequenza e variabilità:** frequenza storica sopra una soglia inclusiva, mediana, deviazione standard descrittiva e intervallo osservato.
6. **Prossimo incontro:** confronto descrittivo automatico fra la squadra di casa e l'ospite del calendario salvato. Affianca tiri in porta, tiri totali, gol e xG prodotti e concessi, in entrambe le direzioni, con media del campionato e copertura. Mostra le frequenze storiche dei gol segnati (0–5 e 6+), senza stimare probabilità future o selezionare intervalli consigliati.

I risultati e le serie dei due profili sono esportabili in Excel.
L'esportazione comprende anche il confronto del prossimo incontro e il relativo campione.

Le schede squadra e il confronto mostrano anche il prossimo avversario in campionato, la data e il campo, come l'esploratore standard. Il calendario salvato copre attualmente i cinque principali campionati; non include coppe. Le partite sono selezionate tra quelle non concluse nel calendario acquisito, dalla data odierna UTC in avanti. L'orario non viene pubblicato perché il fuso della fonte non è garantito. Le variazioni e gli esiti della giornata saranno recepiti al successivo aggiornamento del calendario: non è un servizio live. Il job importa il calendario nei metadati JSONB anche quando le statistiche delle partite restano identiche; non serve una migrazione SQL.

## Calcoli e dati mancanti

- Le medie per partita usano soltanto osservazioni con metrica disponibile; zero è un valore valido. Ogni riepilogo mostra il numero di osservazioni valide rispetto a quelle caricate.
- Per i giocatori, la media per 90 minuti è `90 × somma della metrica / somma dei minuti`, usando solo presenze con metrica e minuti validi. Mediana e dispersione si riferiscono invece ai valori per 90 delle singole presenze.
- I rapporti usano le somme di numeratore e denominatore sulle stesse partite, con entrambi i dati disponibili e denominatore positivo. Non sono medie semplici dei rapporti per partita.
- Le medie mobili includono la partita mostrata e richiedono esattamente 5 o 10 osservazioni consecutive complete. Un dato mancante lascia un vuoto. Le schede riepilogative “ultime 5/10” possono contenere meno osservazioni: il conteggio lo segnala.
- Il filtro casa/trasferta precede la selezione delle ultime N osservazioni. Il riferimento stagionale mantiene tutta la stagione caricata nello stesso campo; le due schede casa/trasferta mantengono l'intera stagione indipendentemente dal filtro ultime N.
- Il campo sconosciuto non viene indovinato: resta nel totale generale ed è escluso dai confronti per campo.
- La frequenza è `osservazioni valide con valore ≥ soglia / osservazioni valide`. È una descrizione del campione, non una probabilità prevista.
- I tiri concessi sono ricavati dai tiri dell'avversario solo quando sono presenti le due squadre della stessa partita nella stessa fonte.
- I tiri in porta subiti corrispondono ai tiri in porta dell'avversario nella stessa partita e fonte. Sono distinti dai tiri totali concessi: descrivono i tentativi nello specchio, non tutti i tentativi. Senza una coppia univoca di squadre o senza il dato avversario il valore resta mancante; zero viene conservato.

La stagione in archivio può essere incompleta. Queste analisi non costituiscono un dataset pre-partita: le medie mobili includono l'incontro corrente. Per addestrare modelli previsionali serviranno variabili calcolate esclusivamente prima del calcio d'inizio e una validazione temporale.

### Campione del prossimo incontro

Il modulo usa le partite in casa della squadra di casa e quelle in trasferta dell'ospite, nello stesso campionato e stagione. Il periodo seleziona tutta la stagione caricata oppure le ultime 5/10 partite **per quel campo**; i filtri Statistica, Campo e Normalizzazione della scheda non modificano questo confronto. Se una squadra ha meno di cinque gare nel campo richiesto, il suo campione viene ampliato alle gare in casa e in trasferta della stessa stagione, applicando poi il periodo selezionato. Il tipo di campione è indicato per ogni squadra, anche in Excel. Sono gare contro tutti gli avversari di campionato, non solo scontri diretti. La finestra viene scelta prima di escludere le metriche mancanti.

Sono ammesse solo date anteriori alla giornata corrente UTC e alla partita in calendario. In assenza di orari verificati, si escludono tutte le osservazioni della giornata corrente. Per ciascuna metrica, la media di riferimento usa tutta la stagione caricata del campionato nello stesso ambito del campione (campo specifico oppure casa + trasferta), indipendentemente dal filtro ultime 5/10. Lo scarto è la media della squadra meno questa media: non è corretto per la forza degli avversari, le assenze o le formazioni.

Zero gol è un dato valido; i gol mancanti sono esclusi dal denominatore delle frequenze. Si mostrano date e numerosità dei campioni; con meno di cinque partite compare un avviso. Se il calendario o la storia dell'avversario non sono disponibili, il modulo lo segnala senza inventare valori. Le frequenze e gli scarti sono descrittivi e non costituiscono un modello validato di forecasting.

Il modulo riutilizza le osservazioni e il calendario già salvati: non richiede nuove colonne, migrazioni SQL o un'importazione aggiuntiva per attivarlo. Segue gli aggiornamenti dell'archivio tramite la revisione della cache esistente.

### Indicatori aggiuntivi e disponibilità della rosa

Il confronto include gol nel primo tempo e corner prodotti/concessi, ricavati dalle due squadre della stessa partita e fonte prima della riconciliazione. Mostra inoltre falli commessi e gialli per partita, tiri nello specchio in percentuale, xG per tiro, xG per tiro concesso, partite senza subire gol e partite senza segnare. Rapporti e conteggi mantengono la propria copertura; un dato mancante non diventa zero.

Il rendimento recente usa sempre le ultime cinque partite caricate, casa e trasferta insieme: risultati e punti per partita sono calcolati solo con entrambi i punteggi disponibili. La continuità della formazione usa la base degli undici con più titolarità nell'intera stagione caricata, indipendentemente dal periodo scelto. Il conteggio delle partite negli ultimi 14 giorni e la distanza fra ultima gara caricata e prossimo incontro riguardano solo il campionato: non comprendono coppe o nazionali e non misurano giorni effettivi di riposo o fatica.

Le assenze sono segnalazioni del feed per uno specifico incontro, distinte in infortunio, squalifica o indisponibilità. Mostrano fonte e data di acquisizione. Dopo 48 ore sono etichettate **da riconfermare**; un elenco vuoto significa soltanto che il feed non segnala assenze, non che l'intera rosa sia disponibile. Nessuna assenza viene dedotta da una mancata presenza o da una formazione passata, e non viene assegnato un punteggio di forma fisica. Il confronto con la base titolare richiede lo stesso identificativo giocatore e la stessa fonte; non abbina persone solo per nome.

L'acquisizione attuale interroga le partite dei prossimi sette giorni di Superliga e Premiership scozzese con gli include Sportmonks `sidelined.player`, `sidelined.type` e `sidelined.sideline`. Per le altre competizioni il modulo segnala la copertura mancante. La documentazione degli [include sulle formazioni e assenze](https://docs.sportmonks.com/v3/tutorials-and-guides/tutorials/lineups-and-formations) descrive il dato di origine.

Il job esistente acquisisce al massimo due pagine, usando lo stesso budget giornaliero Sportmonks e lo stesso blocco dei download. Risposte recenti vengono riutilizzate per 24 ore; in caso di errore conserva l'ultimo elenco e segnala il problema nel riepilogo del job, senza impedire l'importazione delle statistiche. Il file normalizzato viene salvato nella cache persistente; assenze e calendario passano nei metadati JSONB dello snapshot Supabase. Anche una modifica delle sole assenze aggiorna la revisione del dataset.

Per acquisire manualmente questi metadati nell'ambiente locale:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_availability.py --max-requests 2
```

Il comando usa la cache delle richieste quando disponibile. Per pubblicare anche i nuovi dati dopo il push, eseguire il workflow **Update football archive** oppure attendere la prossima esecuzione programmata: il job ripristina la cache persistente, aggiorna le fonti e importa lo snapshot. Non sono necessarie nuove chiavi o migrazioni SQL.

## Architettura e rilascio

L'endpoint di sola lettura `/api/premium/report` calcola le analisi dall'archivio locale o dallo snapshot PostgreSQL configurato. Navigazione e aggiornamento della pagina non chiamano i provider. La cache del report usa la revisione dei dati e supporta ETag.

I campi casa/trasferta e avversario sono salvati nelle osservazioni JSONB esistenti: l'importazione non richiede nuove colonne SQL. Dopo aver aggiornato il codice, eseguire l'importatore dei dati locali per aggiornare le osservazioni già presenti su Supabase.

`FOOTBALL_PREMIUM_MODE=open` è il valore predefinito. Qualsiasi altro valore blocca l'endpoint Premium con HTTP 403. È un interruttore globale, non un sistema di autorizzazione per abbonati. Il rilascio a pagamento richiederà autenticazione, verifica server degli abbonamenti e gestione degli eventi di pagamento.
