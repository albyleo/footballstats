"""Read cached public match data. No network access; missing is never zero."""
from collections import defaultdict
from datetime import date
import json
import math
from pathlib import Path

from score_audit import goal_count

ROOT = Path(__file__).resolve().parents[1] / 'data/providers/understat'
LEAGUES = {'Serie_A': ('I1', 'Serie A'), 'EPL': ('E0', 'Premier League'),
           'La_liga': ('SP1', 'La Liga'), 'Bundesliga': ('D1', 'Bundesliga'),
           'Ligue_1': ('F1', 'Ligue 1')}
# Explicit equivalences verified against both catalogues. No fuzzy joins.
ALIASES = {'Serie A': {'AC Milan': 'Milan', 'Parma Calcio 1913': 'Parma'},
           'Bundesliga': {'Bayer Leverkusen': 'Leverkusen', 'Borussia Dortmund': 'Dortmund',
                          'Borussia M.Gladbach': "M'gladbach", 'Eintracht Frankfurt': 'Ein Frankfurt',
                          'FC Cologne': 'FC Koln', 'Hamburger SV': 'Hamburg', 'Mainz 05': 'Mainz',
                          'RasenBallsport Leipzig': 'RB Leipzig', 'VfB Stuttgart': 'Stuttgart'},
           'Ligue 1': {'Paris Saint Germain': 'Paris SG'},
           'Premier League': {'Manchester City': 'Man City', 'Manchester United': 'Man United',
                              'Newcastle United': 'Newcastle', 'Nottingham Forest': "Nott'm Forest"},
           'La Liga': {'Athletic Club': 'Ath Bilbao', 'Atletico Madrid': 'Ath Madrid',
                       'Celta Vigo': 'Celta', 'Deportivo La Coruna': 'La Coruna',
                       'Espanyol': 'Espanol', 'Racing Santander': 'Santander',
                       'Rayo Vallecano': 'Vallecano', 'Real Betis': 'Betis', 'Real Sociedad': 'Sociedad'}}


def files(root=ROOT):
    return sorted(root.glob('league-*.json')) + sorted(root.glob('match-*.json'))


def name(league, value):
    return ALIASES.get(league, {}).get(value, value)


