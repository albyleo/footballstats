"""Read-only analytics over normalized observations. No external requests."""
from collections import defaultdict
import hashlib
import math
import statistics

import provider_stats
import understat_stats

RATIOS = {'xg-per-shot': ('xg', 'shots-total', 1, 'xG per tiro'),
          'on-target-share': ('shots-on-target', 'shots-total', 100, 'Tiri in porta (%)'),
          'xga-per-shot': ('xga', 'shots-conceded', 1, 'xG per tiro concesso')}
TEAM_ONLY = {'shots-on-target-conceded', 'goals-conceded', 'first-half-goals', 'corners', 'xga', 'xgd', 'shots-conceded', 'xga-per-shot'}
PLAYER_ONLY = {'xa', 'key-passes', 'xg-chain', 'xg-buildup', 'assists', 'fouls-drawn'}


def metrics(kind):
    result = {**provider_stats.METRICS, 'shots-conceded': 'Tiri concessi',
              **{key: value[3] for key, value in RATIOS.items()}}
    excluded = TEAM_ONLY if kind == 'players' else PLAYER_ONLY
    return {k:v for k,v in result.items() if k not in excluded}


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def observations(snapshot=None):
    players, teams, warnings = provider_stats.dataset() if snapshot is None else (snapshot['players'], snapshot['teams'], snapshot['warnings'])
    teams = provider_stats.with_goals_conceded(teams)
    fixtures = defaultdict(list)
    for row in teams:
        fixtures[(row['provider'], row['fixture'], row['league'], row['season'])].append(row)
    enriched = []
    for rows in fixtures.values():
        for row in rows:
            opponents = [other for other in rows if other['id'] != row['id']]
            conceded = opponents[0]['stats'].get('shots-total') if len(rows) == 2 and len(opponents) == 1 else None
            enriched.append({**row, 'stats': {**row['stats'], 'shots-conceded': conceded}})
    players, teams, extra = understat_stats.merge_sources(players, enriched)
    return players, teams, sorted(set(warnings + extra))


def identity(row, kind):
    parts = [kind, row['league'], row['season'], row['team']]
    if kind == 'players':
        parts += [row['provider'], str(row['id'])]
    return hashlib.sha256('\0'.join(parts).encode()).hexdigest()[:24]


def value(row, metric, basis):
    if metric in RATIOS:
        numerator, denominator, scale, _ = RATIOS[metric]
        n, d = number(row['stats'].get(numerator)), number(row['stats'].get(denominator))
        return n / d * scale if n is not None and d is not None and d > 0 else None
    n = number(row['stats'].get(metric))
    if basis == 'per90':
        minutes = number(row.get('minutes'))
        return n * 90 / minutes if n is not None and minutes is not None and minutes > 0 else None
    return n


def aggregate(rows, metric, basis):
    if metric in RATIOS:
        numerator, denominator, scale, _ = RATIOS[metric]
        paired = [r for r in rows if number(r['stats'].get(numerator)) is not None
                  and number(r['stats'].get(denominator)) is not None and r['stats'][denominator] > 0]
        d = sum(r['stats'][denominator] for r in paired)
        return sum(r['stats'][numerator] for r in paired) / d * scale if d else None
    known = [r for r in rows if value(r, metric, basis) is not None]
    if not known:
        return None
    total = sum(r['stats'][metric] for r in known)
    return total * 90 / sum(r['minutes'] for r in known) if basis == 'per90' else total / len(known)


def summary(rows, metric, basis, threshold):
    values = [v for r in rows if (v := value(r, metric, basis)) is not None]
    n = len(values)
    successes = sum(v >= threshold for v in values)
    return dict(matches=len(rows), covered=n, mean=aggregate(rows, metric, basis),
                median=statistics.median(values) if n else None,
                stddev=statistics.pstdev(values) if n else None,
                minimum=min(values) if n else None, maximum=max(values) if n else None,
                total=sum(r['stats'][metric] for r in rows if value(r, metric, basis) is not None) if n and metric not in RATIOS else None,
                successes=successes, threshold=threshold, frequency=successes/n if n else None)


