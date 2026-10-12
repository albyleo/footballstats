# Collegamento iniziale a Supabase

Guida generica: usare il proprio progetto Supabase. Identificativi, host e
password negli esempi sono segnaposto. Se il progetto è già configurato,
non rigenerare le credenziali; verificare lo stato prima di ripetere il setup.

## 1. Creare lo schema

Aprire il progetto Supabase → **SQL Editor → New query**. Copiare tutto il file
`supabase/migrations/202610100001_football.sql` e premere **Run**.
La migrazione crea uno schema privato `football`, le tabelle e due utenti
inizialmente senza password. Non elimina dati. Nel Table Editor selezionare
lo schema `football` per vedere le tabelle (inizialmente vuote).

Non aggiungere `football` agli schemi esposti dalla Data API: il backend usa
PostgreSQL direttamente. RLS è attiva e non ci sono permessi anon/authenticated.
Per ora applicare la migrazione dal SQL Editor; non attivare contemporaneamente
un deploy automatico delle migrazioni GitHub. Manca ancora la configurazione CLI
per gestirne la cronologia: collegare il repo non sostituisce questo passaggio.

## 2. Configurare la connessione amministrativa soltanto in locale

Supabase → **Connect → Session pooler** (porta 5432). Copiare l'URI PostgreSQL.
Nel `.env` locale del progetto aggiungere:

```dotenv
FOOTBALL_ADMIN_DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
```

Prendere PROJECT_REF e POOLER_HOST dalla dashboard. Sostituire PASSWORD con la
password del database, codificando i caratteri speciali per un URL. Non usare
le API key anon/service_role: sono credenziali diverse. Non incollare questa
connessione in chat o su GitHub; non metterla su Vercel.

## 3. Generare credenziali separate e importare

Dalla cartella del progetto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\supabase_data.py dry-run
.\.venv\Scripts\python.exe scripts\supabase_data.py provision
.\.venv\Scripts\python.exe scripts\supabase_data.py import
.\.venv\Scripts\python.exe scripts\supabase_data.py check
```

`provision` imposta password casuali per `football_reader` e `football_importer`
e salva le connessioni in **`.env.supabase`**, escluso da Git. Non le stampa.
Se il file esiste, non sovrascrive o ruota le password. Non eseguirlo nuovamente
su un progetto già configurato senza pianificare la rotazione.

L'importazione legge i file esistenti: **zero richieste ai feed**. Ogni partita
importata sostituisce le proprie osservazioni nella stessa transazione; ripetere
l'importazione non duplica le righe. Le altre partite/stagioni sono conservate.
Non vengono conservati nel database tutti i payload API originali: vengono
importate le osservazioni normalizzate, con provenienza, valori mancanti e audit HT.
I file originali rimangono disponibili sul PC per gli audit.

## 4. Collegare Vercel

Vercel → footballstats → **Settings → Environment Variables**, ambiente Production:

| Nome | Valore |
|---|---|
| `FOOTBALL_STORAGE` | `supabase` |
| `FOOTBALL_DATABASE_URL` | Valore omonimo del file locale `.env.supabase` |

La connessione reader usa il Transaction pooler (6543); il driver disabilita le
prepared statements. Le operazioni di importazione usano Session pooler (5432).
Non caricare su Vercel il file intero, l'URL admin/importer o le chiavi dei feed.
Usare Preview solo se si vuole esplicitamente che le anteprime leggano questo
stesso archivio. Dopo aver caricato il codice aggiornato, fare un nuovo deploy.

Il backend mantiene uno snapshot consistente del database per 60 secondi per
istanza, più la cache delle risposte già presente. Nuovi import sono visibili
entro circa 60 secondi. Non scarica dai feed se il database è vuoto o indisponibile:
in caso di errore restituisce 503, senza mostrare falsamente zero partite.
Questa prima versione legge tutte le osservazioni normalizzate: è adatta al
campione attuale; archivi estesi richiederanno aggregazioni SQL e paginazione.

## Stato della quota dei feed

Nessuno scheduler è attivo. La dashboard non possiede i token dei feed.
L'importatore trasferisce dati già presenti e non usa il downloader. Il budget
globale e il lock distribuito dei download sono il passaggio successivo, da
collegare al downloader prima di attivare qualsiasi acquisizione automatica.
Il `--max-requests` attuale resta per singola esecuzione: non eseguire più copie
del downloader pensando che esista già un limite globale.

Fonti: [Supabase connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Psycopg prepared statements](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html).