def expected(value):
    """Expected metrics are nonnegative decimals; missing is not zero."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def match_rows(match, envelope, league, code, season):
    if match.get('isResult') is not True or match['datetime'][:10] > date.today().isoformat():
        return [], []
    data = envelope['data']
    if set(data['rosters']) != {'h', 'a'} or set(data['shots']) != {'h', 'a'}:
        raise ValueError('Missing match sides')
    ft = {side: goal_count(match['goals'][side]) for side in ('h', 'a')}
    if None in ft.values():
        raise ValueError('Missing final score')
    base = dict(provider='understat', fixture='understat:' + str(match['id']),
                date=match['datetime'][:10], league=league, league_id='understat:' + code,
                season=season, fetched_at=envelope['fetched_at'], source_url=envelope['source_url'])
    players, teams, issues = [], [], []
    for side, other in (('h', 'a'), ('a', 'h')):
        roster = list(data['rosters'][side].values())
        if not roster or any(str(p['team_id']) != str(match[side]['id']) for p in roster):
            raise ValueError('Roster/team mismatch')
        goals = [goal_count(p.get('goals')) for p in roster]
        own = [goal_count(p.get('own_goals')) for p in data['rosters'][other].values()]
        if None in goals + own or sum(goals) + sum(own) != ft[side]:
            issues.append(f"Understat {match['id']}: gol individuali/autogol non coerenti con FT; giocatori esclusi.")
        shots_by_player = defaultdict(list)
        for shot in data['shots'][side]:
            if str(shot['match_id']) != str(match['id']):
                raise ValueError('Shot/match mismatch')
            shots_by_player[str(shot['player_id'])].append(shot)
        team = name(league, match[side]['title'])
        tid = 'understat:' + str(match[side]['id'])
        side_players = []
        for p in roster:
            if not p.get('position'):
                raise ValueError('Missing starting position')
            stats = {key: goal_count(p.get(field)) for key, field in
                     [('goals', 'goals'), ('assists', 'assists'), ('yellowcards', 'yellow_card'),
                      ('shots-total', 'shots')]}
            shots = shots_by_player[str(p['player_id'])]
            # Validate the event list against the explicit player shot total.
            valid = (stats['shots-total'] == len(shots) and
                     all(s['result'] in {'Goal', 'SavedShot', 'MissedShots', 'BlockedShot', 'ShotOnPost'} for s in shots))
            stats['shots-on-target'] = sum(s['result'] in {'Goal', 'SavedShot'} for s in shots) if valid else None
            stats.update({key: expected(p.get(field)) for key, field in
                          [('xg', 'xG'), ('xa', 'xA'), ('xg-chain', 'xGChain'), ('xg-buildup', 'xGBuildup')]})
            stats['key-passes'] = goal_count(p.get('key_passes'))
            stats['goals-minus-xg'] = stats['goals'] - stats['xg'] if stats['goals'] is not None and stats['xg'] is not None else None
            shot_xg = [expected(s.get('xG')) for s in shots]
            consistent = (valid and None not in shot_xg and stats['xg'] is not None
                          and abs(sum(shot_xg) - stats['xg']) < 0.0001
                          and all(s.get('situation') in {'OpenPlay','FromCorner','SetPiece','DirectFreekick','Penalty'} for s in shots))
            stats['npxg'] = sum(x for s, x in zip(shots, shot_xg) if s['situation'] != 'Penalty') if consistent else None
            row = dict(**base, id='understat:' + str(p['player_id']), name=p['player'], team=team,
                       team_id=tid, minutes=goal_count(p.get('time')), starter=p.get('position') != 'Sub',
                       stats=stats, metric_sources={'shots-on-target': 'Understat shots: Goal + SavedShot; total checked'})
            players.append(row)
            side_players.append(row)
        # Only use the shot event list when it reconciles with all player totals.
        complete_shots = (all(p['stats']['shots-on-target'] is not None for p in side_players)
                          and sum(p['stats']['shots-total'] for p in side_players) == len(data['shots'][side]))
        team_stats = {'goals': ft[side],
                      'shots-total': len(data['shots'][side]) if complete_shots else None,
                      'shots-on-target': sum(p['stats']['shots-on-target'] for p in side_players) if complete_shots else None}
        team_stats['xg'] = expected((match.get('xG') or {}).get(side))
        team_stats['xga'] = expected((match.get('xG') or {}).get(other))
        team_stats['xgd'] = team_stats['xg'] - team_stats['xga'] if None not in (team_stats['xg'], team_stats['xga']) else None
        team_stats['goals-minus-xg'] = ft[side] - team_stats['xg'] if team_stats['xg'] is not None else None
        values = [p['stats']['npxg'] for p in side_players]
        team_stats['npxg'] = sum(values) if complete_shots and None not in values else None
        teams.append(dict(**base, id=tid, name=team, team=team,
                          opponent=name(league, match[other]['title']), stats=team_stats,
                          outcome='V' if ft[side] > ft[other] else 'P' if ft[side] == ft[other] else 'S',
                          starters=sorted(p['id'] for p in side_players if p['starter'])))
    if issues:
        players = []
        for team in teams:
            team['stats'] = {'goals': team['stats']['goals']}
            team['starters'] = []
            team['player_data_issues'] = sorted(set(issues))
    return players, teams


def load_rows(root=ROOT):
    players, teams, warnings, seen = [], [], [], set()
    for league_file in sorted(root.glob('league-*.json')):
        try:
            slug, year = league_file.stem.removeprefix('league-').rsplit('-', 1)
            code, league = LEAGUES[slug]
            season = f'{int(year)}/{int(year)+1}'
            listing = json.loads(league_file.read_text(encoding='utf-8'))['data']['dates']
            for match in listing:
                mid = str(match['id'])
                path = root / f'match-{mid}.json'
                if not mid.isdigit() or mid in seen or not path.exists():
                    continue
                envelope = json.loads(path.read_text(encoding='utf-8'))
                p, t = match_rows(match, envelope, league, code, season)
                players.extend(p)
                teams.extend(t)
                seen.add(mid)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            warnings.append(f'Understat {league_file.name}: {exc}')
    return players, teams, warnings


def merge_sources(players, teams):
    """One observation per fixture in reports; retain source rows in PostgreSQL.

    Join requires league, season, date, both explicitly mapped teams and equal FT.
    CSV supplies team statistics/HT; Understat supplies appearances. A disagreement
    keeps CSV and excludes the conflicting Understat fixture, with an alert.
    """
    def key(row):
        return (row['league'], row['season'], row['date'], row['team'], row.get('opponent'))
    csv = {key(r): r for r in teams if r['provider'] == 'football-data.co.uk'}
    rejected, warnings = set(), []
    for row in teams:
        if row['provider'] == 'understat' and (original := csv.get(key(row))):
            if original['stats'].get('goals') != row['stats'].get('goals'):
                rejected.add(row['fixture'])
    if rejected:
        warnings.append(f'Conflitti FT tra fonti: {len(rejected)} partite Understat escluse.')
    used, result = set(), []
    for row in teams:
        if row['provider'] != 'understat':
            continue
        if row['fixture'] in rejected:
            continue
        original = csv.get(key(row))
        if original:
            combined = {**original['stats'], **row['stats']}
            combined.update({k: v for k, v in original['stats'].items() if v is not None})
            row = {**row, 'stats': combined,
                   'metric_sources': {k: ('football-data.co.uk' if original['stats'].get(k) is not None else 'understat') for k in combined},
                   'halftime_audit': {**original['halftime_audit'], 'fixture': row['fixture']}}
            used.add(key(original))
        result.append(row)
    result.extend(r for r in teams if r['provider'] != 'understat' and
                  not (r['provider'] == 'football-data.co.uk' and key(r) in used))
    return [r for r in players if not (r['provider'] == 'understat' and r['fixture'] in rejected)], result, warnings
