"""Descriptive pre-match comparisons over reconciled, saved team observations."""
from datetime import date, datetime, timezone
import math

from entity_identity import identity
from lineup_stats import season_lineups
import availability


METRICS = (
    ('shots-on-target', 'shots-on-target-conceded', 'Tiri in porta'),
    ('shots-total', 'shots-conceded', 'Tiri totali'),
    ('goals', 'goals-conceded', 'Gol'),
    ('xg', 'xga', 'xG'),
    ('first-half-goals', 'first-half-goals-conceded', 'Gol primo tempo'),
    ('corners', 'corners-conceded', 'Corner'),
)


def valid_day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def numeric(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def summary(rows, metric):
    values = [v for r in rows if (v := numeric(r['stats'].get(metric))) is not None]
    return dict(mean=sum(values) / len(values) if values else None,
                covered=len(values), matches=len(rows))


def comparison(rows, baseline, metric):
    result = summary(rows, metric)
    result['baseline'] = summary(baseline, metric)
    a, b = result['mean'], result['baseline']['mean']
    result['difference'] = a - b if a is not None and b is not None else None
    return result


def goal_frequencies(rows):
    values = [int(v) for r in rows if (v := numeric(r['stats'].get('goals'))) is not None
              and v == int(v)]
    bins = [sum(min(v, 6) == k for v in values) for k in range(7)]
    return dict(covered=len(values), matches=len(rows),
                bins=[dict(label=str(k) if k < 6 else '6+', count=count,
                           frequency=count / len(values) if values else None)
                      for k, count in enumerate(bins)])


def paired_ratio(rows, numerator, denominator, scale=1):
    pairs = [(n, d) for r in rows if (n := numeric(r['stats'].get(numerator))) is not None
             and (d := numeric(r['stats'].get(denominator))) is not None and d > 0]
    return dict(mean=scale * sum(n for n, _ in pairs) / sum(d for _, d in pairs) if pairs else None,
                covered=len(pairs), matches=len(rows))


def recent_form(rows):
    rows = sorted(rows, key=lambda r: (r['date'], str(r['fixture'])))[-5:]
    matches, points = [], []
    for r in rows:
        gf, ga = numeric(r['stats'].get('goals')), numeric(r['stats'].get('goals-conceded'))
        outcome = None if gf is None or ga is None else ('V' if gf > ga else 'P' if gf == ga else 'S')
        if outcome is not None:
            points.append({'V':3, 'P':1, 'S':0}[outcome])
        matches.append(dict(date=r['date'], opponent=r.get('opponent'), result=outcome, goals=gf, conceded=ga))
    return dict(matches=matches, covered=len(points), points=sum(points) if points else None,
                points_per_match=sum(points) / len(points) if points else None,
                goals=summary(rows, 'goals'), conceded=summary(rows, 'goals-conceded'))


def events_summary(rows, metric, predicate):
    values = [v for r in rows if (v := numeric(r['stats'].get(metric))) is not None]
    return dict(count=sum(predicate(v) for v in values), covered=len(values), matches=len(rows))


def build(teams, selected, fixture, last_n=0, *, today=None, players=(), availability_data=None):
    """Keep goal frequencies historical; do not turn them into forecast probabilities."""
    if last_n not in (0, 5, 10):
        raise ValueError('Invalid match comparison window')
    result = dict(mode='descriptive', status='unavailable', last_n=last_n,
                  league=selected['league'], season=selected['season'])
    if not fixture:
        return {**result, 'reason':'Prossima partita non disponibile nel calendario salvato.'}
    as_of = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
    fixture_day = valid_day(fixture.get('date'))
    if (not fixture_day or fixture_day < as_of or fixture.get('venue') not in ('home', 'away')
            or not fixture.get('opponent') or fixture['opponent'] == selected['team']):
        return {**result, 'reason':'Data, campo o avversario non disponibili per un confronto coerente.'}
    home, away = ((selected['team'], fixture['opponent']) if fixture['venue'] == 'home'
                  else (fixture['opponent'], selected['team']))
    # Dates carry no reliable kickoff timezone: conservatively exclude the entire current day.
    cutoff = min(as_of, fixture_day)
    history = [r for r in teams if r['league'] == selected['league'] and r['season'] == selected['season']
               and (day := valid_day(r.get('date'))) is not None and day < cutoff]
    baselines = {side: [r for r in history if r.get('venue') == side] for side in ('home', 'away')}
    prior_players = [p for p in players if p['league'] == selected['league'] and p['season'] == selected['season']
                     and (day := valid_day(p.get('date'))) is not None and day < cutoff]
    lineups = season_lineups(prior_players, history, combine_sources=True)
    samples, profiles, sample_baselines = {}, {}, {}
    for side, name in (('home', home), ('away', away)):
        team_rows = [r for r in history if r['team'] == name]
        venue_rows = sorted((r for r in team_rows if r.get('venue') == side),
                            key=lambda r: (r['date'], str(r['fixture'])))
        expanded = len(venue_rows) < 5
        eligible = sorted((r for r in team_rows if r.get('venue') in ('home', 'away')),
                          key=lambda r: (r['date'], str(r['fixture']))) if expanded else venue_rows
        sample = eligible[-last_n:] if last_n else eligible
        baseline = [r for r in history if r.get('venue') in ('home', 'away')] if expanded else baselines[side]
        sample_baselines[side] = baseline
        samples[side] = sample
        profiles[side] = dict(name=name, venue=side, matches=len(sample),
                             sample_scope='all' if expanded else side,
                             sample_label='casa + trasferta' if expanded else ('in casa' if side == 'home' else 'in trasferta'),
                             season_venue_matches=len(venue_rows), season_matches=len(team_rows),
                             unknown_venue=sum(r.get('venue') not in ('home', 'away') for r in team_rows),
                             first=sample[0]['date'] if sample else None,
                             latest=sample[-1]['date'] if sample else None,
                             entity=identity({**selected, 'team':name}, 'teams') if team_rows else None,
                             goal_frequencies=goal_frequencies(sample))
        p = profiles[side]
        p['context_metrics'] = [dict(key=key, label=label, **comparison(sample, baseline, key))
                                for key, label in (('fouls', 'Falli commessi'), ('yellowcards', 'Cartellini gialli'))]
        p['quality'] = [dict(label=label, unit=unit, **paired_ratio(sample, n, d, scale))
                        for n, d, scale, label, unit in (
                            ('shots-on-target', 'shots-total', 100, 'Tiri nello specchio', '%'),
                            ('xg', 'shots-total', 1, 'xG per tiro', ''),
                            ('xga', 'shots-conceded', 1, 'xG per tiro concesso', ''))]
        p['clean_sheets'] = events_summary(sample, 'goals-conceded', lambda v: v == 0)
        p['scoreless'] = events_summary(sample, 'goals', lambda v: v == 0)
        p['recent_form'] = recent_form(team_rows)
        last_day = max((valid_day(r['date']) for r in team_rows), default=None)
        p['activity'] = dict(last_match=last_day.isoformat() if last_day else None,
                             days_to_fixture=(fixture_day - last_day).days if last_day else None,
                             matches_last_14_days=sum(0 < (as_of - valid_day(r['date'])).days <= 14 for r in team_rows))
        p['lineup'] = lineups.get((selected['league'], selected['season'], name))
        p['availability'] = availability.for_fixture(availability_data or {}, selected['league'], selected['season'],
            name, away if side == 'home' else home, fixture_day.isoformat(), (p['lineup'] or {}).get('reference', []))
    directions = []
    for side, other in (('home', 'away'), ('away', 'home')):
        directions.append(dict(side=side, attacker=profiles[side]['name'], defender=profiles[other]['name'],
            metrics=[dict(key=attack, label=label,
                          attack=comparison(samples[side], sample_baselines[side], attack),
                          conceded=comparison(samples[other], sample_baselines[other], defense))
                     for attack, defense, label in METRICS]))
    notes = []
    for side, profile in profiles.items():
        field = profile['sample_label']
        if profile['sample_scope'] == 'all':
            notes.append(f"{profile['name']}: campione ampliato a casa + trasferta perché sono disponibili solo {profile['season_venue_matches']} gare nel campo del prossimo incontro.")
        if profile['matches'] < 5:
            notes.append(f"{profile['name']}: campione ridotto, {profile['matches']} partite {field}.")
        if profile['unknown_venue']:
            notes.append(f"{profile['name']}: {profile['unknown_venue']} partite escluse perché il campo non è noto.")
    return {**result, 'status':'ready' if all(samples.values()) else 'partial',
            'date':fixture_day.isoformat(), 'as_of':as_of.isoformat(),
            'cutoff_exclusive':cutoff.isoformat(), 'schedule_updated':fixture.get('fetched_at'),
            'home':profiles['home'], 'away':profiles['away'], 'directions':directions, 'notes':notes}
