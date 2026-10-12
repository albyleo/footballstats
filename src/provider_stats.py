"""Descriptive statistics from cached completed fixtures; no network calls."""
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import csv_stats
import understat_stats
import standings
from lineup_stats import season_lineups
from score_audit import audit_match, score_value

ROOT = Path(__file__).resolve().parents[1] / "data/providers/sportmonks"
METRICS = {"shots-on-target": "Tiri in porta", "yellowcards": "Gialli",
           "xg": "xG", "xa": "xA", "npxg": "npxG", "xga": "xG subiti", "xgd": "Differenza xG",
           "goals-minus-xg": "Gol − xG", "key-passes": "Passaggi chiave",
           "xg-chain": "xGChain", "xg-buildup": "xGBuildup",
           "fouls": "Falli commessi", "fouls-drawn": "Falli subiti", "assists": "Assist", "goals": "Gol",
           "shots-total": "Tiri totali", "shots-on-target-conceded": "Tiri in porta subiti", "goals-conceded": "Gol subiti", "first-half-goals": "Gol primo tempo", "corners": "Calci d’angolo"}


def numeric(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def details(items):
    return {item.get("type", {}).get("code"): numeric((item.get("data") or {}).get("value"))
            for item in items}


def catalog(root=ROOT):
    leagues = {}
    for path in sorted(root.glob("leagues-page-*.json")):
        for league in json.loads(path.read_text(encoding="utf-8"))["data"]:
            leagues[league["id"]] = league
    return leagues


def input_revision(root=None, include_status=True):
    root = ROOT if root is None else root
    paths = sorted(root.glob("match-*.json")) + sorted(root.glob("leagues-page-*.json")) + sorted(root.glob("standings-*.json")) + standings.files() + csv_stats.files() + understat_stats.files()
    if include_status and (root / "sync-status.json").exists():
        paths.append(root / "sync-status.json")
    signature = []
    for path in paths:
        info = path.stat()
        signature.append((str(path), info.st_mtime_ns, info.st_size))
    return tuple(signature)


def dataset(root=ROOT):
    return _dataset(str(root), input_revision(root, include_status=False))


@lru_cache(maxsize=2)
def _dataset(directory, signature):
    root = Path(directory)
    players, teams, fixtures, warnings = [], [], {}, []
    leagues = catalog(root)
    for path in sorted(root.glob("match-*.json")):
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            match = envelope["data"]
            if (match.get("state") or {}).get("state") != "FT":
                continue
            fixtures[match["id"]] = (match, envelope["fetched_at"])
        except (ValueError, KeyError, TypeError, AttributeError):
            warnings.append(f"File non valido: {path.name}")
    for match, fetched in fixtures.values():
        audit = audit_match(match)
        names = {p["id"]: p["name"] for p in match.get("participants", [])}
        venues = {p['id']: (p.get('meta') or {}).get('location') for p in match.get('participants', [])}
        base = {"provider": "sportmonks", "fixture": match["id"], "date": match["starting_at"][:10],
                "league": leagues.get(match["league_id"], {}).get("name", str(match["league_id"])),
                "league_id": match["league_id"],
                "season": (match.get("season") or {}).get("name", str(match["season_id"])), "fetched_at": fetched}
        for player in match.get("lineups", []):
            stats = details(player.get("details", []))
            # Unused substitutes remain in roster data but are not appearances.
            players.append({**base, "id": player["player_id"], "name": player["player_name"],
                            "venue": venues.get(player['team_id']),
                            "opponent": next((n for i,n in names.items() if i != player['team_id']), None),
                            "team": names.get(player["team_id"], str(player["team_id"])),
                            "team_id": player["team_id"], "starter": player.get("type_id") == 11,
                            "minutes": stats.get("minutes-played"), "stats": stats})
        scores = {tid: score_value(match, tid, 1525) for tid in names}
        for tid, name in names.items():
            stats = details([s for s in match.get("statistics", []) if s.get("participant_id") == tid])
            stats["goals"] = score_value(match, tid, 1525)
            stats["first-half-goals"] = None if audit["status"] == "conflict" else score_value(match, tid, 1)
            opponent = next((i for i in names if i != tid), None)
            gf, ga = scores.get(tid), scores.get(opponent)
            outcome = None if gf is None or ga is None else ("V" if gf > ga else "P" if gf == ga else "S")
            starters = sorted(p["player_id"] for p in match.get("lineups", [])
                              if p["team_id"] == tid and p.get("type_id") == 11)
            teams.append({**base, "id": tid, "name": name, "team": name, "stats": stats,
                          "venue": venues.get(tid), "opponent": names.get(opponent),
                          "outcome": outcome, "starters": starters, "halftime_audit": audit})
    csv_rows, csv_warnings = csv_stats.load_rows(csv_stats.files())
    teams.extend(csv_rows)
    warnings.extend(csv_warnings)
    extra_players, extra_teams, extra_warnings = understat_stats.load_rows()
    players.extend(extra_players)
    teams.extend(extra_teams)
    warnings.extend(extra_warnings)
    return players, teams, warnings


def with_goals_conceded(teams):
    """Derive opponent goals and shots on target before filtering or merging."""
    fixtures = defaultdict(list)
    for row in teams:
        fixtures[(row['provider'], row['league'], row['season'], row['fixture'])].append(row)
    result = []
    for rows in fixtures.values():
        for row in rows:
            opponent = [other for other in rows if other['id'] != row['id']]
            conceded = opponent[0]['stats'].get('goals') if len(rows) == 2 and len(opponent) == 1 else None
            shots = opponent[0]['stats'].get('shots-on-target') if len(rows) == 2 and len(opponent) == 1 else None
            result.append({**row, 'stats': {**row['stats'], 'goals-conceded': conceded,
                                          'shots-on-target-conceded': shots}})
    return result


def report(kind="players", metric="shots-on-target", league="", season="", min_minutes=0,
           team="", search="", last_n=0, sort="total", *, snapshot=None):
    if kind not in ("players", "teams") or metric not in METRICS or sort not in ("total", "per90", "minutes", "name"):
        raise ValueError("Tipo o metrica non valida")
    players, teams, warnings = dataset() if snapshot is None else (snapshot['players'], snapshot['teams'], snapshot['warnings'])
    players, teams, merge_warnings = understat_stats.merge_sources(players, with_goals_conceded(teams))
    league_positions = standings.index(standings.load() if snapshot is None else snapshot.get('standings', {})) if kind == 'teams' else {}
    lineups = season_lineups(players, teams) if kind == 'teams' else {}
    warnings = warnings + merge_warnings
    warnings = sorted(set(warnings + [issue for row in teams for issue in row.get('player_data_issues', [])]))
    selected = [r for r in (players if kind == "players" else teams)
                if (not league or r["league"] == league) and (not season or r["season"] == season)
                and (not team or r["team"] == team)]
    groups = defaultdict(list)
    for row in selected:
        if kind == "players" and not (row["minutes"] is not None and row["minutes"] > 0):
            continue
        groups[(row["provider"], row["id"], row["team"], row["league"], row["season"])].append(row)
    result = []
    for rows in groups.values():
        rows = sorted(rows, key=lambda r: (r["date"], r["fixture"]), reverse=True)
        if last_n:
            rows = rows[:last_n]
        known = [r for r in rows if r["stats"].get(metric) is not None]
        total = sum(r["stats"][metric] for r in known) if known else None
        minutes = sum(r["minutes"] or 0 for r in rows) if kind == "players" else None
        paired_minutes = sum(r["minutes"] for r in known) if kind == "players" else 0
        if kind == "players" and minutes < min_minutes:
            continue
        first = rows[0]
        if search and search.casefold() not in (first["name"] + " " + first["team"]).casefold():
            continue
        totals = {k: sum(r["stats"][k] for r in rows if r["stats"].get(k) is not None)
                  if any(r["stats"].get(k) is not None for r in rows) else None for k in METRICS}
        coverage = {k: sum(r["stats"].get(k) is not None for r in rows) for k in METRICS}
        same_starters = None
        if kind == "teams" and len(rows) >= 2 and all(len(r.get("starters", [])) == 11 for r in rows[:2]):
            same_starters = len(set(rows[0]["starters"]) & set(rows[1]["starters"]))
        result.append({"name": first["name"], "team": first["team"], "league": first["league"],
                       "standing": standings.lookup(league_positions, first),
                       "provider": first["provider"],
                       "season": first["season"], "matches": len(rows), "covered": len(known),
                       "minutes": minutes, "total": total,
                       "per90": round(total * 90 / paired_minutes, 2) if paired_minutes and total is not None else None,
                       "per_match": round(total / len(known), 2) if known else None,
                       "starts": sum(r.get("starter", False) for r in rows) if kind == "players" else None,
                       "totals": totals, "coverage": coverage, "paired_minutes": paired_minutes,
                       "form": [r.get("outcome") for r in rows[:5]][::-1] if kind == "teams" else [],
                       "same_starters": same_starters,
                       "season_lineup": lineups.get((first['provider'], first['league'], first['season'], first['team']))})
    if sort == "name":
        result.sort(key=lambda r: r["name"].casefold())
    else:
        result.sort(key=lambda r: (r[sort] is not None, r[sort] or 0), reverse=True)
    all_rows = teams
    coverage_cards = []
    for lid, entry in (catalog() if snapshot is None else snapshot['catalog']).items():
        loaded = [r for r in teams if r.get("league_id") == lid]
        coverage_cards.append({"id": lid, "name": entry["name"],
            "provider": "Sportmonks", "scope": "players_and_teams",
            "latest_match": max((r["date"] for r in loaded), default=None),
            "country": {320: "Danimarca", 1161: "Scozia"}.get(entry.get("country_id"), ""),
            "season": (entry.get("currentseason") or {}).get("name"),
            "matches": len({r["fixture"] for r in loaded}), "teams": len({r["id"] for r in loaded}),
            "players": len({r["id"] for r in players if r.get("league_id") == lid and (r["minutes"] or 0) > 0})})
    for code, (name, country) in csv_stats.LEAGUES.items():
        loaded = [r for r in teams if r.get("league_id") in (f"csv:{code}", f"understat:{code}")]
        individual = [r for r in players if r.get('league_id') == f'understat:{code}' and (r['minutes'] or 0) > 0]
        if loaded:
            coverage_cards.append({"id": f"csv:{code}", "name": name, "country": country,
                "provider": "Understat + football-data.co.uk" if individual else "football-data.co.uk", "scope": "players_and_teams" if individual else "teams",
                "season": ", ".join(sorted({r["season"] for r in loaded})),
                "matches": len({r["fixture"] for r in loaded}), "teams": len({r["team"] for r in loaded}),
                "players": len({r['id'] for r in individual}), "latest_match": max(r["date"] for r in loaded),
                "player_matches": len({r['fixture'] for r in individual}),
                "ht_matches": len({r['fixture'] for r in loaded if r['stats'].get('first-half-goals') is not None})})
    status_path = ROOT / "sync-status.json"
    sync = snapshot['sync'] if snapshot is not None else (json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else None)
    audit_rows = {r["fixture"]: r["halftime_audit"] for r in teams if "halftime_audit" in r
                  and (not league or r["league"] == league) and (not season or r["season"] == season)
                  and (not team or r["team"] == team)}
    return {"rows": result, "metrics": METRICS, "leagues": sorted({r["league"] for r in all_rows}),
            "catalog": coverage_cards, "sync": sync,
            "halftime_audit": sorted(audit_rows.values(), key=lambda r: (r["date"], str(r["fixture"])), reverse=True),
            "teams": sorted({r["team"] for r in teams if not league or r["league"] == league}),
            "seasons": sorted({r["season"] for r in all_rows}),
            "fixtures": len({r["fixture"] for r in selected}),
            "dates": sorted({r["date"] for r in selected}),
            "updated": max((r["fetched_at"] for r in selected), default=None),
            "warnings": warnings,
            "metric_coverage": {k: sum(r["stats"].get(k) is not None for r in selected) for k in METRICS},
            "total_players": len({(r['provider'], r["id"]) for r in players if (r["minutes"] or 0) > 0}),
            "total_teams": len({(r['league'], r['team']) for r in teams}),
            "availability": "Assenze e infortuni non acquisiti. Titolarità riferita solo alle partite del campione; nessuna stima di forma fisica."}
