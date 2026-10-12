# Verifica copertura del 12 ottobre 2026

- Portogallo: integrato P1, Primeira Liga 2026/27, da
  https://football-data.co.uk/portugalm.php. Una richiesta CSV: 62 partite,
  18 squadre, ultima data 20 settembre 2026. Gol FT/HT, tiri totali/in porta,
  gialli, falli e corner disponibili per entrambe le squadre; nessun giocatore.
  Importate 62 partite su Supabase e conservato il file nella cache persistente.
- Arabia Saudita e Islanda: integrazione dati non disponibile nel campione.
  La copertura delle stagioni va verificata prima di attivare un nuovo feed.
  Sportmonks Free copre Danimarca e Scozia, non questi campionati:
  https://www.sportmonks.com/football-api/free-plan/.
- Archivio integrativo: dati acquisiti separatamente e riconciliati con le altre fonti.

Per proseguire con Arabia Saudita e Islanda occorre controllare nel
dashboard del provider le stagioni e la copertura accessibili
prima di implementare il download. Non inserire campionati vuoti come se
fossero coperti e non sostituire la stagione corrente con storici senza indicarlo.
