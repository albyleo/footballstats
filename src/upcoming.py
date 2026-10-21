"""Next league fixture from saved schedules, with no network access."""
from datetime import datetime, timezone
import json
from urllib.parse import urlencode
import understat_stats as archive
import availability


# Search terms follow the competition's language, independently of the UI locale.
LINEUP_LANGUAGES = {
    'Serie A': ('it', 'formazioni ufficiali', 'prossima partita'),
    'Premier League': ('en', 'confirmed lineups', 'next match'),
    'Premiership': ('en', 'confirmed lineups', 'next match'),
    'La Liga': ('es', 'alineaciones oficiales', 'próximo partido'),
    'Bundesliga': ('de', 'offizielle Aufstellungen', 'nächstes Spiel'),
    'Ligue 1': ('fr', 'compositions officielles', 'prochain match'),
    'Primeira Liga': ('pt-PT', 'onzes oficiais', 'próximo jogo'),
    'Superliga': ('da', 'officielle startopstillinger', 'næste kamp'),
}


def lineup_search(row, fixture=None):
    """Build a localized search link; this does not acquire or confirm a lineup."""
    language, terms, next_match = LINEUP_LANGUAGES.get(
        row['league'], ('en', 'confirmed lineups', 'next match'))
    opponent = fixture.get('opponent') if fixture else None
    pairing = f"{row['team']} - {opponent}" if opponent else f"{row['team']} {next_match}"
    date = fixture.get('date', '') if fixture else ''
    query = ' '.join(part for part in (pairing, terms, row['league'], date) if part)
    return dict(url='https://www.google.com/search?' + urlencode({'q': query, 'hl': language}),
                query=query, language=language)


def load():
    # Availability acquisition also supplies the free-plan leagues' next fixtures.
    fixtures = [{k:f[k] for k in ('id','league','season','date','home','away','fetched_at')}
                for f in availability.load().get('fixtures', [])]
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
