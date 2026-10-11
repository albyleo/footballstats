"""Offline checks for quota isolation, response caching and the web/MCP boundary."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import provider_stats
import report_cache
from report_cache import ReportCache
from starlette.testclient import TestClient
import webapp


class CacheTests(unittest.TestCase):
    def test_concurrent_visitors_share_one_calculation(self):
        cache = ReportCache()
        build = Mock(return_value={"rows": [1]})
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: cache.get(("teams",), "revision1", build), range(24)))
        self.assertEqual(build.call_count, 1)
        self.assertEqual(sum(r[2] for r in results), 23)
        self.assertEqual(len({r[1] for r in results}), 1)

    def test_expiry_and_file_revision_invalidate(self):
        cache = ReportCache(ttl=60)
        build = Mock(side_effect=[{"n": 1}, {"n": 2}, {"n": 3}])
        with patch.object(report_cache, "monotonic", return_value=100):
            first = cache.get("filter", "revision1", build)
        with patch.object(report_cache, "monotonic", return_value=159):
            self.assertTrue(cache.get("filter", "revision1", build)[2])
        with patch.object(report_cache, "monotonic", return_value=160):
            expired = cache.get("filter", "revision1", build)
            changed = cache.get("filter", "revision2", build)
        self.assertFalse(expired[2])
        self.assertFalse(changed[2])
        self.assertEqual(len({first[1], expired[1], changed[1]}), 3)

    def test_memory_and_filter_limits(self):
        cache = ReportCache(max_entries=2, max_bytes=14)
        build = Mock(return_value={"a": 1})  # Seven serialized bytes.
        for key in ("a", "b", "c"):
            cache.get(key, 1, build)
        self.assertTrue(cache.get("c", 1, build)[2])
        self.assertFalse(cache.get("a", 1, build)[2])
        self.assertLessEqual(cache._bytes, 14)
        oversized = Mock(return_value={"large": "x" * 100})
        self.assertFalse(cache.get("large", 1, oversized)[2])
        self.assertFalse(cache.get("large", 1, oversized)[2])

    def test_revision_tracks_files_and_sync_status(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(provider_stats.csv_stats, "files", return_value=[]):
            root = Path(temp)
            empty = provider_stats.input_revision(root)
            fixture = root / "match-1.json"
            fixture.write_text("{}")
            added = provider_stats.input_revision(root)
            fixture.write_text('{"goals": 1}')
            changed = provider_stats.input_revision(root)
            (root / "sync-status.json").write_text('{"complete": false}')
            status = provider_stats.input_revision(root)
            fixture.unlink()
            removed = provider_stats.input_revision(root)
            self.assertEqual(len({empty, added, changed, status, removed}), 5)

    def test_http_reload_revalidation_and_zero_external_requests(self):
        with patch.object(webapp, "REPORT_CACHE", ReportCache()), \
             patch.object(provider_stats, "report", wraps=provider_stats.report) as build, \
             patch.object(provider_stats, "input_revision", return_value="v1") as revision, \
             patch("socket.create_connection", side_effect=AssertionError("Unexpected outbound connection")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected feed call")), \
             TestClient(webapp.app) as client:
            url = "/api/providers/report?kind=teams&metric=first-half-goals"
            first = client.get(url)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.headers["x-report-cache"], "MISS")
            second = client.get(url)
            self.assertEqual(second.headers["x-report-cache"], "HIT")
            self.assertEqual(build.call_count, 1)
            conditional = client.get(url, headers={"If-None-Match": "W/" + first.headers["etag"]})
            self.assertEqual(conditional.status_code, 304)
            self.assertEqual(conditional.content, b"")
            revision.return_value = "v2"
            self.assertEqual(client.get(url).headers["x-report-cache"], "MISS")
            self.assertEqual(build.call_count, 2)
            self.assertEqual(client.get(url + "&search=Arsenal").headers["x-report-cache"], "MISS")
            self.assertEqual(client.get(url + "&search=" + "a" * 129).status_code, 400)
            before_home = build.call_count
            home, dashboard = client.get("/"), client.get("/providers")
            self.assertEqual(home.status_code, 200)
            self.assertIn('MyCombo srl', home.text)
            self.assertNotEqual(home.content, dashboard.content)
            self.assertEqual(build.call_count, before_home)
            for path in ("/api/query", "/api/leaderboard"):
                self.assertEqual(client.post(path, json={"sql": "SELECT 1"}).status_code, 404)
            for path in ("/api/meta", "/api/find_team", "/static/app.js"):
                self.assertEqual(client.get(path).status_code, 404)

    def test_web_import_and_start_without_duckdb_or_mcp(self):
        src = str(Path(__file__).resolve().parents[1] / "src")
        code = '''
import builtins, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'duckdb', 'mcp', 'db', 'fetch_provider'}:
        raise AssertionError('Web imported optional component: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import webapp
with patch.object(sys, 'argv', ['webapp.py']), patch.object(webapp.uvicorn, 'run') as run:
    assert webapp.main() == 0
    run.assert_called_once()
'''
        result = subprocess.run([sys.executable, "-c", code, src], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
