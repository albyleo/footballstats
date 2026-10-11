import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import standings
import provider_stats
from fetch_org_standings import normalize, download, COMPETITIONS
from unittest.mock import Mock, patch
from datetime import datetime, timezone
import tempfile
from scheduled_sync import ALLOWED


class StandingsTests(unittest.TestCase):
    def envelope(self):
        return {'standings-10': {'fetched_at': '2026-10-12T07:00:00Z', 'data': [
            {'league_id': 271, 'season_id': 10, 'participant_id': 1, 'position': 4,
             'points': 12, 'season': {'name': '2026/2027'}, 'stage': {'name': 'Regular Season'}}]}}

    def test_provider_position_not_recalculated_with_filters(self):
        base = dict(provider='sportmonks', league='Superliga', league_id=271,
                    season='2026/2027', id=1, name='A', team='A', fetched_at='now')
        teams = [{**base, 'fixture': i, 'date': f'2026-10-0{i}', 'stats': {'goals': 4}}
                 for i in (1, 2)]
        snapshot = dict(teams=teams, players=[], warnings=[], catalog={}, sync=None, standings=self.envelope())
        for last_n in (0, 1):
            row = provider_stats.report(kind='teams', metric='goals', team='A', last_n=last_n, snapshot=snapshot)['rows'][0]
            self.assertEqual(row['standing']['position'], 4)
            self.assertEqual(row['standing']['points'], 12)
        snapshot['standings'] = {}
        self.assertIsNone(provider_stats.report(kind='teams', snapshot=snapshot)['rows'][0]['standing'])

    def test_season_and_provider_must_match(self):
        values = standings.index(self.envelope())
        self.assertIn(('sportmonks', '271', '2026/2027', '1'), values)
        self.assertNotIn(('sportmonks', '271', '2025/2026', '1'), values)
        self.assertNotIn(('understat', '271', '2026/2027', '1'), values)

    def test_ambiguous_stages_and_invalid_positions_are_missing(self):
        data = self.envelope()
        data['standings-10']['data'].append(copy.deepcopy(data['standings-10']['data'][0]))
        self.assertEqual(standings.index(data), {})
        for position in (None, 0, -1, True, '1'):
            data = self.envelope();data['standings-10']['data'][0]['position'] = position
            self.assertEqual(standings.index(data), {})

    def org_payload(self):
        return dict(competition={'code': 'SA'}, season={'startDate': '2026-08-23', 'endDate': '2027-05-30'},
                    standings=[dict(type='TOTAL', stage='REGULAR_SEASON', group='Matchday', table=[
                        dict(position=4, points=12, playedGames=6, team={'id': 1, 'name': 'Como 1907', 'shortName': 'Como 1907'})])])

    def test_org_total_only_exact_alias_and_season(self):
        payload = self.org_payload()
        payload['standings'].append({**payload['standings'][0], 'type': 'HOME'})
        rows, year = normalize(payload, 'SA')
        self.assertEqual(year, 2026)
        values = standings.index({'org': dict(provider='football-data.org', data=rows)})
        team = dict(provider='understat', league='Serie A', season='2026/2027', id=99, team='Como')
        self.assertEqual(standings.lookup(values, team)['position'], 4)
        self.assertIsNone(standings.lookup(values, {**team, 'season': '2025/2026'}))
        self.assertIsNone(standings.lookup(values, {**team, 'team': 'Como Women'}))
        self.assertIsNone(standings.lookup(values, {**team, 'league': 'Other'}))

    def test_org_rejects_wrong_competition_duplicate_and_ambiguous_tables(self):
        with self.assertRaises(ValueError): normalize(self.org_payload(), 'PL')
        payload = self.org_payload();payload['standings'] *= 2
        with self.assertRaises(ValueError): normalize(payload, 'SA')
        payload = self.org_payload();payload['standings'][0]['table'] *= 2
        with self.assertRaises(ValueError): normalize(payload, 'SA')
        payload = self.org_payload();payload['standings'][0]['group'] = 'Group A'
        with self.assertRaises(ValueError): normalize(payload, 'SA')

    def test_org_fresh_cache_makes_no_requests(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'FOOTBALL_DATA_ORG': 'secret'}):
            root = Path(directory);folder = root/'data/providers/football-data-org';folder.mkdir(parents=True)
            for code in COMPETITIONS:
                path = folder/f'standings-{code}-2026.json';path.write_text('{}')
                self.assertIsNotNone(ALLOWED.fullmatch(path.relative_to(root).as_posix()))
            store = Mock()
            download(store, root, datetime(2026,10,12,tzinfo=timezone.utc))
            store.fetch.assert_not_called();store.persist.assert_not_called()


if __name__ == '__main__':
    unittest.main()
