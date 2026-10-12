# Copertura dell'archivio integrativo

L'archivio comprende statistiche per partita acquisite separatamente dai feed
API. La provenienza originale rimane nei record interni per audit; i dati non
vengono attribuiti a Sportmonks o API-Football.

Le osservazioni dei giocatori sono riferite a singole partite, non ricostruite
dai totali stagionali. I dati mancanti restano assenti. Le partite con risultati
individuali incoerenti vengono escluse dai report dei giocatori.

Le fonti sono riconciliate tramite campionato, stagione, data, entrambe le
squadre e risultato finale. Nomi equivalenti sono definiti esplicitamente,
senza abbinamenti approssimativi. Le fonti sovrapposte non vanno sommate.

Gli eventi di tiro alimentano solo metriche compatibili con la loro copertura.
I gol del primo tempo usano campi espliciti HT, non il solo minuto dell'evento.
Le definizioni delle metriche avanzate sono in [expected-metrics.md](expected-metrics.md).

Per acquisizioni coordinate usare il processo descritto in
[automatic-updates.md](automatic-updates.md). Il sito legge i dati salvati e
non avvia richieste ai feed durante la navigazione.

```powershell
.\.venv\Scripts\python.exe scripts\supabase_data.py dry-run
.\.venv\Scripts\python.exe scripts\supabase_data.py import
```

L'import legge l'archivio locale senza scaricare nuove informazioni.
