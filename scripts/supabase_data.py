"""Import existing local data into Supabase; never calls football providers."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit, urlunsplit, quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import provider_stats
import standings
import upcoming
import availability
from cloud_store import connect, StorageUnavailable
from sync_diff import changed_fixtures, SYNC_LOCK


def load_config():
    names = {'FOOTBALL_ADMIN_DATABASE_URL', 'FOOTBALL_IMPORT_DATABASE_URL'}
    for filename in ('.env', '.env.supabase'):
        path = ROOT / filename
        if path.exists():
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                key, sep, value = line.partition('=')
                if sep and key.strip() in names:
                    # Ignore empty placeholders so generated credentials can be used.
                    value = value.strip().strip('\"\'')
                    if value:
                        os.environ.setdefault(key.strip(), value)


def local_snapshot():
    players, teams, warnings = provider_stats.dataset()
    status = provider_stats.ROOT / 'sync-status.json'
    return dict(players=players, teams=teams, warnings=warnings,
                standings=standings.load(), upcoming=upcoming.load(), availability=availability.load(),
                catalog=provider_stats.catalog(),
                sync=json.loads(status.read_text()) if status.exists() else None)


def counts(snapshot):
    return dict(fixtures=len({(r['provider'], str(r['fixture'])) for r in snapshot['teams']}),
                teams=len({(r['provider'], str(r['id'])) for r in snapshot['teams']}),
                players=len({(r['provider'], str(r['id'])) for r in snapshot['players']}),
                team_rows=len(snapshot['teams']), player_rows=len(snapshot['players']))


def import_snapshot(conn, snapshot):
    """One transaction: readers see either the previous archive or the new one."""
    from psycopg.types.json import Jsonb
    if not snapshot['teams']:
        raise ValueError('Archivio locale vuoto: importazione annullata.')
    if snapshot['warnings']:
        raise ValueError('Archivio con avvisi: correggerli prima di importare.')
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout = '120s'")
        conn.execute("SET LOCAL lock_timeout = '10s'")
        conn.execute('SELECT pg_advisory_xact_lock(%s)', [SYNC_LOCK])
        conn.execute('SELECT id FROM football.dataset_state WHERE id=1 FOR UPDATE')
        previous = conn.execute('SELECT metadata FROM football.dataset_state WHERE id=1').fetchone()[0]
        old_players = [r[0] for r in conn.execute('SELECT payload FROM football.player_match_stats')]
        old_teams = [r[0] for r in conn.execute('SELECT payload FROM football.team_match_stats')]
        changed = changed_fixtures(snapshot, old_players, old_teams)
        merged_catalog = {**previous.get('catalog', {}), **{str(k):v for k,v in snapshot['catalog'].items()}}
        merged_standings = {**previous.get('standings', {}), **snapshot.get('standings', {})}
        merged_availability = snapshot.get('availability') or previous.get('availability', {})
        if not changed and snapshot.get('upcoming', previous.get('upcoming', [])) == previous.get('upcoming', []) and merged_catalog == previous.get('catalog', {}) and merged_standings == previous.get('standings', {}) and merged_availability == previous.get('availability', {}):
            return {**counts(snapshot), 'changed_fixtures': 0, 'updated': False}
        original_counts = counts(snapshot)
        snapshot = {**snapshot, **{kind: [r for r in snapshot[kind]
                    if (r['provider'], str(r['fixture'])) in changed] for kind in ('teams','players')}}
        fixture_rows = {}
        team_rows = {}
        player_rows = {}
        for row in snapshot['teams']:
            provider, fixture, tid = row['provider'], str(row['fixture']), str(row['id'])
            fixture_rows[(provider, fixture)] = (provider, fixture, row['date'], row['league'], row['season'])
            team_rows[(provider, tid)] = (provider, tid, row['name'])
        for row in snapshot['players']:
            player_rows[(row['provider'], str(row['id']))] = (row['provider'], str(row['id']), row['name'])
        with conn.cursor() as cur:
            cur.executemany('INSERT INTO football.teams VALUES (%s,%s,%s) ON CONFLICT(provider,id) DO UPDATE SET name=excluded.name', team_rows.values())
            cur.executemany('INSERT INTO football.players VALUES (%s,%s,%s) ON CONFLICT(provider,id) DO UPDATE SET name=excluded.name', player_rows.values())
            cur.executemany('INSERT INTO football.fixtures VALUES (%s,%s,%s,%s,%s) ON CONFLICT(provider,id) DO UPDATE SET match_date=excluded.match_date,league=excluded.league,season=excluded.season', fixture_rows.values())
            # Replace observations only for imported fixtures, preserving other seasons.
            cur.executemany('DELETE FROM football.player_match_stats WHERE provider=%s AND fixture_id=%s', fixture_rows.keys())
            cur.executemany('DELETE FROM football.team_match_stats WHERE provider=%s AND fixture_id=%s', fixture_rows.keys())
            cur.executemany('INSERT INTO football.team_match_stats VALUES (%s,%s,%s,%s)',
                            [(r['provider'],str(r['fixture']),str(r['id']),Jsonb(r)) for r in snapshot['teams']])
            cur.executemany('INSERT INTO football.player_match_stats VALUES (%s,%s,%s,%s,%s)',
                            [(r['provider'],str(r['fixture']),str(r['id']),str(r['team_id']),Jsonb(r)) for r in snapshot['players']])
        previous = conn.execute('SELECT metadata FROM football.dataset_state WHERE id=1').fetchone()[0]
        merged_catalog = {**previous.get('catalog', {}), **{str(k):v for k,v in snapshot['catalog'].items()}}
        metadata = {**previous, 'availability': merged_availability, 'upcoming': snapshot.get('upcoming', previous.get('upcoming', [])), 'catalog': merged_catalog, 'standings': merged_standings, 'sync': snapshot['sync'], 'warnings': snapshot['warnings']}
        conn.execute('UPDATE football.dataset_state SET revision=revision+1,metadata=%s,updated_at=now() WHERE id=1', [Jsonb(metadata)])
    return {**original_counts, 'changed_fixtures': len(changed), 'updated': True}


def provision():
    """Generate separate login passwords into a Git-ignored file, never stdout."""
    from psycopg import sql
    source = os.environ.get('FOOTBALL_ADMIN_DATABASE_URL', '')
    parsed = urlsplit(source)
    if parsed.scheme not in ('postgres', 'postgresql') or not parsed.hostname:
        raise ValueError('Inserire la URL PostgreSQL del Session pooler in FOOTBALL_ADMIN_DATABASE_URL.')
    destination = ROOT / '.env.supabase'
    if destination.exists():
        raise ValueError('.env.supabase esiste già: nessuna password modificata.')
    suffix = '.' + parsed.username.split('.', 1)[1] if '.' in parsed.username else ''
    credentials = {}
    for role, variable, port in [('football_reader', 'FOOTBALL_DATABASE_URL', 6543),
                                  ('football_importer', 'FOOTBALL_IMPORT_DATABASE_URL', 5432)]:
        password = secrets.token_urlsafe(36)
        # On direct/local hosts use their supplied port, not the pooler ports.
        pooled = '.pooler.supabase.com' in parsed.hostname
        host = f'[{parsed.hostname}]' if ':' in parsed.hostname else parsed.hostname
        netloc = f'{quote(role+suffix)}:{quote(password)}@{host}:{port if pooled else parsed.port or 5432}'
        credentials[role] = (password, variable, urlunsplit((parsed.scheme, netloc, parsed.path, 'sslmode=require', '')))
    with connect('FOOTBALL_ADMIN_DATABASE_URL') as conn:
        for role in credentials:
            if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', [role]).fetchone():
                raise ValueError('Eseguire prima la migrazione SQL nel progetto Supabase.')
        # Exclusive creation prevents overwriting existing credentials.
        with destination.open('x', encoding='utf-8') as handle:
            handle.write('FOOTBALL_STORAGE=supabase\n')
            for password, variable, url in credentials.values():
                handle.write(f'{variable}={url}\n')
        try:
            for role, (password, _, _) in credentials.items():
                conn.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
            conn.commit()
        except Exception:
            destination.unlink()
            raise
    print('Credenziali create in .env.supabase (file privato escluso da Git).')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['dry-run', 'provision', 'import', 'check'])
    args = parser.parse_args()
    load_config()
    try:
        if args.action == 'provision':
            provision()
        elif args.action in ('dry-run', 'import'):
            snapshot = local_snapshot()
            print(json.dumps(counts(snapshot)))
            print('Avvisi:', len(snapshot['warnings']))
            report = provider_stats.report('teams', 'goals', snapshot=snapshot)
            print('Partite distinte nel report (fonti riconciliate):', report['fixtures'])
            for warning in report['warnings']:
                print('Qualità dati:', warning)
            if args.action == 'import':
                with connect('FOOTBALL_IMPORT_DATABASE_URL') as conn:
                    result = import_snapshot(conn, snapshot)
                    print('Partite nuove/modificate:', result['changed_fixtures'])
                print('Importazione completata. Chiamate ai feed: 0.')
        else:
            with connect('FOOTBALL_IMPORT_DATABASE_URL') as conn:
                for table in ('fixtures', 'teams', 'players', 'player_match_stats', 'team_match_stats'):
                    print(table, conn.execute('SELECT count(*) FROM football.' + table).fetchone()[0])
        return 0
    except (ValueError, StorageUnavailable) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print('Operazione database fallita. Verificare migrazione, connessione e permessi; credenziali non mostrate.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
