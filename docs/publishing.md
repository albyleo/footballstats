# GitHub e pubblicazione: stato e prossimi passaggi

Il codice può essere versionato su GitHub. GitHub Pages pubblica contenuti
statici e non esegue questo backend Starlette/Python: caricare un repository
non rende automaticamente disponibile la dashboard online.

Al momento Supabase non è collegato, non ci sono migrazioni SQL da eseguire e
non è stato creato alcun processo pianificato. La cartella originale non aveva
un repository Git o un remote; nessun push è stato effettuato durante questa verifica.

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
