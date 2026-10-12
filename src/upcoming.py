"""Next league fixture from saved schedules, with no network access."""
from datetime import datetime, timezone
import json
import understat_stats as archive


def load():
    fixtures = []
    for path in sorted(archive.ROOT.glob('league-*.json')):
        code, year = path.stem.removeprefix('league-').rsplit('-', 1)
        if code not in archive.LEAGUES:
            continue
        envelope = json.loads(path.read_text(encoding='utf-8'))
        league = archive.LEAGUES[code][1]
        for match in envelope['data']['dates']:
            if match.get('isResult') is not False:
                continue
            day = match.get('datetime', '')[:10]
            try:
                datetime.strptime(day, '%Y-%m-%d')
            except ValueError:
                continue
            home, away = match.get('h', {}).get('title'), match.get('a', {}).get('title')
            if home and away:
                fixtures.append(dict(id=str(match['id']), league=league,
                    season=f'{year}/{int(year)+1}', date=day,
                    home=archive.name(league, home), away=archive.name(league, away),
                    fetched_at=envelope.get('fetched_at')))
    return fixtures


def index(fixtures, today=None):
    # Source timezone is not guaranteed: publish dates only, including today.
    today = today or datetime.now(timezone.utc).date().isoformat()
    result = {}
    for fixture in sorted(fixtures, key=lambda f: (f['date'], f['id'])):
        if fixture['date'] < today:
            continue
        for side, other in (('home', 'away'), ('away', 'home')):
            key = (fixture['league'], fixture['season'], fixture[side])
            result.setdefault(key, dict(opponent=fixture[other], date=fixture['date'],
                                       venue=side, fetched_at=fixture.get('fetched_at')))
    return result


def lookup(indexed, row):
    return indexed.get((row['league'], row['season'], row['team']))
