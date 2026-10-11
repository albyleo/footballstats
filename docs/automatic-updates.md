# Aggiornamento automatico

Il workflow `.github/workflows/football-sync.yml` gira martedì e venerdì
alle 07:15 Europe/Rome (gestione automatica ora legale). GitHub può ritardare
o perdere esecuzioni pianificate; sui repository pubblici lo schedule viene
disabilitato dopo 60 giorni senza attività. Non è un servizio real-time.

## Configurazione una tantum

1. Applicare `supabase/migrations/202610110002_sync_jobs.sql` come amministratore.
2. Dal checkout con i dati acquisiti: `python scripts/scheduled_sync.py --seed-cache`.
3. Nei repository Actions secrets aggiungere `FOOTBALL_IMPORT_DATABASE_URL`
   (importer, Session pooler, porta 5432, TLS), `SPORTMONKS_TOKEN` e `FOOTBALL_DATA_ORG`.
   Non usare le credenziali amministrative nel workflow.
4. Pubblicare codice e workflow sul branch predefinito `main`.
5. Actions > Update football archive > Run workflow. Selezionare
   `cached_only` per una prova senza richieste ai feed.

Non serve un processo sul PC. Il sito Vercel non deve essere ridistribuito
dopo ogni importazione e i visitatori non eseguono download dai provider.

## Flusso

- Cache compressa dei file in `football.sync_cache`, accessibile solo
  all'importer; nessun token o URL autenticato memorizzato.
- Stato, budget giornalieri UTC e cooldown in `football.sync_control`.
- Advisory lock PostgreSQL per tutta l'acquisizione/import e concurrency
  GitHub senza cancellare una run in corso. Anche l'importatore manuale usa
  la stessa chiave di lock. I vecchi downloader standalone non partecipano
  al budget del job: usare `scheduled_sync.py` per le acquisizioni coordinate.
- Cinque cataloghi Understat della stagione luglio-giugno; i dettagli vengono
  scaricati se mancanti, oppure ricontrollati per le partite degli ultimi
  sette giorni. La cache JSON Understat ha una freschezza minima di 24 ore.
- Sei CSV della stagione, salvati solo se il contenuto cambia.
- Sportmonks: catalogo e partite concluse di Superliga/Premiership negli ultimi
  sette giorni, estesi all'ultima acquisizione riuscita in caso di interruzione.
  Oltre 99 giorni di interruzione occorre un recupero manuale a finestre.
- API-Football non viene interrogata: l'account risultava sospeso.
- football-data.org: sei classifiche correnti (SA, PL, PD, BL1, FL1, PPL),
  autenticazione X-Auth-Token da `FOOTBALL_DATA_ORG`. Una richiesta per
  campionato, cache 24 ore, almeno 7 secondi tra richieste e tetto condiviso
  12 al giorno. Con due esecuzioni settimanali normali: 12 chiamate/settimana.
  Si accetta solo una tabella TOTAL/REGULAR_SEASON della stagione prevista;
  le posizioni non vengono ricalcolate. Nomi equivalenti espliciti e verificati,
  mai fuzzy matching. Classifiche conservate per stagione in Supabase.
  Questa chiave serve sul job, non su Vercel. Nessuna nuova migrazione SQL.
- Pausa minima di tre secondi fra richieste; niente retry automatici.
- Budget massimo giornaliero condiviso: Understat 250, CSV 6, Sportmonks 20.
  Sono tetti, non obiettivi di consumo. Anche richieste fallite consumano budget.
- HTTP 403/429/503 interrompono il processo e registrano una pausa persistente,
  rispettando Retry-After (minimo un'ora; default sei ore). Gli altri errori
  interrompono la run senza retry. Il budget limita anche i rilanci manuali.
- Understat: 401/403 e risposte JSON non valide/incomplete impostano anche
  `blocked:understat=true` su Supabase. Nessuna nuova acquisizione di rete
  viene tentata finché un amministratore non verifica la causa e rimuove il
  blocco. User-Agent identificativo `MyComboDataSync/1.0`; nessun CAPTCHA,
  proxy o rotazione di IP. Queste misure non garantiscono l'accesso futuro.
  Usare questo job per le acquisizioni: il vecchio downloader manuale non
  condivide lo stato di blocco e il budget Supabase.
- Il CSV `P1` (Primeira Liga) è incluso nella cache e nel job. Fornisce solo
  statistiche di squadra, non osservazioni sui singoli giocatori.
- Classifiche: il job scarica anche `/standings/seasons/{id}` per le stagioni
  correnti di Superliga e Premiership (massimo due chiamate aggiuntive, nello
  stesso budget Sportmonks). Cache 24 ore, file `standings-<id>.json`, copie
  persistenti in sync_cache e dataset_state.metadata.standings. Una variazione
  di classifica aggiorna la revisione anche senza modifiche alle partite.
  `--standings-only` aggiorna soltanto queste risposte e importa l'archivio
  locale ripristinato, senza download Understat/CSV e senza avanzare last_success
  dell'acquisizione completa. La vista usa posizione, campionato, stagione e
  squadra del provider; nessun ricalcolo sui filtri. Dati assenti o più fasi
  ambigue danno “—”, mai una classifica stimata. Nessuna migrazione SQL richiesta.

## Solo dati cambiati

L'importatore confronta i payload normalizzati per partita, ignorando
`fetched_at` e l'ordine delle righe. Sostituisce solo partite nuove o modificate,
compresa la rimozione di osservazioni individuali precedentemente presenti.
Le partite non contenute nell'import sono conservate. Se non ci sono modifiche
e il catalogo è uguale, non scrive statistiche e non incrementa la revisione.
Un cambio di catalogo può incrementarla anche senza nuove osservazioni.
Lo stato operativo dell'ultimo controllo viene comunque registrato.

La cache contiene le risposte originali necessarie a ricostruire l'archivio.
Una run incompleta non pubblica il nuovo snapshot; mantiene i file scaricati
per la successiva esecuzione. Risultati vecchi corretti oltre sette giorni non
vengono ricontrollati automaticamente. `--seed-cache` inizializza la cache dai
file locali: non pianificarlo nel workflow e non usarlo con copie obsolete.

La stagione parte automaticamente dall'anno corrente a luglio. Se un nuovo
catalogo non è ancora disponibile, la run fallisce e l'archivio rimane valido.
La cache cresce nel tempo: verificare periodicamente spazio Supabase e retention.

## Diagnostica (SQL Editor Supabase)

```sql
select name, value from football.sync_control
where name in ('last_run', 'last_success');

select name, value from football.sync_control
where name like 'budget:%' or name like 'cooldown:%' or name like 'blocked:%'
order by name desc;

select count(*) as files, sum(octet_length(payload)) as compressed_bytes
from football.sync_cache;
```

La run ha timeout di 30 minuti. Le credenziali non sono stampate nei log.
Il file workflow richiede solo `contents: read`; non effettua commit o push.
Su GitHub pubblico i runner standard sono gratuiti, nei limiti delle policy
del servizio. Fonti: https://docs.github.com/en/billing/concepts/product-billing/github-actions
e https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