def profile(rows, kind, metric, basis, venue, last_n, threshold):
    rows = sorted(rows, key=lambda r:(r['date'], str(r['fixture'])))
    selected_season = [r for r in rows if venue == 'all' or r.get('venue') == venue]
    selected = selected_season[-last_n:] if last_n else selected_season
    series = []
    for i, row in enumerate(selected_season):
        point = dict(date=row['date'], opponent=row.get('opponent'), venue=row.get('venue'),
                     minutes=row.get('minutes'), value=value(row, metric, basis))
        for size in (5, 10):
            window = selected_season[max(0, i-size+1):i+1]
            point[f'ma{size}'] = aggregate(window, metric, basis) if len(window) == size and all(value(r, metric, basis) is not None for r in window) else None
        series.append(point)
    quality = {key: {'value': aggregate(selected, key, 'match'),
                     'covered': sum(value(r, key, 'match') is not None for r in selected)}
               for key in RATIOS if key in metrics(kind)}
    first = rows[0]
    return dict(name=first['name'], team=first['team'], league=first['league'], season=first['season'],
                summary=summary(selected, metric, basis, threshold),
                season_summary=summary(selected_season, metric, basis, threshold),
                splits={side: summary([r for r in rows if r.get('venue') == side], metric, basis, threshold) for side in ('home', 'away')},
                unknown_venue=sum(r.get('venue') not in ('home', 'away') for r in rows),
                quality=quality, series=series[-last_n:] if last_n else series,
                last5=summary(selected_season[-5:], metric, basis, threshold),
                last10=summary(selected_season[-10:], metric, basis, threshold),
                latest=rows[-1]['date'], fetched_at=max(r.get('fetched_at', '') for r in rows))


def report(kind='teams', league='', season='', entity='', compare='', metric='xg', venue='all', last_n=0, basis='match', threshold=1, *, snapshot=None):
    if kind not in ('teams','players') or metric not in metrics(kind) or venue not in ('all','home','away') or last_n not in (0,5,10) or basis not in ('match','per90'):
        raise ValueError('Invalid analytics filters')
    if not math.isfinite(threshold) or abs(threshold) > 10000:
        raise ValueError('Invalid threshold')
    if basis == 'per90' and (kind != 'players' or metric in RATIOS):
        raise ValueError('Per90 unavailable for this metric')
    players, teams, warnings = observations(snapshot)
    rows = players if kind == 'players' else teams
    if kind == 'players':
        rows = [r for r in rows if number(r.get('minutes')) is not None and r['minutes'] > 0]
    leagues = sorted({r['league'] for r in rows})
    league = league or (leagues[0] if leagues else '')
    seasons = sorted({r['season'] for r in rows if r['league'] == league}, reverse=True)
    season = season or (seasons[0] if seasons else '')
    groups = defaultdict(list)
    for row in rows:
        if row['league'] == league and row['season'] == season:
            groups[identity(row,kind)].append(row)
    entities = sorted([dict(id=key, name=group[0]['name'], team=group[0]['team']) for key,group in groups.items()], key=lambda r:(r['name'],r['team']))
    entity = entity or (entities[0]['id'] if entities else '')
    if (entity and entity not in groups) or (compare and compare not in groups):
        raise ValueError('Entity not in selected competition/season')
    return dict(access='open_preview', leagues=leagues, seasons=seasons, entities=entities, metrics=metrics(kind),
                filters=dict(kind=kind,league=league,season=season,entity=entity,compare=compare,metric=metric,venue=venue,last_n=last_n,basis=basis,threshold=threshold),
                primary=profile(groups[entity],kind,metric,basis,venue,last_n,threshold) if entity else None,
                comparison=profile(groups[compare],kind,metric,basis,venue,last_n,threshold) if compare else None,
                warnings=warnings)
