# Metriche attese

Disponibili dai file Understat già acquisiti, senza nuove richieste HTTP.
I valori sono stime del modello del provider sulle occasioni osservate,
non previsioni del risultato della prossima partita.

| Campo | Definizione e origine |
|---|---|
| xG | Gol attesi: `xG` del roster per giocatore, `xG.h/a` del catalogo per squadra. |
| xA | Assist attesi: `xA` esplicito del roster, solo giocatori. |
| npxG | Somma degli xG degli eventi esclusi quelli con `situation=Penalty`. Disponibile solo quando numero, esiti e xG dei tiri riconciliano il roster; per squadra devono essere completi tutti i giocatori. |
| xG subiti | xG dell'avversaria nello stesso incontro. Solo squadre. |
| Differenza xG | xG prodotti meno xG subiti, calcolati per partita con entrambi presenti. |
| Gol − xG | Scostamento tra gol e xG nella stessa partita. Positivo: più gol degli attesi. I gol di squadra includono gli autogol a favore, quelli del giocatore no. |
| Passaggi chiave | `key_passes` del roster, solo giocatori. |
| xGChain | Indicatore di partecipazione alle azioni che terminano in tiro, `xGChain` del roster. Non sommare tra giocatori per ricostruire gli xG di squadra. |
| xGBuildup | Indicatore di costruzione delle azioni, `xGBuildup` del roster; non ricalcolato da xGChain. Solo giocatori. |

Valori mancanti, negativi dove non consentiti, infiniti e NaN restano assenti.
Zero è un dato valido. Le differenze possono essere negative.
Le esclusioni per incoerenza dei risultati individuali restano applicate.
Totali, per 90 minuti e medie per partita usano solo le osservazioni con la
metrica disponibile; non sottrarre totali con coperture diverse.
I filtri ultime N usano le ultime partite/presenze caricate, non necessariamente
tutto il calendario. Excel mantiene i valori numerici non arrotondati.

La colonna xG è visibile nella tabella riepilogativa, insieme a xA per i
giocatori e xG subiti per le squadre. Le altre metriche sono selezionabili.
Il normale import aggiorna i JSONB esistenti, senza migrazioni SQL; il job
normalizza automaticamente questi campi anche nelle acquisizioni future.

Riferimento concettuale per xGChain/xGBuildup:
https://statsbomb.com/articles/soccer/introducing-xgchain-and-xgbuildup/
