"""Scheduled ingestion: durable cache, shared budgets, no overlapping import/download.

Run --seed-cache once from the populated local checkout; --cached-only verifies
the durable snapshot/import without contacting any football provider.
"""
import argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import gzip
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from supabase_data import ROOT, load_config, local_snapshot, import_snapshot, connect
from sync_diff import SYNC_LOCK
from fetch_understat import LEAGUES, save
import fetch_provider
from fetch_football_data import _looks_like_csv
from psycopg.types.json import Jsonb
from public_report import public_report

LIMITS = {'understat': 250, 'csv': 6, 'sportmonks': 20, 'football-data.org': 12}
ALLOWED = re.compile(r'data/(?:providers/football-data-org/standings-(?:SA|PL|PD|BL1|FL1|PPL)-\d{4}\.json|raw/(?:I1|E0|SP1|D1|F1|P1)_20\d\d-\d\d\.csv|providers/understat/(?:league-(?:Serie_A|EPL|La_liga|Bundesliga|Ligue_1)-\d{4}|match-\d+)\.json|providers/sportmonks/(?:match-\d+|leagues-page-\d+|standings-\d+|sync-status|availability)\.json)\Z')


def utcnow():
    return datetime.now(timezone.utc)


def completed_today(value, now):
    """Only a full successful acquisition advances this marker, never cache tests."""
    try:
        completed = datetime.fromisoformat(value)
        return completed.tzinfo is not None and completed <= now and completed.astimezone(timezone.utc).date() == now.date()
    except (ValueError, TypeError):
        return False


def coverage(snapshot):
    from premium_stats import observations
    players, teams, warnings = observations(snapshot)
    rows = []
    for league, season in sorted({(r['league'], r['season']) for r in teams}):
        selected = [r for r in teams if (r['league'], r['season']) == (league, season)]
        individual = [r for r in players if (r['league'], r['season']) == (league, season) and (r.get('minutes') or 0) > 0]
        rows.append(dict(league=league, season=season, teams=len({r['team'] for r in selected}),
                         team_rows=len(selected), player_rows=len(individual),
                         latest_match=max(r['date'] for r in selected),
                         shots_on_target=sum(r['stats'].get('shots-on-target') is not None for r in selected)))
    issues = set(warnings + [issue for row in teams for issue in row.get('player_data_issues', [])])
    return dict(leagues=rows, quality_warnings=len(issues))


def write_summary(state):
    """Safe job summary: no connection details, tokens, raw payloads or URLs."""
    target = os.environ.get('GITHUB_STEP_SUMMARY')
    if not target:
        return
    safe = public_report(state)
    text = ['## Football archive sync', '', f"Status: **{safe['status']}**", '',
            f"Stage: {safe.get('stage', 'complete')}",
            f"Changed fixtures: {safe.get('changed_fixtures', '—')}",
            f"Provider requests: {json.dumps({public_report(k): v for k, v in safe.get('requests', {}).items()})}", '']
    if safe.get('reason'):
        text.extend([f"Reason: {safe['reason']}", ''])
    if safe.get('availability'):
        text.extend([f"Squad availability: {safe['availability']['status']}",
                     'Missing or stale absence reports do not imply a fully available squad.', ''])
    text.extend(['| League | Season | Teams | Team observations | Player appearances | Latest match | Shots on target coverage |',
                 '|---|---|---:|---:|---:|---|---|'])
    for row in safe.get('coverage', {}).get('leagues', []):
        text.append(f"| {row['league']} | {row['season']} | {row['teams']} | {row['team_rows']} | {row['player_rows']} | {row['latest_match']} | {row['shots_on_target']}/{row['team_rows']} |")
    text.extend(['', 'Counts refer to the imported sample, not guaranteed full-season coverage.',
                 f"Quality warnings: {safe.get('coverage', {}).get('quality_warnings', '—')}", ''])
    with Path(target).open('a', encoding='utf-8') as handle:
        handle.write('\n'.join(text))


def retry_delay(value, now):
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            seconds = (parsedate_to_datetime(value) - now).total_seconds()
        except (ValueError, TypeError, OverflowError):
            seconds = 21600
    return max(3600, seconds)


