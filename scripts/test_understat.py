import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import understat_stats as stats
from fetch_understat import Client


def sample():
    match = dict(id='1', isResult=True, datetime='2026-09-10 12:00:00',
                 h={'id': '10', 'title': 'AC Milan'}, a={'id': '20', 'title': 'Roma'},
                 goals={'h': '1', 'a': '0'})
    player = dict(player_id='30', player='Player', team_id='10', position='FW',
                  goals='1', own_goals='0', assists='0', yellow_card='0', shots='2', time='90')
    away = {**player, 'player_id': '40', 'team_id': '20', 'goals': '0', 'shots': '0'}
    data = dict(rosters={'h': {'30': player}, 'a': {'40': away}},
                shots={'h': [dict(match_id='1', player_id='30', result=r, minute='47')
                              for r in ['Goal', 'BlockedShot']], 'a': []})
    envelope = dict(data=data, fetched_at='2026-10-11T00:00:00Z', source_url='https://understat.com/getMatchData/1')
    return match, envelope


class UnderstatTests(unittest.TestCase):
    def test_real_appearances_null_fouls_and_no_inferred_halftime(self):
        players, teams = stats.match_rows(*sample(), 'Serie A', 'I1', '2026/2027')
        self.assertEqual(players[0]['team'], 'Milan')
        self.assertEqual(players[0]['stats']['shots-on-target'], 1)
        self.assertEqual(players[1]['stats']['shots-on-target'], 0)
        self.assertNotIn('fouls', players[0]['stats'])
        self.assertNotIn('first-half-goals', teams[0]['stats'])

    def test_incomplete_shot_events_are_unknown_not_zero(self):
        match, envelope = sample()
        envelope['data']['shots']['h'].pop()
        players, teams = stats.match_rows(match, envelope, 'Serie A', 'I1', '2026/2027')
        self.assertIsNone(players[0]['stats']['shots-on-target'])
        self.assertIsNone(teams[0]['stats']['shots-on-target'])

    def test_mismatched_goals_rejected_and_future_games_excluded(self):
        match, envelope = sample()
        match['goals']['h'] = '2'
        players, teams = stats.match_rows(match, envelope, 'Serie A', 'I1', '2026/2027')
        self.assertFalse(players)
        self.assertTrue(teams[0]['player_data_issues'])
        self.assertEqual(teams[0]['stats'], {'goals': 2})
        match['datetime'] = '2099-01-01'
        self.assertEqual(stats.match_rows(match, envelope, 'Serie A', 'I1', '2026/2027'), ([], []))

    def test_merge_is_idempotent_preserves_csv_ht_and_source_payloads(self):
        players, teams = stats.match_rows(*sample(), 'Serie A', 'I1', '2026/2027')
        csv = [{**t, 'provider': 'football-data.co.uk', 'fixture': 'csv:1',
                'stats': {'goals': t['stats']['goals'], 'first-half-goals': 0},
                'halftime_audit': {'fixture': 'csv:1', 'status': 'source_only'}} for t in teams]
        original = copy.deepcopy(teams + csv)
        p, t, w = stats.merge_sources(players, teams + csv)
        self.assertEqual(len(t), 2)
        self.assertEqual(t[0]['stats']['first-half-goals'], 0)
        self.assertEqual(teams + csv, original)
        self.assertEqual(stats.merge_sources(p, t), (p, t, w))
        csv[0]['stats']['shots-on-target'] = None
        self.assertEqual(stats.merge_sources(players, teams + csv)[1][0]['stats']['shots-on-target'], 1)
        csv[0]['stats']['goals'] = 5
        p, t, w = stats.merge_sources(players, teams + csv)
        self.assertFalse(p)
        self.assertEqual(t, csv)
        self.assertTrue(w)

    def test_cache_and_zero_budget_never_make_network_calls(self):
        with tempfile.TemporaryDirectory() as directory, patch('fetch_understat.urlopen') as request:
            root = Path(directory)
            (root / 'match-1.json').write_text(json.dumps({'data': 'saved'}))
            client = Client(root, budget=0)
            self.assertEqual(client.get('getMatchData/1', 'match-1.json')['data'], 'saved')
            with self.assertRaises(RuntimeError):
                client.get('getMatchData/2', 'match-2.json')
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
