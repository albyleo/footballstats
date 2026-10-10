"""Private PostgreSQL reader. No provider code, credentials or downloads here."""
import os
from threading import Lock
from time import monotonic


class StorageUnavailable(RuntimeError):
    pass


def connect(variable):
    import psycopg
    dsn = os.environ.get(variable, '').strip()
    if not dsn:
        raise StorageUnavailable(f'Configurare {variable} sul backend.')
    try:
        from psycopg.conninfo import conninfo_to_dict
        options = conninfo_to_dict(dsn)
        if options.get('host') not in ('localhost', '127.0.0.1', '::1'):
            if options.get('sslmode') not in ('require', 'verify-ca', 'verify-full'):
                options['sslmode'] = 'require'
        options.update(connect_timeout=10, prepare_threshold=None)
        return psycopg.connect(**options)
    except psycopg.Error:
        raise StorageUnavailable('Connessione al database non disponibile.') from None


def read_snapshot():
    import psycopg
    try:
        with connect('FOOTBALL_DATABASE_URL') as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            conn.execute("SET LOCAL statement_timeout = '15s'")
            state = conn.execute('SELECT revision, metadata FROM football.dataset_state WHERE id=1').fetchone()
            if state is None:
                raise StorageUnavailable('Schema database non inizializzato.')
            players = [r[0] for r in conn.execute('SELECT payload FROM football.player_match_stats ORDER BY provider,fixture_id,player_id,team_id')]
            teams = [r[0] for r in conn.execute('SELECT payload FROM football.team_match_stats ORDER BY provider,fixture_id,team_id')]
            meta = state[1]
            return dict(revision=state[0], players=players, teams=teams,
                        warnings=meta.get('warnings', []), sync=meta.get('sync'),
                        catalog={int(k): v for k,v in meta.get('catalog', {}).items()})
    except psycopg.Error:
        raise StorageUnavailable('Lettura database non disponibile; verificare schema e permessi.') from None


class SnapshotCache:
    """One consistent DB snapshot per instance, at most one refresh per minute."""
    def __init__(self, ttl=60):
        self.ttl = ttl
        self.lock = Lock()
        self.value = None
        self.expires = 0
        self.retry_at = 0

    def get(self):
        with self.lock:
            now = monotonic()
            if self.value is not None and now < self.expires:
                return self.value
            if now < self.retry_at:
                raise StorageUnavailable('Database temporaneamente non disponibile. Riprova tra poco.')
            try:
                value = read_snapshot()
            except StorageUnavailable:
                self.retry_at = now + 15
                raise
            self.value = value
            self.expires = monotonic() + self.ttl
            return value


SNAPSHOTS = SnapshotCache()


def enabled():
    mode = os.environ.get('FOOTBALL_STORAGE', 'local')
    if mode not in ('local', 'supabase'):
        raise StorageUnavailable('FOOTBALL_STORAGE deve essere local oppure supabase.')
    return mode == 'supabase'