class Store:
    def __init__(self, conn):
        self.conn = conn
        self.calls = {p: 0 for p in LIMITS}
        self.last_request = 0

    def get(self, key, default=None):
        row = self.conn.execute('SELECT value FROM football.sync_control WHERE name=%s', [key]).fetchone()
        return row[0] if row else default

    def set(self, key, value):
        self.conn.execute('INSERT INTO football.sync_control VALUES(%s,%s) ON CONFLICT(name) DO UPDATE SET value=excluded.value', [key, Jsonb(value)])

    def persist(self, path):
        relative = path.relative_to(ROOT).as_posix()
        if not ALLOWED.fullmatch(relative):
            raise ValueError('Cache path not allowed')
        self.conn.execute('INSERT INTO football.sync_cache VALUES(%s,%s,%s) ON CONFLICT(path) DO UPDATE SET payload=excluded.payload,mtime=excluded.mtime WHERE football.sync_cache.payload IS DISTINCT FROM excluded.payload',
                          [relative, gzip.compress(path.read_bytes(), mtime=0), path.stat().st_mtime])

    def hydrate(self):
        count = 0
        for relative, payload, mtime in self.conn.execute('SELECT path,payload,mtime FROM football.sync_cache'):
            if not ALLOWED.fullmatch(relative):
                raise ValueError('Unexpected cache path')
            path = ROOT / relative
            if not path.exists() or path.stat().st_mtime < mtime:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix('.tmp')
                tmp.write_bytes(gzip.decompress(payload)); tmp.replace(path)
                os.utime(path, (mtime, mtime))
            count += 1
        return count

    def reserve(self, provider):
        now = utcnow()
        if self.get('blocked:' + provider, False):
            raise RuntimeError(provider + ': acquisition blocked; manual review required')
        if self.get('cooldown:' + provider, 0) > now.timestamp():
            raise RuntimeError(provider + ': cooldown still active')
        key = 'budget:' + now.date().isoformat() + ':' + provider
        # Atomic across all compliant processes; failed HTTP calls count too.
        row = self.conn.execute("INSERT INTO football.sync_control(name,value) VALUES(%s,'1'::jsonb) ON CONFLICT(name) DO UPDATE SET value=to_jsonb((football.sync_control.value::text)::int + 1) WHERE (football.sync_control.value::text)::int < %s RETURNING value", [key, LIMITS[provider]]).fetchone()
        if row is None:
            raise RuntimeError(provider + ': daily request budget exhausted')
        self.calls[provider] += 1

    def fetch(self, provider, url, headers=None):
        self.reserve(provider)
        delay = (7 if provider == 'football-data.org' else 3) - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.monotonic()
        try:
            with urlopen(Request(url, headers=headers or {'User-Agent':'Mozilla/5.0'}), timeout=30) as response:
                raw = response.read(20_000_001)
            if len(raw) > 20_000_000:
                raise ValueError('Response too large')
            return gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        except HTTPError as exc:
            if provider == 'understat' and exc.code in (401, 403):
                self.set('blocked:' + provider, True)
            if exc.code in (403, 429, 503):
                self.set('cooldown:' + provider, utcnow().timestamp() + retry_delay(exc.headers.get('Retry-After'), utcnow()))
            raise RuntimeError(f'{provider}: HTTP {exc.code}; no automatic retries') from None

    def understat(self, route, filename, refresh):
        path = ROOT / 'data/providers/understat' / filename
        if path.exists() and (not refresh or time.time() - path.stat().st_mtime < 86400):
            return json.loads(path.read_text(encoding='utf-8'))
        url = 'https://understat.com/' + route
        raw = self.fetch('understat', url, {'User-Agent':'MyComboDataSync/1.0', 'Accept':'application/json', 'X-Requested-With':'XMLHttpRequest'})
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            self.set('blocked:understat', True)
            raise RuntimeError('understat: unexpected response; manual review required') from None
        required = ('dates','teams','players') if route.startswith('getLeagueData/') else ('rosters','shots')
        if not isinstance(data,dict) or not all(k in data for k in required):
            self.set('blocked:understat', True)
            raise RuntimeError('understat: incomplete response; manual review required')
        envelope = dict(provider='understat',source_url=url,fetched_at=utcnow().isoformat(),data=data)
        save(path, envelope); self.persist(path)
        return envelope


