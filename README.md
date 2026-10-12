# MyCombo srl — Football Analytics

Dashboard descrittiva per squadre e giocatori, con archivio locale o PostgreSQL/Supabase. Backend Python con Starlette e Uvicorn; frontend HTML/CSS/JavaScript e GSAP/ScrollTrigger serviti dal progetto.

## Avvio locale

Aprire il terminale **nella cartella del repository clonato**, quindi:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\webapp.py --port 8078
```

Su macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/webapp.py --port 8078
```

Aprire `http://localhost:8078/` per la presentazione, `/providers` per l'esploratore e `/documentation` per copertura e metodologia. Localhost indica il computer che avvia il server, non un host pubblico.

Una nuova installazione parte senza dati reali: JSON/CSV scaricati, database e credenziali non sono inclusi nel repository. Consultare l'archivio locale non richiede token e non avvia download. Usare un ambiente virtuale dedicato.

## Funzionalità

- Viste separate per giocatori e squadre; filtri per campionato, stagione, squadra e ultime partite/presenze caricate.
- Gol, assist, tiri, cartellini, falli e corner dove disponibili.
- Gol subiti e gol del primo tempo per le squadre.
- xG, xA, npxG e altre metriche avanzate con copertura esplicita.
- Posizioni di classifica fornite dai feed, senza ricostruzioni da campioni parziali.
- Base titolare stagionale e confronto con l'ultima formazione acquisita.
- Esportazione delle tabelle in Excel.

I valori mancanti sono indicati con “—”, mai sostituiti con zero. Totali e medie si riferiscono ai dati osservati; i valori per 90 minuti usano soltanto i minuti associati alla metrica. Gli xG descrivono le occasioni osservate e non sono previsioni del prossimo risultato. La continuità della formazione non misura la forma fisica; infortuni e squalifiche non sono acquisiti.

## Fonti e copertura

| Fonte | Utilizzo |
|---|---|
| Sportmonks | Partite, statistiche, formazioni e classifiche dei campionati accessibili al piano |
| football-data.org | Classifiche generali dei sei campionati europei configurati |
| football-data.co.uk | Risultati e statistiche di squadra da CSV |
| Understat | Statistiche individuali, tiri e metriche attese per i campionati supportati |
| API-Football | Client CLI disponibile; risposte non normalizzate nella dashboard |

Una chiave non garantisce accesso a tutte le stagioni o metriche. Date e copertura effettiva sono mostrate nell'applicazione. Football data provided by [football-data.org](https://www.football-data.org/).

## Configurazione privata

Usare `.env.example` come riferimento per creare un `.env` locale, escluso da Git. Non pubblicare `.env`, `.env.supabase`, password o token.

Variabili del processo di acquisizione:

```dotenv
API_FOOTBALL_KEY=
SPORTMONKS_TOKEN=
FOOTBALL_DATA_ORG=
FOOTBALL_IMPORT_DATABASE_URL=
```

`FOOTBALL_ADMIN_DATABASE_URL` serve solo per il setup amministrativo. Sul backend web in produzione configurare la modalità di archiviazione e la connessione dell'utente PostgreSQL di sola lettura:

```dotenv
FOOTBALL_STORAGE=supabase
FOOTBALL_DATABASE_URL=
```

Le chiavi dei feed e le connessioni privilegiate vanno nei Secrets del job, non nel frontend. Gli esempi di connessione nelle guide sono segnaposto.

## Archivio, cache e aggiornamenti

```text
Job di acquisizione → cache persistente → normalizzazione → Supabase
                                                              ↓
Visitatori → backend in sola lettura → cache report → archivio
```

La navigazione e “Rileggi archivio” non chiamano i provider. La cache di lettura accelera le risposte: la sua scadenza non elimina i dati da PostgreSQL.

Il workflow `Update football archive` è configurato per martedì e venerdì alle 07:15 Europe/Rome. Usa un blocco PostgreSQL contro esecuzioni simultanee, budget condivisi e cache persistente. Aggiorna le osservazioni per partita quando cambiano; le classifiche sono conservate nei metadati.

Dopo la configurazione Supabase, dalla cartella del repository:

```powershell
# Importa i dati locali senza scaricare dai provider.
.\.venv\Scripts\python.exe scripts\supabase_data.py import

# Verifica/importa la cache persistente senza richieste ai feed.
.\.venv\Scripts\python.exe scripts\scheduled_sync.py --cached-only

# Aggiorna le classifiche: può consumare quota se la cache è scaduta.
.\.venv\Scripts\python.exe scripts\scheduled_sync.py --standings-only
```

Per acquisizioni coordinate usare il job: i vecchi downloader standalone non condividono tutti i suoi controlli. Vedere la [guida agli aggiornamenti automatici](docs/automatic-updates.md).

## Pubblicazione

Vercel carica l'app ASGI `src.webapp:app`, configurata in `pyproject.toml`. Versionare `uv.lock`; il server MCP `src/server.py` non è l'entrypoint web. Collegare il repository a Vercel e configurare la connessione reader. Gli aggiornamenti dei dati su Supabase non richiedono un nuovo deploy.

- [Configurazione Supabase](docs/supabase-setup.md)
- [Pubblicazione su GitHub e Vercel](docs/publishing.md)
- [Workflow, cache e budget](docs/automatic-updates.md)
- [Metriche attese](docs/expected-metrics.md)
- [Copertura e riconciliazione Understat](docs/understat-coverage.md)
- [Strumenti MCP locali opzionali](docs/mcp.md)

## Test

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s scripts -p "test_*.py"
```

I test usano risposte simulate per le acquisizioni. Verificano normalizzazione, valori mancanti, classifiche, cache, budget, archivio ed esportazione Excel.
