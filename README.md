# Football — osservatorio descrittivo

Dashboard Python con Starlette + Uvicorn e frontend HTML/CSS/JavaScript senza
build o CDN. Mostra statistiche salvate di squadre e giocatori, copertura dei
campi, risultati recenti e verifica dei gol del primo tempo.

## Avvio

```powershell
cd C:\Users\alber\Desktop\foootbalMCP
.\.venv\Scripts\python.exe src\webapp.py --port 8078
```

Aprire http://127.0.0.1:8078/ oppure `/providers`: entrambe mostrano la dashboard.
Non servono DuckDB, MCP, Supabase o token per consultare i dati già salvati.
Con archivio vuoto il sito mostra zero partite, senza scaricare automaticamente.

Per una nuova installazione usare un ambiente virtuale dedicato:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Non installare le dipendenze nel Python globale, condiviso con altri progetti.

## Dove sono i dati e cosa consuma quota

```
Comando di acquisizione → cache delle risposte → JSON/CSV salvati
                                                ↓
Browser → backend in sola lettura → cache report → statistiche locali
```

| Componente | Funzione attuale |
|---|---|
| `data/providers/sportmonks/match-*.json` | Archivio partite con statistiche di squadra/giocatore |
| `data/providers/*/cache/` | Risposte dei provider riutilizzabili per 24 ore |
| `data/raw/` | CSV football-data.co.uk, statistiche di squadra |
| `src/provider_stats.py` | Normalizzazione e aggregazione; cache del dataset basata sui file |
| `src/report_cache.py` | Risposte JSON pronte, cache condivisa dai visitatori dello stesso processo |
| `football_mvp.duckdb` | Vecchio archivio SQL, solo per MCP locale opzionale |
| Supabase | Backend opzionale: attivare con `FOOTBALL_STORAGE=supabase` dopo il setup |

**Rileggi dati locali non chiama Sportmonks o API-Football.** Anche filtri,
ricerche, paginazione e caricamento iniziale leggono solo il nostro backend.
Il pulsante non aggiorna le partite dal provider e non svuota la cache dei feed.

Le risposte della dashboard sono memorizzate per 60 secondi, con massimo 32
combinazioni di filtri e 8 MiB per processo. La modifica, aggiunta o rimozione
dei file di input (anche lo stato sync) invalida la cache alla richiesta
successiva. Un lock evita calcoli duplicati tra richieste contemporanee nello
stesso processo. ETag e risposte HTTP 304 evitano di ritrasmettere JSON invariati.
`Cache-Control: no-cache` significa *rivalida la copia*, non disattivare la cache.
Non è ancora una cache distribuita tra più server.

Solo `scripts/fetch_provider.py` usa i token e consuma chiamate esterne. Ha una
cache persistente di 24 ore per provider, impronta della credenziale, endpoint e
parametri. Gli hit consumano zero chiamate. `--max-requests` limita le richieste
di **una singola esecuzione**, non è un limite giornaliero globale. Errori e
controlli API-Football `/status` non sono memorizzati. Nessun retry automatico,
polling, cron o aggiornamento collegato alle visite è attivo.

## Acquisizione manuale dei feed

Le credenziali sono in `.env`, escluso da Git:

```dotenv
API_FOOTBALL_KEY=your_direct_api_sports_key
SPORTMONKS_TOKEN=your_sportmonks_token
```

Le variabili d'ambiente esistenti hanno precedenza. Le chiavi RapidAPI non sono
supportate. I token non devono finire nel frontend, nei file pubblici o nei log.

```powershell
# Questi comandi possono consumare quota: non eseguirli ad ogni visita.
.\.venv\Scripts\python.exe scripts\fetch_provider.py api-football check --max-requests 1
.\.venv\Scripts\python.exe scripts\fetch_provider.py sportmonks leagues --max-requests 2
.\.venv\Scripts\python.exe scripts\fetch_provider.py sportmonks sync --from-date 2026-07-24 --to-date 2026-10-10 --max-requests 5
# File gratuiti, senza quota API-Football/Sportmonks; aggiungere --force per aggiornare file esistenti.
.\.venv\Scripts\python.exe scripts\fetch_football_data.py --seasons 2627 --leagues I1 E0 SP1 --retries 1
```

