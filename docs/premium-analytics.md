# Premium Analytics — anteprima gratuita

La pagina `/premium` offre analisi descrittive su dati già archiviati. Durante l'anteprima è accessibile a tutti: non sono attivi abbonamenti, pagamenti o autenticazione Premium.

## Funzioni

1. **Casa / trasferta:** medie separate per campo, con copertura esplicita, per xG, gol, tiri e altre metriche disponibili. Gol subiti e tiri concessi sono disponibili per le squadre.
2. **Schede squadra e giocatore:** grafico partita per partita, medie mobili 5/10 e confronto con la stagione caricata. I giocatori sono distinti anche per squadra e stagione.
3. **Confronto diretto:** due profili dello stesso campionato e stagione, con gli stessi filtri. Avversari, minuti e numerosità dei campioni possono differire; non è una correzione per difficoltà del calendario.
4. **Qualità dei tiri:** xG per tiro, percentuale di tiri in porta e, per le squadre, xG per tiro concesso.
5. **Frequenza e variabilità:** frequenza storica sopra una soglia inclusiva, mediana, deviazione standard descrittiva e intervallo osservato.

I risultati e le serie dei due profili sono esportabili in Excel.

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

## Architettura e rilascio

L'endpoint di sola lettura `/api/premium/report` calcola le analisi dall'archivio locale o dallo snapshot PostgreSQL configurato. Navigazione e aggiornamento della pagina non chiamano i provider. La cache del report usa la revisione dei dati e supporta ETag.

I campi casa/trasferta e avversario sono salvati nelle osservazioni JSONB esistenti: l'importazione non richiede nuove colonne SQL. Dopo aver aggiornato il codice, eseguire l'importatore dei dati locali per aggiornare le osservazioni già presenti su Supabase.

`FOOTBALL_PREMIUM_MODE=open` è il valore predefinito. Qualsiasi altro valore blocca l'endpoint Premium con HTTP 403. È un interruttore globale, non un sistema di autorizzazione per abbonati. Il rilascio a pagamento richiederà autenticazione, verifica server degli abbonamenti e gestione degli eventi di pagamento.
