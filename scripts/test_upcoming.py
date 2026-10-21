import sys
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import upcoming


class UpcomingTests(unittest.TestCase):
    def test_lineup_search_uses_opponent_date_and_competition_language(self):
        row = dict(team='Vitória SC', league='Primeira Liga')
        fixture = dict(opponent='Sporting CP', date='2026-10-25', venue='away')
        result = upcoming.lineup_search(row, fixture)
        params = parse_qs(urlsplit(result['url']).query)
        self.assertEqual(params['hl'], ['pt-PT'])
        self.assertEqual(params['q'], ['Vitória SC - Sporting CP onzes oficiais Primeira Liga 2026-10-25'])
        self.assertNotIn('formazioni', result['query'])

    def test_lineup_search_missing_calendar_and_url_encoding(self):
        result = upcoming.lineup_search(dict(team='A&B + FC', league='La Liga'))
        url = urlsplit(result['url'])
        params = parse_qs(url.query)
        self.assertEqual(url.netloc, 'www.google.com')
        self.assertEqual(params['hl'], ['es'])
        self.assertEqual(params['q'], ['A&B + FC próximo partido alineaciones oficiales La Liga'])
        self.assertEqual(set(params), {'q', 'hl'})

    def test_lineup_search_covers_current_competitions(self):
        expected = {'Serie A': 'it', 'Premier League': 'en', 'Premiership': 'en',
                    'La Liga': 'es', 'Bundesliga': 'de', 'Ligue 1': 'fr',
                    'Primeira Liga': 'pt-PT', 'Superliga': 'da'}
        for league, language in expected.items():
            with self.subTest(league=league):
                result = upcoming.lineup_search(dict(team='Team', league=league))
                self.assertEqual(result['language'], language)
        self.assertEqual(upcoming.lineup_search(dict(team='Team', league='Unknown'))['language'], 'en')

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