def download(store, season):
    today = utcnow().date()
    cutoff = today - timedelta(days=7)
    # Refresh catalogues first, then only new or recent match details.
    for league in LEAGUES:
        store.stage = 'league fixtures: ' + league
        listing = store.understat(f'getLeagueData/{league}/{season}', f'league-{league}-{season}.json', True)
        matches = [m for m in listing['data']['dates'] if m.get('isResult') is True and m['datetime'][:10] <= today.isoformat()]
        for match in sorted(matches, key=lambda m:m['datetime'], reverse=True):
            mid = str(match['id'])
            if not mid.isdigit(): raise ValueError('Invalid match ID')
            store.understat('getMatchData/' + mid, 'match-' + mid + '.json', match['datetime'][:10] >= cutoff.isoformat())
        print(league + ': cached completed fixtures ' + str(len(matches)), flush=True)
    for code in ('I1','E0','SP1','D1','F1','P1'):
        store.stage = 'season CSV: ' + code
        path = ROOT / f'data/raw/{code}_{season}-{(season+1)%100:02}.csv'
        checked_key=f'checked:csv:{season}:{code}'
        checked=max(path.stat().st_mtime if path.exists() else 0,store.get(checked_key,0))
        if path.exists() and time.time()-checked < 86400: continue
        raw = store.fetch('csv', f'https://football-data.co.uk/mmz4281/{season%100:02}{(season+1)%100:02}/{code}.csv')
        if not _looks_like_csv(raw): raise ValueError('Invalid CSV response')
        if not path.exists() or raw != path.read_bytes():
            path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(path);store.persist(path)
        store.set(checked_key,time.time())
    if not os.environ.get('SPORTMONKS_TOKEN'):
        raise ValueError('SPORTMONKS_TOKEN must be configured for automatic updates')
    if time.time()-store.get('checked:sportmonks',0) < 86400:
        return
    store.stage = 'Sportmonks fixtures'
    class Sportmonks(fetch_provider.Client):
        def get(self, endpoint, **params):
            data = json.loads(store.fetch('sportmonks', self.base + endpoint + '?' + urlencode(params),
                                         {'Authorization':self.key,'Accept':'application/json','User-Agent':'FootballMVP/1.0'}))
            if not isinstance(data,dict) or 'data' not in data or data.get('errors') or data.get('error'):
                raise ValueError('Sportmonks response refused or incomplete')
            self.last_fetched_at=utcnow().isoformat();self.network_requests+=1
            return data
        def save(self, label, payload, quiet=False):
            super().save(label,payload,quiet=True)
            store.persist(ROOT/'data/providers/sportmonks'/f'{label}.json')
    client=Sportmonks('sportmonks',20)
    # Free-plan catalog contains only a few leagues; refuse unnoticed truncation.
    leagues=client.get('/leagues',per_page=50,include='currentSeason')
    if leagues.get('pagination',{}).get('has_more'): raise ValueError('League catalog needs pagination')
    client.save('leagues-page-1',leagues)
    last=store.get('last_success')
    start=min(cutoff.isoformat(),last[:10]) if last else cutoff.isoformat()
    summary=fetch_provider.sync_sportmonks(client,start,today.isoformat())
    if not summary['complete']: raise ValueError('Incomplete Sportmonks sync')
    store.persist(ROOT/'data/providers/sportmonks/sync-status.json')
    store.set('checked:sportmonks',time.time())


def download_standings(store):
    import provider_stats
    token = os.environ.get('SPORTMONKS_TOKEN')
    if not token:
        raise ValueError('SPORTMONKS_TOKEN required')
    client = fetch_provider.Client('sportmonks', 0)
    for league in provider_stats.catalog().values():
        season = league.get('currentseason') or {}
        if league['id'] not in (271, 501) or not season.get('id') or season.get('pending'):
            continue
        sid = int(season['id'])
        path = ROOT / f'data/providers/sportmonks/standings-{sid}.json'
        if path.exists() and time.time() - path.stat().st_mtime < 86400:
            continue
        url = client.base + f'/standings/seasons/{sid}?include=season;stage;group'
        payload = json.loads(store.fetch('sportmonks', url,
            {'Authorization': token, 'Accept': 'application/json', 'User-Agent': 'MyComboDataSync/1.0'}))
        rows = payload.get('data') if isinstance(payload, dict) else None
        if (not isinstance(payload, dict) or payload.get('error') or payload.get('errors') or not isinstance(rows, list)
                or not rows or payload.get('pagination', {}).get('has_more')
                or any(r.get('season_id') != sid or r.get('league_id') != league['id'] for r in rows)):
            raise ValueError('Standings incomplete or refused')
        client.save(f'standings-{sid}', payload, quiet=True)
        store.persist(path)
        print(f"Standings {league['name']}: {len(rows)} teams", flush=True)


