"""Offline checks: no credentials or API quota required."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import fetch_provider as feed


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root_patch = patch.object(feed, "ROOT", Path(self.temp.name))
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def client(self, provider):
        return feed.Client(provider, budget=2)

    @patch.dict(feed.os.environ, {"API_FOOTBALL_KEY": "test-secret", "SPORTMONKS_TOKEN": "test-secret"})
    def test_auth_and_budget(self):
        for provider, header in [("api-football", "X-apisports-key"), ("sportmonks", "Authorization")]:
            client = self.client(provider)
            with patch.object(feed, "urlopen", return_value=io.BytesIO(b'{"data": []}')) as request:
                client.get("/leagues")
                sent = request.call_args.args[0]
                self.assertEqual(sent.get_header(header), "test-secret")
                self.assertNotIn("test-secret", sent.full_url)
            # Same request comes from cache, even with exhausted request budget.
            client.remaining = 0
            self.assertEqual(client.get("/leagues"), {"data": []})
            client.remaining = 0
            with self.assertRaisesRegex(ValueError, "budget"):
                client.get("/different")

    @patch.dict(feed.os.environ, {"API_FOOTBALL_KEY": "test-secret"})
    def test_api_error_and_http_error(self):
        client = self.client("api-football")
        with patch.object(feed, "urlopen", return_value=io.BytesIO(b'{"errors":{"plan":"test-secret"}}')):
            with self.assertRaisesRegex(ValueError, "API refused") as error:
                client.get("/fixtures")
            self.assertNotIn("test-secret", str(error.exception))
        with patch.object(feed, "urlopen", side_effect=HTTPError("url", 429, "test-secret", {}, None)):
            with self.assertRaisesRegex(ValueError, "HTTP 429"):
                client.get("/fixtures")

    @patch.dict(feed.os.environ, {"SPORTMONKS_TOKEN": "test-secret"})
    def test_storage_removes_token_links_and_preserves_null(self):
        client = self.client("sportmonks")
        with tempfile.TemporaryDirectory() as temp, patch.object(feed, "ROOT", Path(temp)):
            client.save("test", {"data": {"shots": None, "goals": 0},
                                 "pagination": {"has_more": True, "next_page": "https://example/?api_token=test-secret"}})
            raw = (Path(temp) / "data/providers/sportmonks/test.json").read_text()
            self.assertNotIn("test-secret", raw)
            saved = json.loads(raw)
            self.assertIsNone(saved["data"]["shots"])
            self.assertEqual(saved["data"]["goals"], 0)
            self.assertTrue(saved["pagination"]["has_more"])

    @patch.dict(feed.os.environ, {"SPORTMONKS_TOKEN": "test-secret"})
    def test_sync_pagination_and_offline_repeat(self):
        client=feed.Client("sportmonks",budget=2)
        first={"data":[{"id":1,"state":{"state":"FT"}}],"pagination":{"has_more":True}}
        second={"data":[{"id":2,"state":{"state":"FT"}}],"pagination":{"has_more":False}}
        with patch.object(feed,"urlopen",side_effect=[io.BytesIO(json.dumps(first).encode()),io.BytesIO(json.dumps(second).encode())]):
            result=feed.sync_sportmonks(client,"2026-07-24","2026-10-10")
        self.assertEqual(result["fixtures"],2)
        self.assertTrue(result["complete"])
        repeat=feed.Client("sportmonks",budget=1)
        with patch.object(feed,"urlopen",side_effect=AssertionError("Unexpected network call")):
            result=feed.sync_sportmonks(repeat,"2026-07-24","2026-10-10")
        self.assertEqual(result["network_requests"],0)
        self.assertEqual(result["cache_hits"],2)

    @patch.dict(feed.os.environ, {"SPORTMONKS_TOKEN": "test-secret"})
    def test_partial_sync_stops_at_budget(self):
        client=feed.Client("sportmonks",budget=1)
        payload={"data":[{"id":1,"state":{"state":"FT"}}],"pagination":{"has_more":True}}
        with patch.object(feed,"urlopen",return_value=io.BytesIO(json.dumps(payload).encode())):
            with self.assertRaisesRegex(ValueError,"budget"):
                feed.sync_sportmonks(client,"2026-07-24","2026-10-10")
        status=json.loads((feed.ROOT/"data/providers/sportmonks/sync-status.json").read_text())
        self.assertFalse(status["complete"])
        self.assertEqual(status["fixtures"],1)


if __name__ == "__main__":
    unittest.main()
