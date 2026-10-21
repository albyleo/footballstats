"""Acquire upcoming fixture absences with a bounded request budget and cache."""
from datetime import datetime, timedelta, timezone
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import availability
from fetch_provider import Client

INCLUDES = 'participants;league;season;state;sidelined.player;sidelined.type;sidelined.sideline'


def acquire(client, today=None, max_pages=2):
    today = today or datetime.now(timezone.utc).date()
    matches, seen = [], set()
    fetched = []
    for page in range(1, max_pages + 1):
        payload = client.get(f'/fixtures/between/{today}/{today+timedelta(days=7)}',
                             per_page=50, page=page, filters='fixtureLeagues:271,501', include=INCLUDES)
        rows = payload.get('data')
        if not isinstance(rows, list) or payload.get('error') or payload.get('errors'):
            raise ValueError('Absence feed refused or malformed')
        for match in rows:
            if match['id'] in seen:
                raise ValueError('Repeated fixture in absence feed')
            seen.add(match['id']); matches.append(match)
        fetched.append(client.last_fetched_at)
        if not payload.get('pagination', {}).get('has_more'):
            # Mixed cached/live pages are only as fresh as the oldest response.
            return availability.normalize(matches, min(fetched))
        if not rows:
            raise ValueError('Empty page with more data announced')
    raise ValueError('Absence pagination incomplete; existing archive preserved')


def save(data, path=None):
    path = path or availability.PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-requests', type=int, default=2)
    args = parser.parse_args()
    if not 0 <= args.max_requests <= 2:
        parser.error('--max-requests must be between 0 and 2')
    client = Client('sportmonks', args.max_requests)
    try:
        data = acquire(client)
        save(data)
        print(f"Saved {len(data['fixtures'])} scheduled fixtures; {sum(len(f['absences']) for f in data['fixtures'])} fixture-specific absence records.")
        print(f'Network requests: {client.network_requests}; cache hits: {client.cache_hits}')
    except (ValueError, KeyError, TypeError):
        print('Availability acquisition incomplete; saved data unchanged.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
