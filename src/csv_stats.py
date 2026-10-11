"""Team-only football-data.co.uk rows, with explicit source and half-time fields."""
import csv
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re

from score_audit import goal_count

RAW = Path(__file__).resolve().parents[1] / "data/raw"
LEAGUES = {"I1": ("Serie A", "Italia"), "E0": ("Premier League", "Inghilterra"),
           "SP1": ("La Liga", "Spagna"), "D1": ("Bundesliga", "Germania"),
           "F1": ("Ligue 1", "Francia"), "P1": ("Primeira Liga", "Portogallo")}
METRICS = {"shots-on-target": "ST", "shots-total": "S", "yellowcards": "Y", "fouls": "F", "corners": "C"}


def files(root=RAW):
    return sorted(p for p in root.glob("*.csv") if re.fullmatch(r"(?:I1|E0|SP1|D1|F1|P1)_20\d\d-\d\d\.csv", p.name))


def load_rows(paths):
    rows, seen, warnings = [], set(), []
    for path in paths:
        code, years = path.stem.split("_")
        start_year = int(years[:4])
        if int(years[-2:]) != (start_year + 1) % 100:
            warnings.append(f"Stagione non valida: {path.name}")
            continue
        league, country = LEAGUES[code]
        fetched = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for index, row in enumerate(csv.DictReader(handle), 2):
                if row.get("Div") != code:
                    warnings.append(f"Divisione non valida: {path.name}:{index}")
                    continue
                try:
                    date = datetime.strptime(row["Date"], "%d/%m/%Y").date()
                    if not datetime(start_year, 7, 1).date() <= date < datetime(start_year + 1, 7, 1).date():
                        raise ValueError("date outside season")
                except (KeyError, ValueError):
                    warnings.append(f"Data non valida: {path.name}:{index}")
                    continue
                home, away = row.get("HomeTeam", "").strip(), row.get("AwayTeam", "").strip()
                ft = [goal_count(row.get("FTHG")), goal_count(row.get("FTAG"))]
                if not home or not away or None in ft:
                    continue  # Scheduled/unplayed fixtures are not observations.
                fixture = "csv:" + hashlib.sha256(f"{code}|{date}|{home}|{away}".encode()).hexdigest()[:20]
                if fixture in seen:
                    continue
                seen.add(fixture)
                ht = [goal_count(row.get("HTHG")), goal_count(row.get("HTAG"))]
                conflict = any(h is not None and h > f for h, f in zip(ht, ft))
                audit = {"fixture": fixture, "date": date.isoformat(), "match": f"{home} vs {away}",
                         "provider": "football-data.co.uk", "status": "conflict" if conflict else "source_only",
                         "ht": ht, "ft": ft, "events_ht": None, "stoppage_goals": 0,
                         "issues": ["HT superiore a FT"] if conflict else ["HTHG/HTAG; eventi non disponibili nel CSV"]}
                for i, (side, name, opponent) in enumerate((("H", home, away), ("A", away, home))):
                    stats = {key: goal_count(row.get(side + suffix)) for key, suffix in METRICS.items()}
                    stats.update(goals=ft[i], **{"first-half-goals": None if conflict else ht[i]})
                    rows.append({"provider": "football-data.co.uk", "fixture": fixture, "date": date.isoformat(),
                        "league": league, "league_id": f"csv:{code}", "season": f"{start_year}/{start_year+1}",
                        "country": country, "fetched_at": fetched, "id": f"csv:{code}:{name}",
                        "name": name, "team": name, "opponent": opponent, "stats": stats,
                        "outcome": "V" if ft[i] > ft[1-i] else "P" if ft[i] == ft[1-i] else "S",
                        "starters": [], "halftime_audit": audit, "source_file": path.name})
    return rows, warnings
