import os
from pathlib import Path
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import cloud_store
import provider_stats
import webapp
from report_cache import ReportCache
from starlette.testclient import TestClient
from supabase_data import local_snapshot, counts


class CloudTests(unittest.TestCase):
    def test_connection_uses_tls_and_hides_errors(self):
        import psycopg
        with patch.dict(os.environ, {'FOOTBALL_DATABASE_URL':'postgresql://reader:test-password@example.com/db?sslmode=disable'}), \
             patch.object(psycopg, 'connect', side_effect=psycopg.OperationalError('test-password')) as connect:
            with self.assertRaises(cloud_store.StorageUnavailable) as error:
                cloud_store.connect('FOOTBALL_DATABASE_URL')
            self.assertNotIn('test-password', str(error.exception))
            self.assertEqual(connect.call_args.kwargs['sslmode'], 'require')
            self.assertIsNone(connect.call_args.kwargs['prepare_threshold'])

    def test_normalized_snapshot_preserves_reports(self):
        snapshot = local_snapshot()
        # Simulate a JSON round trip through Postgres (catalog keys become strings).
        import json
        restored = json.loads(json.dumps(snapshot))
        restored['catalog'] = {int(k):v for k,v in restored['catalog'].items()}
        for kind, metric in [('teams','first-half-goals'), ('players','goals'), ('players','fouls')]:
            expected = provider_stats.report(kind, metric)
            with (patch.object(provider_stats, 'dataset', side_effect=AssertionError('Local file access')),
                  patch.object(provider_stats, 'catalog', side_effect=AssertionError('Local catalog access'))):
                self.assertEqual(expected, provider_stats.report(kind, metric, snapshot=restored))

    def test_concurrent_refreshes_share_one_db_read(self):
        cache = cloud_store.SnapshotCache()
        with patch.object(cloud_store, 'read_snapshot', return_value={'revision': 1}) as read:
            with ThreadPoolExecutor(max_workers=8) as pool:
                values = list(pool.map(lambda _: cache.get(), range(24)))
            self.assertEqual(read.call_count, 1)
            self.assertTrue(all(v == {'revision':1} for v in values))

    def test_failure_does_not_fallback_or_retry_on_every_click(self):
        cache = cloud_store.SnapshotCache()
        with patch.object(cloud_store, 'read_snapshot', side_effect=cloud_store.StorageUnavailable('Unavailable')) as read:
            for _ in range(3):
                with self.assertRaises(cloud_store.StorageUnavailable):
                    cache.get()
            self.assertEqual(read.call_count, 1)

    def test_http_cloud_path_and_failure(self):
        snapshot = dict(revision=4, players=[], teams=[], catalog={}, sync=None, warnings=[])
        with (patch.dict(os.environ, {'FOOTBALL_STORAGE':'supabase'}),
             patch.object(webapp, 'REPORT_CACHE', ReportCache()),
             patch.object(cloud_store.SNAPSHOTS, 'get', return_value=snapshot) as read,
             patch.object(provider_stats, 'dataset', side_effect=AssertionError('Local fallback')),
             TestClient(webapp.app) as client):
            self.assertEqual(client.get('/api/providers/report').json()['fixtures'], 0)
            read.side_effect = cloud_store.StorageUnavailable('Database non disponibile')
            failed = client.get('/api/providers/report')
            self.assertEqual(failed.status_code, 503)
            self.assertEqual(failed.headers['cache-control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
