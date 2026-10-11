"""Season starting-frequency reference, never a predicted or tactical XI."""
from collections import defaultdict


def season_lineups(players, teams):
    key = lambda r: (r['provider'], r['league'], r['season'], r['team'])
    groups = defaultdict(list)
    names = { (key(p), p['id']): p['name'] for p in players }
    minutes = defaultdict(float)
    for p in players:
        minutes[(key(p), p['id'])] += p.get('minutes') or 0
    for row in teams:
        groups[key(row)].append(row)
    result = {}
    for group, rows in groups.items():
        rows = sorted(rows, key=lambda r: (r['date'], str(r['fixture'])))
        complete = [r for r in rows if len(set(r.get('starters', []))) == 11]
        counts = defaultdict(int)
        for row in complete:
            for pid in set(row['starters']):
                counts[pid] += 1
        ranked = sorted(counts, key=lambda pid: (-counts[pid], -minutes[(group, pid)], str(pid)))
        reference = ranked[:11]
        latest = rows[-1]
        result[group] = {
            'reference': [{'id': pid, 'name': names.get((group,pid), str(pid)), 'starts': counts[pid]} for pid in reference],
            'sample': len(complete), 'season_matches': len(rows),
            'latest_date': latest['date'],
            'latest_common': len(set(reference) & set(latest.get('starters', [])))
                if len(reference) == 11 and len(set(latest.get('starters', []))) == 11 else None,
            'tie': len(ranked) > 11 and counts[ranked[10]] == counts[ranked[11]],
            'next_common': None, 'next_status': 'Formazione della prossima partita non acquisita',
        }
    return result
