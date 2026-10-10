# GitHub e pubblicazione: stato e prossimi passaggi

Il codice può essere versionato su GitHub. GitHub Pages pubblica contenuti
statici e non esegue questo backend Starlette/Python: caricare un repository
non rende automaticamente disponibile la dashboard online.

Il collegamento Supabase richiede il setup descritto in
[supabase-setup.md](supabase-setup.md): migrazione SQL, importazione locale e
variabili Vercel. Schema, credenziali separate e importazione remota sono stati
verificati l'11 ottobre 2026; resta da attivare il backend Supabase su Vercel.
Nessun processo pianificato è attivo.

## Pubblicare il codice

Creare un repository GitHub vuoto, poi dalla cartella del progetto:

```powershell
git init
git add .
git status --short
# Verificare che .env, data/providers, CSV scaricati, database, appunti e
# artifacts non compaiano nell'elenco dei file da caricare.
git commit -m "Initial football analytics dashboard"
git branch -M main
# Sostituire con l'URL del proprio repository.
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

Usare Git, che rispetta `.gitignore`, evitando di trascinare tutta la cartella
nel sito GitHub. `.env.example` contiene solo nomi delle variabili, senza valori.
Il repository non include l'archivio scaricato: una nuova installazione parte
vuota finché non vengono importati i dati. Il CSV in `data/samples/` è sintetico
e non viene letto dalla dashboard. I test funzionano senza token e senza feed.

## Scelta per il primo deploy: Supabase senza Redis

### Deploy del backend Python su Vercel

La configurazione `pyproject.toml` indica esplicitamente
`[tool.vercel] entrypoint = "src.webapp:app"`. Il file `src/server.py` è il
server MCP stdio: non è un'app ASGI e non va scelto come entrypoint. Anche
`scripts.test_provider_stats:app`, suggerito dall'autodetection, è errato:
è un modulo di test che importa l'app, non il modulo di produzione.

`.python-version` seleziona Python 3.13. Vercel usa la sezione `[project]` di
`pyproject.toml` per risolvere le dipendenze con uv; deve contenere nome,
versione, versione Python e dipendenze runtime. `requirements.txt` conserva
le stesse dipendenze per l'installazione locale con pip. Non serve convertire il progetto in Node/React o lanciare
Uvicorn nella build: Vercel carica direttamente l'oggetto ASGI.

Versionare anche `uv.lock`, generato con `uv lock`, per fissare le versioni
risolte. Dopo una modifica alle dipendenze aggiornare il lockfile e mantenere
allineato `requirements.txt`.

Nel progetto Vercel importato da GitHub usare:

- Root Directory: `./`
- Framework/Application Preset: `Python`
- Install Command: lasciare il default automatico (rimuovere l'override pip)
- Build Command: lasciare il default / nessun comando personalizzato
- Output Directory: lasciare il default / N/A

Caricare su GitHub i file di configurazione nuovi, poi distribuire il nuovo
commit. Ripetere il deployment del vecchio commit non applica la correzione.
Non configurare `scripts.test_provider_stats:app` nell'interfaccia Vercel.
Nessuna chiave dei feed è necessaria per questo frontend/backend di sola lettura.

`.vercelignore` esclude credenziali locali, ambienti virtuali, test, MCP e dati
locali anche dai caricamenti tramite CLI. `src/static/` rimane nel bundle e
Starlette serve HTML e JavaScript insieme agli endpoint API.

**Stato dei dati:** il primo deploy mostra un archivio vuoto, perché i dati
scaricati non sono su GitHub e Supabase non è ancora collegato. Questo non è
un errore del deploy. Non usare il filesystem della Function come archivio
persistente e non avviare sync durante le richieste web. La cache in memoria è
per istanza e può sparire ai riavvii; budget e lock condivisi saranno in Supabase.

Riferimento: [Vercel Python entrypoints](https://vercel.com/docs/functions/runtimes/python#python-entrypoints).

### Archivio e cache condivisi

Usare PostgreSQL/Supabase come archivio persistente condiviso, conservando la
cache breve nel backend per le letture ripetute. Redis potrà essere valutato
se misure reali mostreranno latenza o carico elevati con più istanze del sito.
Non serve Redis per impedire che un refresh consumi quota dei feed.

Architettura prevista:

```
Processo di acquisizione → provider → dati normalizzati in Supabase
                                         ↓
