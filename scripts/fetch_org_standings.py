"""Bounded football-data.org standings acquisition using the shared Store."""
import json
import os
import time
from datetime import date
from fetch_understat import save

COMPETITIONS = {'SA': 'Serie A', 'PL': 'Premier League', 'PD': 'La Liga',
                'BL1': 'Bundesliga', 'FL1': 'Ligue 1', 'PPL': 'Primeira Liga'}


def normalize(payload, code):
    if not isinstance(payload, dict) or payload.get('competition', {}).get('code') != code:
        raise ValueError('Unexpected football-data.org competition')
    season = payload.get('season') or {}
    start = date.fromisoformat(season['startDate'])
    end = date.fromisoformat(season['endDate'])
    if not start < end or end.year != start.year + 1:
        raise ValueError('Invalid standings season')
    tables = [s for s in payload.get('standings', [])
              if s.get('type') == 'TOTAL' and s.get('stage') == 'REGULAR_SEASON' and s.get('group') in (None, '', 'Matchday')]
    if len(tables) != 1 or not tables[0].get('table'):
        raise ValueError('Missing or ambiguous overall standings')
    rows = []
    for row in tables[0]['table']:
        team = row['team']
        if type(row.get('position')) is not int or row['position'] < 1 or type(team.get('id')) is not int:
            raise ValueError('Invalid standings row')
        rows.append(dict(league=COMPETITIONS[code], season=f'{start.year}/{end.year}',
                         team_id=team['id'], names=[n for n in (team.get('name'), team.get('shortName')) if n],
                         position=row['position'], points=row.get('points'), played=row.get('playedGames')))
    if len({r['team_id'] for r in rows}) != len(rows) or len({r['position'] for r in rows}) != len(rows):
        raise ValueError('Duplicate standings row')
    return rows, start.year


def download(store, root, now):
    token = os.environ.get('FOOTBALL_DATA_ORG', '').strip()
    if not token:
        print('football-data.org: key missing; standings skipped', flush=True)
        return
    year = now.year if now.month >= 7 else now.year - 1
    for code in COMPETITIONS:
        path = root / f'data/providers/football-data-org/standings-{code}-{year}.json'
        if path.exists() and time.time() - path.stat().st_mtime < 86400:
            continue
        payload = json.loads(store.fetch('football-data.org',
            f'https://api.football-data.org/v4/competitions/{code}/standings',
            {'X-Auth-Token': token, 'Accept': 'application/json', 'User-Agent': 'MyComboDataSync/1.0'}))
        rows, actual_year = normalize(payload, code)
        if actual_year != year:
            raise ValueError('football-data.org returned a different season; cache unchanged')
        # Keep only needed fields, never arbitrary response fields or credentials.
        save(path, dict(provider='football-data.org', fetched_at=now.isoformat(), data=rows))
        store.persist(path)
        print(f'football-data.org {code}: {len(rows)} teams', flush=True)