def download_availability(store):
    """Optional feed: preserve the last valid report and the main import on failure."""
    from fetch_availability import acquire, save as save_availability
    path = ROOT / 'data/providers/sportmonks/availability.json'
    if path.exists():
        try:
            checked = datetime.fromisoformat(json.loads(path.read_text(encoding='utf-8'))['fetched_at'])
            if 0 <= (utcnow() - checked).total_seconds() < 86400:
                return {'status':'cached'}
        except (ValueError, TypeError, KeyError):
            pass
    if time.time() - store.get('checked:availability-attempt', 0) < 86400:
        return {'status':'deferred_after_failure'}
    store.set('checked:availability-attempt', time.time())
    try:
        class AvailabilityClient(fetch_provider.Client):
            def get(self, endpoint, **params):
                raw = store.fetch('sportmonks', self.base + endpoint + '?' + urlencode(params),
                    {'Authorization':self.key, 'Accept':'application/json', 'User-Agent':'MyComboDataSync/1.0'})
                self.last_fetched_at = utcnow().isoformat()
                return json.loads(raw)
        data = acquire(AvailabilityClient('sportmonks', 0), utcnow().date(), max_pages=2)
        save_availability(data, path)
        store.persist(path)
        return {'status':'updated', 'fixtures':len(data['fixtures'])}
    except Exception as exc:
        # Absence access is optional. No raw provider response or credentials in logs.
        print('Availability not refreshed; previous report retained (' + type(exc).__name__ + ').', flush=True)
        return {'status':'unavailable', 'error_type':type(exc).__name__}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed-cache',action='store_true')
    parser.add_argument('--cached-only',action='store_true')
    parser.add_argument('--standings-only',action='store_true')
    parser.add_argument('--season',type=int)
    parser.add_argument('--if-needed',action='store_true',help='Skip after a successful full sync today (UTC)')
    args=parser.parse_args()
    if args.if_needed and (args.seed_cache or args.cached_only or args.standings_only or args.season):
        parser.error('--if-needed applies only to the current full scheduled sync')
    if args.standings_only and (args.cached_only or args.seed_cache):
        parser.error('--standings-only cannot be combined with cache-only modes')
    load_config();fetch_provider.load_env()
    with connect('FOOTBALL_IMPORT_DATABASE_URL') as conn:
        conn.autocommit=True
        if conn.info.host.endswith('.pooler.supabase.com') and conn.info.port == 6543:
            raise ValueError('Use the session pooler on port 5432 for session advisory locks')
        if not conn.execute('SELECT pg_try_advisory_lock(%s)',[SYNC_LOCK]).fetchone()[0]:
            write_summary({'status':'skipped','reason':'Another sync holds the database lock.'})
            print('Another sync/import is running: skipped.');return 0
        store=Store(conn)
        store.stage = 'restore persistent cache'
        try:
            if args.if_needed and completed_today(store.get('last_success'), utcnow()):
                state = dict(status='skipped', time=utcnow().isoformat(), reason='Full sync already succeeded today.', requests=store.calls)
                store.set('last_attempt', state)
                write_summary(state)
                print('Full sync already succeeded today; no provider requests.');return 0
            if args.seed_cache:
                paths=[p for p in (ROOT/'data').rglob('*') if p.is_file() and ALLOWED.fullmatch(p.relative_to(ROOT).as_posix())]
                for path in paths: store.persist(path)
                print('Seeded cached files:',len(paths));return 0
            if not store.hydrate(): raise ValueError('Persistent cache empty: run --seed-cache first')
            store.set('last_run',{'status':'running','time':utcnow().isoformat(),'cached_only':args.cached_only})
            availability_status = {'status':'not_requested'}
            if not args.cached_only and not args.standings_only:
                now=utcnow();season=args.season or (now.year if now.month>=7 else now.year-1)
                download(store,season)
            if not args.cached_only:
                store.stage = 'Sportmonks standings'
                download_standings(store)
                from fetch_org_standings import download as download_org
                store.stage = 'football-data.org standings'
                download_org(store, ROOT, utcnow())
            if not args.cached_only and not args.standings_only:
                store.stage = 'Sportmonks availability'
                availability_status = download_availability(store)
            store.stage = 'normalize and validate'
            snapshot = local_snapshot()
            inventory = coverage(snapshot)
            store.stage = 'Supabase import'
            result=import_snapshot(conn,snapshot)
            if not args.cached_only and not args.standings_only: store.set('last_success',utcnow().isoformat())
            state = {'status':'success','stage':'complete','time':utcnow().isoformat(),'cached_only':args.cached_only,
                     'requests':store.calls,'coverage':inventory,'availability':availability_status,**result}
            store.set('last_run',state)
            write_summary(state)
            print(json.dumps(public_report({'requests':store.calls,**result})),flush=True)
            return 0
        except Exception as exc:
            # Never emit raw provider/connection exception text or credentials.
            reason = str(exc) if type(exc) is RuntimeError else type(exc).__name__
            state = {'status':'failed','stage':store.stage,'time':utcnow().isoformat(),'reason':reason,'requests':store.calls}
            store.set('last_run',state)
            write_summary(state)
            print(public_report('Sync failed at '+store.stage+': '+reason+'. Cached responses retained; imports are atomic.'),file=sys.stderr)
            return 1
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)',[SYNC_LOCK])


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print('Sync setup failed ('+type(exc).__name__+'); check migration and secrets.',file=sys.stderr)
        raise SystemExit(1)