Visitatori → backend Python → cache → letture Supabase
```

Le ricerche e i refresh non devono chiamare i provider, nemmeno se manca un
dato o scade la cache. In quel caso il sito mostra i dati disponibili e la data
di aggiornamento. Solo il processo di acquisizione possiede le chiavi dei feed.

## Cosa fare in Supabase quando iniziamo il collegamento

1. Creare un progetto Free e scegliere una regione europea vicina all'hosting
   del backend. Conservare la password del database nel proprio gestore password.
2. Comunicare il riferimento/URL del progetto, senza incollare chiavi o password
   in chat. I segreti andranno nelle variabili d'ambiente del servizio che esegue
   il backend e dell'unico processo di acquisizione.
3. Preparare ed eseguire le migrazioni versionate nel repository: partite,
   squadre, giocatori, statistiche per partita, mapping degli ID dei provider,
   stato delle acquisizioni e budget. Conservare provider, data di acquisizione,
   copertura e valori NULL; non identificare giocatori o squadre soltanto dal nome.
4. Importare i file locali già presenti con upsert per provider/ID, senza
   riscaricarli e senza consumare quota. Verificare conteggi, HT e valori mancanti.
5. Collegare le letture della dashboard a Supabase e verificare gli accessi.
   I browser non ricevono chiavi privilegiate; le tabelle operative di quota e
   lock non sono scrivibili dagli utenti. Se si espone la Data API, configurare
   permessi e RLS espliciti. Il backend web usa solo i permessi necessari.
6. Implementare e testare il controllo condiviso descritto sotto. Soltanto dopo
   attivare un unico scheduler, con frequenza stabilita in base alla quota e
   alla freschezza richiesta. Nessuna pianificazione è attiva al momento.

## Budget e aggiornamenti simultanei: requisiti da implementare

- Registro persistente per provider/account e finestra di quota. Il reset deve
  seguire il piano effettivo del provider: non presumere mezzanotte italiana o
  la stessa finestra per entrambi i servizi.
- Prima di **ogni** chiamata, prenotare atomicamente un'unità nel database solo
  se il limite e il margine di riserva lo consentono. Comprendere pagine,
  tentativi, verifiche e retry. Un timeout può avere consumato quota: non
  restituire automaticamente quell'unità al budget.
- Se il database o la prenotazione non sono disponibili, fermare i download.
  Non ripiegare su un contatore locale. Il registro copre solo i client che
  passano da questo controllo: eventuali altri programmi sulla stessa chiave
  richiedono margine e riconciliazione con i dati del provider.
- Lock condiviso con proprietario e scadenza per impedire due acquisizioni
  contemporanee dello stesso feed. Acquisizione/rinnovo/rilascio devono essere
  atomici; un processo che perde il lock deve fermarsi prima della chiamata
  successiva. La durata deve superare il timeout della richiesta in corso.
  Non mantenere una transazione SQL aperta durante una richiesta HTTP.
- Cache condivisa per provider, account, endpoint e parametri canonici, senza
  token nelle chiavi pubblicate. Verificare la cache nuovamente dopo avere
  acquisito il lock. Archiviare i risultati con upsert e registrare l'esito.
- Aggiornare principalmente le partite recenti, con una piccola sovrapposizione
  per correzioni. Conservare i risultati storici; limitare dimensioni e durata
  dei payload duplicati e dei log, per non saturare lo spazio gratuito.
- Test con più processi: una sola acquisizione per lo stesso lavoro, nessun
  superamento del budget per chiamate concorrenti, recupero da crash, stop su
  errore database, nessuna acquisizione causata da refresh o filtri.

La cache attuale di 24 ore e `--max-requests` sono locali/per esecuzione e non
sostituiscono questi controlli. Il sito attuale, invece, è già separato dai
download: i visitatori non causano chiamate ai feed.

## Limiti dei piani verificati il 10 ottobre 2026

Supabase Free dichiara 500 MB di database, 5 GB di egress e pausa dopo una
settimana di inattività. I limiti riguardano Supabase, non le quote dei feed.
Upstash Redis Free dichiara 256 MB e 500.000 comandi mensili: anche letture/cache
hit possono consumare comandi Redis. Non aggiungerlo senza una necessità misurata.

Fonti: [Supabase pricing](https://supabase.com/pricing),
[Upstash Redis pricing](https://upstash.com/pricing/redis),
[GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages),
[Supabase sicurezza](https://supabase.com/docs/guides/database/secure-data).
