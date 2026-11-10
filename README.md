# MyCombo srl — Football Analytics

Dashboard descrittiva per squadre e giocatori, con archivio locale o PostgreSQL/Supabase. Backend Python con Starlette e Uvicorn; frontend HTML/CSS/JavaScript e GSAP/ScrollTrigger serviti dal progetto.

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

Una nuova installazione parte senza dati reali: JSON/CSV scaricati, database e credenziali non sono inclusi nel repository. Consultare l'archivio locale non richiede token e non avvia download. Usare un ambiente virtuale dedicato.

## Funzionalità

- Viste separate per giocatori e squadre; filtri per campionato, stagione, squadra e ultime partite/presenze caricate.
- Gol, assist, tiri, cartellini, falli e corner dove disponibili.
- Gol subiti e gol del primo tempo per le squadre.
- xG, xA, npxG e altre metriche avanzate con copertura esplicita.
- Posizioni di classifica fornite dai feed, senza ricostruzioni da campioni parziali.
- Base titolare stagionale e confronto con l'ultima formazione acquisita.
- Esportazione delle tabelle in Excel.
- Premium Analytics in anteprima gratuita su `/premium`: casa/trasferta, schede con grafici e medie mobili, confronto tra profili, qualità dei tiri e frequenza/variabilità. [Metodologia e configurazione](docs/premium-analytics.md).

I valori mancanti sono indicati con “—”, mai sostituiti con zero. Totali e medie si riferiscono ai dati osservati; i valori per 90 minuti usano soltanto i minuti associati alla metrica. Gli xG descrivono le occasioni osservate e non sono previsioni del prossimo risultato. La continuità della formazione non misura la forma fisica; infortuni e squalifiche non sono acquisiti.

## Fonti e copertura

| Fonte | Utilizzo |
|---|---|
| Sportmonks | Partite, statistiche, formazioni e classifiche dei campionati accessibili al piano |
| football-data.org | Classifiche generali dei sei campionati europei configurati |
| football-data.co.uk | Risultati e statistiche di squadra da CSV |
| archivio integrativo | Statistiche individuali, tiri e metriche attese per i campionati supportati |
| API-Football | Client CLI disponibile; risposte non normalizzate nella dashboard |


I test usano risposte simulate per le acquisizioni. Verificano normalizzazione, valori mancanti, classifiche, cache, budget, archivio ed esportazione Excel.
