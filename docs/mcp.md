# MCP e DuckDB: strumenti locali opzionali

La dashboard non usa DuckDB. Questi strumenti sono conservati per interrogazioni
SQL da un client AI locale e per esperimenti sul vecchio archivio CSV. Non
contengono automaticamente i dati Sportmonks mostrati nel sito.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt
.\.venv\Scripts\python.exe src\ingest.py --no-samples
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

`ingest.py` importa i CSV in `football_mvp.duckdb`; controllare sempre le fonti
effettivamente importate. `data/samples/` contiene risultati sintetici per test,
che non vengono letti dalla dashboard. Non usare dati sintetici per analisi reali.

`src/server.py` espone `describe_schema`, `find_team` e `query` tramite stdio.
`.mcp.json` registra questo server sul computer originale; i percorsi assoluti
vanno adattati su altri computer. `FOOTBALL_DB` seleziona un database diverso.

`src/db.py` apre DuckDB in sola lettura con accesso esterno disabilitato: scritture,
letture di file esterni, COPY e ATTACH sono bloccati. Una whitelist e un limite
alle righe aiutano a gestire le query generate. Nessun endpoint SQL è esposto dal sito.

Le viste di `src/schema.py` normalizzano i dati CSV: `matches`,
`team_match_stats` (una riga per squadra e partita), `team_match_form` (anche
risultati, punti e ordine delle partite). Sommare soltanto le colonne della
squadra di casa perderebbe tutte le prestazioni in trasferta. I campi assenti
rimangono NULL; le date storiche con anno a due cifre vengono normalizzate.

Per pubblicare solo il sito bastano `requirements.txt`, `src/webapp.py`,
`src/report_cache.py`, `src/provider_stats.py`, `src/csv_stats.py`,
`src/score_audit.py`, `src/static/` e l'archivio dati. Il server MCP, questo
database e i dati sintetici non sono necessari al runtime web.
