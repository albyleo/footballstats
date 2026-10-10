import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import provider_stats as stats
from starlette.testclient import TestClient
from webapp import app


class StatsTests(unittest.TestCase):
    def test_missing_values_paired_minutes_and_unused_subs(self):
        base = dict(provider="sportmonks", id=1, name="Player", team="Team", league="L",
                    season="S", starter=True, fetched_at="2026-10-10", date="2026-10-09")
        rows = [{**base, "fixture": 1, "minutes": 90, "stats": {"goals": 2}},
                {**base, "fixture": 2, "minutes": 45, "stats": {}},
                {**base, "fixture": 3, "minutes": 0, "stats": {"goals": 0}}]
        with patch.object(stats, "dataset", return_value=(rows, [], [])):
            row = stats.report(metric="goals")["rows"][0]
            self.assertEqual((row["total"], row["per90"], row["covered"], row["matches"]), (2, 2, 1, 2))
            self.assertIsNone(stats.report(metric="assists")["rows"][0]["total"])

    def test_routes_and_empty_archive(self):
        with patch.object(stats, "dataset", return_value=([], [], [])), TestClient(app) as client:
            self.assertEqual(client.get("/providers").status_code, 200)
            result = client.get("/api/providers/report?kind=teams&metric=first-half-goals")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["fixtures"], 0)
            self.assertEqual(client.get("/api/providers/report?metric=invalid").status_code, 400)
            self.assertEqual(client.get("/api/providers/report?min_minutes=bad").status_code, 400)

    def test_recency_filter_before_metric_filter(self):
        base = dict(provider="sportmonks", id=1, name="Player", team="Team", league="L",
                    season="2026/2027", starter=True, fetched_at="2026-10-10", minutes=90)
        rows = [{**base, "fixture": 1, "date": "2026-10-01", "stats": {"goals": 3}},
                {**base, "fixture": 2, "date": "2026-10-02", "stats": {}}]
        with patch.object(stats, "dataset", return_value=(rows, [], [])):
            r=stats.report(metric="goals", last_n=1)["rows"][0]
            self.assertIsNone(r["total"])
            self.assertEqual(r["coverage"]["goals"], 0)
            self.assertEqual(r["matches"], 1)
            self.assertEqual(stats.report(team="Other")["rows"], [])
            self.assertEqual(stats.report(search="absent")["rows"], [])

    def test_starter_continuity_only_for_complete_lineups(self):
        base=dict(provider="sportmonks", id=1, name="Team", team="Team", league="L", season="S",
                  fetched_at="2026-10-10", stats={"goals": 1}, outcome="V")
        rows=[{**base, "fixture": 1, "date": "2026-10-01", "starters": list(range(11))},
              {**base, "fixture": 2, "date": "2026-10-02", "starters": list(range(1,12))}]
        with patch.object(stats,"dataset",return_value=([],rows,[])):
            self.assertEqual(stats.report(kind="teams",metric="goals")["rows"][0]["same_starters"],10)
            rows[0]["starters"]=[]
            self.assertIsNone(stats.report(kind="teams",metric="goals")["rows"][0]["same_starters"])


if __name__ == "__main__":
    unittest.main()
