import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import upcoming


class UpcomingTests(unittest.TestCase):
    def test_order_venue_season_and_expired_dates(self):
        base = dict(league='L', season='S', home='A', away='B')
        rows = [{**base, 'id':'2', 'date':'2026-10-20'},
                {**base, 'id':'1', 'date':'2026-10-12'},
                {**base, 'id':'0', 'date':'2026-10-11'}]
        result = upcoming.index(rows, today='2026-10-12')
        self.assertEqual(result[('L','S','A')]['date'], '2026-10-12')
        self.assertEqual(result[('L','S','B')]['opponent'], 'A')
        self.assertEqual(result[('L','S','B')]['venue'], 'away')
        self.assertIsNone(upcoming.lookup(result, dict(league='L',season='old',team='A')))
        self.assertEqual(upcoming.index(rows, today='2026-10-21'), {})


if __name__ == '__main__': unittest.main()
