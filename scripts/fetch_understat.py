"""Manual, cached acquisition of public Understat match data (no API keys)."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / 'data/providers/understat'
LEAGUES = ('Serie_A', 'EPL', 'La_liga', 'Bundesliga', 'Ligue_1')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


class Client:
    def __init__(self, root=ROOT, budget=10):
        self.root, self.budget, self.calls = root, budget, 0

    def get(self, route, filename, refresh=False):
        path = self.root / filename
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding='utf-8'))
        if self.calls >= self.budget:
            raise RuntimeError('Budget richieste raggiunto; riprendere usa i file già salvati.')
        if self.calls:
            time.sleep(1)
        self.calls += 1
        url = 'https://understat.com/' + route
        request = Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                       'X-Requested-With': 'XMLHttpRequest'})
        with urlopen(request, timeout=30) as response:
            raw = response.read()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        data = json.loads(raw)
        required = ('dates', 'teams', 'players') if route.startswith('getLeagueData/') else ('rosters', 'shots')
        if not isinstance(data, dict) or not all(key in data for key in required):
            raise ValueError('Risposta Understat incompleta; file precedente conservato.')
        envelope = dict(provider='understat', source_url=url,
                        fetched_at=datetime.now(timezone.utc).isoformat(), data=data)
        save(path, envelope)
        return envelope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--leagues', nargs='+', choices=LEAGUES, default=list(LEAGUES))
    parser.add_argument('--max-requests', type=int, default=10)
    parser.add_argument('--refresh-leagues', action='store_true')
    parser.add_argument('--refresh-matches', action='store_true')
    args = parser.parse_args()
    if args.max_requests < 0:
        parser.error('--max-requests deve essere >= 0')
    client = Client(budget=args.max_requests)
    try:
        for league in args.leagues:
            envelope = client.get(f'getLeagueData/{league}/{args.season}',
                                  f'league-{league}-{args.season}.json', args.refresh_leagues)
            matches = [m for m in envelope['data']['dates'] if m.get('isResult') is True
                       and m['datetime'][:10] <= datetime.now(timezone.utc).date().isoformat()]
            for match in sorted(matches, key=lambda m: m['datetime'], reverse=True):
                mid = str(match['id'])
                if not mid.isdigit():
                    raise ValueError('ID partita non valido')
                client.get(f'getMatchData/{mid}', f'match-{mid}.json', args.refresh_matches)
            print(f'{league}: {len(matches)} partite concluse in cache', flush=True)
    except Exception as exc:
        print(f'Acquisizione interrotta ({type(exc).__name__}): {exc}', flush=True)
        return 1
    finally:
        print(f'Richieste di rete Understat: {client.calls}; API-Football/Sportmonks: 0', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