`sync` scarica fino a 50 partite concluse per pagina con statistiche, formazioni,
eventi e periodi. Default: campionati Sportmonks 271 e 501; `--league ID` restringe
la selezione. Intervalli da 1 a 100 giorni. Lo stato in `sync-status.json` indica
chiamate, hit, partite e completezza della paginazione. Un download interrotto
conserva le pagine ricevute e viene segnato incompleto. Gli ID evitano duplicati.
Ripetere lo stesso intervallo entro 24 ore riutilizza le risposte in cache.

Per uso regolare preferire intervalli recenti limitati, con una breve
sovrapposizione per correzioni, anziché riscaricare ogni volta tutta la stagione.
Un intervallo o un insieme di parametri differente genera una chiave cache diversa.

`match --fixture ID` usa tre chiamate con API-Football e una con Sportmonks.
I file API-Football sono archiviati ma **non ancora normalizzati dalla dashboard**.
Gli ID tra provider non sono intercambiabili. Un controllo credenziali riuscito
non dimostra accesso alle stagioni o alle statistiche individuali desiderate.

## Copertura verificata il 10 ottobre 2026

Sportmonks: 101 partite concluse (55 Danimarca, 46 Scozia), 24 squadre e 579
giocatori con minuti. Acquisite in tre chiamate bulk. La copertura restituita
dal provider non è una garanzia indipendente di completezza del campionato.
Le righe per giocatore/squadra possono superare i giocatori distinti dopo trasferimenti.

CSV Serie A, Premier League e La Liga 2026/27: rispettivamente 50, 50 e 69
partite, solo squadre. Questi file arrivano al **20 settembre 2026**, anche se
scaricati il 10 ottobre. Il sito mostra la data dell'ultima partita per fonte.
L'ultima verifica API-Football ha restituito account sospeso; nessun dato di
quel provider è attualmente visibile. Non viene ricontrollato durante la navigazione.

I valori omessi rimangono sconosciuti, mai zeri inventati. Per-90 e medie usano
soltanto le partite con valore osservato: l'omissione degli zeri può sovrastimarle.
La copertura è indicata sotto ogni statistica. Le riserve senza minuti non contano
come presenze; tiri e falli di squadra non vengono ricostruiti sommando dati
individuali incompleti. Infortuni e squalifiche non sono ancora acquisiti.
La continuità dei titolari confronta due formazioni complete di 11 giocatori;
non misura la forma fisica.

## Controllo dei gol del primo tempo

Sportmonks: score type 1 `1ST_HALF`, associato alla squadra, con tipo e descrizione
concordanti. Il confronto con gli eventi usa il periodo 1, includendo il recupero;
considera gol, autogol e rigori segnati non annullati. I delta del punteggio
assegnano gli autogol alla squadra beneficiaria. `CURRENT` e `2ND_HALF` non sono
gol del primo tempo; il secondo è cumulativo. Eventi incompleti sono segnalati
come non verificabili, conflitti HT esclusi dai totali.

Audit dei 101 match: tutti gli HT concordano con gli eventi, inclusi otto gol
nel recupero. Un avviso su FC Midtjylland–Brøndby IF (19713933, 14 settembre):
`2ND_HALF_ONLY` ospite incoerente; HT 2–0 e FT 4–1 concordano con gli eventi.
È un controllo interno alla fonte, non una conferma indipendente.

I CSV usano `HTHG` e `HTAG`, controllati contro il risultato finale; non
contengono eventi per un secondo controllo. Definizioni di tiri e cartellini
possono differire tra fonti e campionati.

```powershell
.\.venv\Scripts\python.exe scripts\audit_half_time.py
```

Definizioni: [Sportmonks Scores](https://docs.sportmonks.com/v3/tutorials-and-guides/tutorials/includes/scores),
[Periods](https://docs.sportmonks.com/v3/tutorials-and-guides/tutorials/includes/periods),
[Football-data.co.uk](https://football-data.co.uk/notes.txt).

## Pubblicazione e Supabase

Il backend PostgreSQL e l'importatore sono ora disponibili. Seguire
[docs/supabase-setup.md](docs/supabase-setup.md) per applicare la migrazione,
creare credenziali separate, importare l'archivio e configurare Vercel.
La modalità predefinita resta locale finché `FOOTBALL_STORAGE=supabase` non
viene impostata. L'11 ottobre 2026 il progetto remoto è stato popolato con
270 partite, 84 squadre e 4.037 osservazioni individuali; accesso reader e
parità dei report verificati. L'attivazione su Vercel richiede le due variabili
descritte nella guida e il deploy del codice aggiornato.
Budget globale e lock dei download rimangono da implementare prima dello scheduler.

Istruzioni per caricare il codice su GitHub, scelta Supabase senza Redis e
procedura di migrazione: [docs/publishing.md](docs/publishing.md).

Supabase/PostgreSQL può diventare l'archivio centrale per partite, squadre,
giocatori, statistiche per partita e registri di acquisizione. I file originali
possono restare come archivio delle fonti per audit. Non basta aggiungere una
chiave: servono schema, importazione e collegamento del backend al database.

Il flusso previsto è **un processo di acquisizione → Supabase → backend/cache →
visitatori**. Il processo aggiorna solo i dati necessari, esegue upsert per
provider/ID e registra consumo/errori. Prima di avviare più processi occorrono
lock condiviso e budget giornaliero persistente, perché i limiti attuali sono
per esecuzione. Il sito serve sempre i dati già acquisiti: mille visite non
devono produrre mille richieste ai feed.

Le chiavi dei provider e quelle privilegiate Supabase restano sul backend.
Eventuali accessi diretti dal browser richiedono permessi di sola lettura e
Row Level Security. Riferimento: [sicurezza dei dati Supabase](https://supabase.com/docs/guides/database/secure-data).
In modalità Supabase il deploy non richiede un volume per i file locali.
È disponibile il workflow GitHub Actions `Update football archive`: martedì e
venerdì alle 07:15 Europe/Rome, attivo quando pubblicato sul branch predefinito.
Usa cache persistente privata, budget giornalieri e lock PostgreSQL. L'import
confronta i dati ed evita scritture/revisioni inutili quando sono invariati.
Setup, limiti e diagnostica: [docs/automatic-updates.md](docs/automatic-updates.md).

## Pulizia e strumenti opzionali

Rimossi dal sito l'esploratore SQL, i relativi file HTML/JS/CSS e gli endpoint
SQL. La home è la dashboard. Rimossa la dipendenza di avvio dal file DuckDB.
Le dipendenze web sono esplicite; quelle MCP sono in `requirements-mcp.txt`.

Conservati i dati scaricati, la cache, le credenziali, i test e gli audit.
`src/server.py`, `db.py`, `schema.py`, `ingest.py`, `scripts/smoke_test.py`,
`.mcp.json`, `data/samples/` e DuckDB sono strumenti locali opzionali, documentati
in [docs/mcp.md](docs/mcp.md). Non vengono caricati dal sito e possono essere
esclusi dal pacchetto web. Il vecchio file di appunti nella root è conservato.

## Test senza consumo di quota

La home `/` presenta MyCombo SRL, con GSAP/ScrollTrigger 3.13.0 serviti
localmente. `/providers` conserva l'osservatorio; i collegamenti dalla home
possono preselezionare la vista giocatori o squadre. Le slide sono orizzontali
su desktop e verticali su mobile; con `prefers-reduced-motion` o JavaScript
disabilitato il contenuto resta leggibile senza animazioni. La vetrina non
interroga il database o i feed.

L'esploratore `/providers` separa Giocatori e Squadre tramite un selettore
esplicito e filtri adattati alla vista. La documentazione dei feed, le schede
di copertura e gli audit HT sono in `/documentation`. I nomi delle fonti
integrative non sono mostrati nel testo pubblico: sono indicati come archivio
integrativo, mantenendo intatti gli identificativi originali nel database e
nelle risposte JSON. Nessun dato integrativo è attribuito alle API configurate.

Serie A, Premier League e La Liga possono ora essere integrate con roster e
statistiche per partita Understat, con cache e budget manuale. Definizioni,
copertura effettiva, riconciliazione CSV e comandi:
[docs/understat-coverage.md](docs/understat-coverage.md).

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s scripts -p test_*.py
```

Coprono download simulati/cache/budget, valori mancanti, periodi e HT,
concorrenza della cache report, invalidazione, ETag, assenza di chiamate esterne
dalla dashboard e avvio senza DuckDB/MCP.
