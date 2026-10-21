"""Verify sample boundaries and missing-data semantics, without downloading feeds."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import matchup_stats as stats


def row(team, day, venue, **metrics):
    return dict(team=team, name=team, league='League', season='2026/2027',
                date=f'2026-10-{day:02}', fixture=f'{team}-{day}', venue=venue, stats=metrics)


def history():
    return [row('Alpha', 1, 'home', goals=0, **{'shots-on-target':6}),
            row('Alpha', 5, 'home', goals=2, **{'shots-on-target':10}),
            row('Alpha', 8, 'away', goals=8, **{'shots-on-target':30}),
            row('Beta', 2, 'away', goals=3, **{'shots-on-target-conceded':8}),
            row('Beta', 6, 'away', goals=1, **{'shots-on-target-conceded':6}),
            row('Beta', 9, 'home', goals=7, **{'shots-on-target-conceded':30}),
            row('Gamma', 10, 'home', goals=1, **{'shots-on-target':2})]


def build(rows=None, selected=None, fixture=None, last_n=0):
    rows = history() if rows is None else rows
    selected = rows[0] if selected is None else selected
    fixture = dict(opponent='Beta', date='2026-10-25', venue='home', fetched_at='2026-10-19T10:00:00Z') if fixture is None else fixture
    return stats.build(rows, selected, fixture, last_n, today='2026-10-20')


class MatchupTests(unittest.TestCase):
    def test_additional_ratios_use_paired_sums_and_missing_results_stay_unknown(self):
        rows = [row('Alpha',1,'home',goals=0,**{'goals-conceded':0,'xg':1,'shots-total':1}),
                row('Alpha',2,'home',goals=2,**{'goals-conceded':1,'xg':1,'shots-total':9}),
                row('Alpha',3,'home',goals=3,**{'xg':None,'shots-total':100}),
                row('Beta',4,'away',goals=1)]
        p=build(rows)['home']
        self.assertEqual(p['quality'][1]['mean'],.2)
        self.assertEqual(p['quality'][1]['covered'],2)
        self.assertEqual(p['clean_sheets']['count'],1)
        self.assertEqual(p['clean_sheets']['covered'],2)
        self.assertEqual(p['scoreless']['count'],1)
        self.assertEqual(p['recent_form']['points_per_match'],2)
        self.assertEqual(p['recent_form']['covered'],2)
        self.assertIsNone(p['recent_form']['matches'][-1]['result'])

    def test_recent_form_and_lineup_reference_ignore_venue_window(self):
        rows=[row('Alpha',i,'home' if i%2 else 'away',goals=1,**{'goals-conceded':0}) for i in range(1,13)]
        for r in rows:r.update(provider='test',starters=list(range(11)))
        rows.append(row('Beta',5,'away',goals=0))
        full=build(rows)['home'];window=build(rows,last_n=5)['home']
        self.assertEqual(full['recent_form'],window['recent_form'])
        self.assertEqual(full['lineup'],window['lineup'])
        self.assertEqual(window['lineup']['sample'],12)
        self.assertEqual(window['activity']['matches_last_14_days'],7)
        self.assertEqual(window['activity']['days_to_fixture'],13)

    def test_small_venue_samples_expand_with_matching_league_baselines(self):
        result = build()
        self.assertEqual(result['mode'], 'descriptive')
        self.assertEqual(result['status'], 'ready')
        self.assertEqual((result['home']['name'], result['away']['name']), ('Alpha', 'Beta'))
        self.assertEqual((result['home']['matches'], result['away']['matches']), (3, 3))
        self.assertEqual(result['home']['sample_scope'], 'all')
        metric = result['directions'][0]['metrics'][0]
        self.assertAlmostEqual(metric['attack']['mean'], 46/3)
        self.assertAlmostEqual(metric['conceded']['mean'], 44/3)
        self.assertEqual(metric['attack']['baseline']['mean'], 12)
        self.assertAlmostEqual(metric['attack']['difference'], 46/3-12)
        self.assertAlmostEqual(metric['conceded']['baseline']['mean'], 44/3)
        self.assertEqual(metric['attack']['baseline']['matches'], 7)
        self.assertEqual(metric['attack']['baseline']['covered'], 4)

    def test_expanded_window_keeps_five_recent_league_games_against_all_opponents(self):
        rows = [{**row('Alpha', i, 'home' if i%2 else 'away', goals=i), 'opponent':f'Other {i}'} for i in range(1,9)]
        rows += [row('Beta', i, 'away', goals=1) for i in range(1,7)]
        result = build(rows, last_n=5)
        self.assertEqual(result['home']['matches'], 5)
        self.assertEqual(result['home']['first'], '2026-10-04')
        self.assertEqual(result['home']['sample_scope'], 'all')
        self.assertEqual(result['away']['sample_scope'], 'away')
        self.assertEqual(result['away']['matches'], 5)
        self.assertEqual(result['directions'][0]['metrics'][2]['attack']['mean'], 6)
        self.assertEqual(result['directions'][0]['metrics'][2]['conceded']['baseline']['matches'], 10)
        self.assertFalse(any('campione ridotto' in n for n in result['notes']))

    def test_selecting_away_team_preserves_fixture_orientation(self):
        rows = history()
        away = build(rows, rows[3], dict(opponent='Alpha', date='2026-10-25', venue='away'))
        home = build(rows)
        for key in ('home', 'away', 'directions'):
            self.assertEqual(away[key], home[key])

    def test_only_past_same_league_season_rows_are_used(self):
        rows = history()
        expected = build(rows)
        extra = [row('Alpha', 20, 'home', goals=99), row('Alpha', 21, 'home', goals=99),
                 row('Alpha', 25, 'home', goals=99), row('Alpha', 26, 'home', goals=99),
                 {**rows[0], 'league':'Other', 'stats':{'goals':99}},
                 {**rows[0], 'season':'2025/2026', 'stats':{'goals':99}},
                 {**rows[0], 'date':'invalid'}, {**rows[0], 'date':None}]
        self.assertEqual(build(rows + extra), expected)
        self.assertEqual(expected['cutoff_exclusive'], '2026-10-20')

    def test_today_fixture_still_excludes_today_observations(self):
        rows = history() + [row('Alpha', 20, 'home', goals=20)]
        result = build(rows, fixture=dict(opponent='Beta', date='2026-10-20', venue='home'))
        self.assertEqual(result['home']['matches'], 3)

    def test_window_is_by_venue_before_metric_filtering(self):
        rows = [row('Alpha', i, 'home', **{'shots-on-target':i if i < 6 else None}) for i in range(1, 7)]
        rows += [row('Alpha', 7, 'away', **{'shots-on-target':100})]
        rows += [row('Beta', i, 'away', **{'shots-on-target-conceded':i}) for i in range(1, 7)]
        window = build(rows, last_n=5)
        full = build(rows)
        attack = window['directions'][0]['metrics'][0]['attack']
        self.assertEqual(window['home']['first'], '2026-10-02')
        self.assertEqual(window['home']['season_venue_matches'], 6)
        self.assertEqual((attack['matches'], attack['covered'], attack['mean']), (5, 4, 3.5))
        self.assertEqual(attack['baseline'], full['directions'][0]['metrics'][0]['attack']['baseline'])
        self.assertEqual(build(rows, last_n=10)['home']['matches'], 6)

    def test_goal_frequencies_include_zero_exclude_missing_and_invalid(self):
        values = (None, 0, 1, 2, 6, 9, True, float('nan'), float('inf'), -1, 1.5, '3')
        result = stats.goal_frequencies([{'stats':{'goals':v}} for v in values])
        self.assertEqual((result['matches'], result['covered']), (12, 5))
        self.assertEqual([b['count'] for b in result['bins']], [1, 1, 1, 0, 0, 0, 2])
        self.assertEqual(result['bins'][-1]['frequency'], .4)
        self.assertAlmostEqual(sum(b['frequency'] for b in result['bins']), 1)
        missing = stats.goal_frequencies([{'stats':{}}])
        self.assertTrue(all(b['frequency'] is None for b in missing['bins']))

    def test_zero_and_missing_metrics_remain_distinct(self):
        result = stats.comparison([{'stats':{'xg':0}}, {'stats':{}}, {'stats':{'xg':True}}], [], 'xg')
        self.assertEqual((result['mean'], result['covered'], result['matches']), (0, 1, 3))
        self.assertIsNone(result['baseline']['mean'])
        self.assertIsNone(result['difference'])

    def test_missing_opponent_history_is_partial_and_not_filled(self):
        result = build(fixture=dict(opponent='Unknown', date='2026-10-25', venue='home'))
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['away']['matches'], 0)
        self.assertIsNone(result['away']['entity'])
        self.assertIsNone(result['directions'][0]['metrics'][0]['conceded']['mean'])
        self.assertIsNone(result['away']['goal_frequencies']['bins'][0]['frequency'])

    def test_unknown_venue_is_excluded_and_reported(self):
        rows = history() + [row('Alpha', 11, None, goals=50)]
        result = build(rows)
        self.assertEqual(result['home']['matches'], 3)
        self.assertEqual(result['home']['unknown_venue'], 1)
        self.assertTrue(any('campo non è noto' in note for note in result['notes']))

    def test_invalid_or_missing_schedule_does_not_create_a_matchup(self):
        for fixture in (None, {}, dict(opponent='Beta', date='2026-10-19', venue='home'),
                        dict(opponent='Beta', date='bad', venue='home'),
                        dict(opponent='Alpha', date='2026-10-25', venue='home'),
                        dict(opponent='Beta', date='2026-10-25', venue=None)):
            with self.subTest(fixture=fixture):
                result = stats.build(history(), history()[0], fixture, today='2026-10-20')
                self.assertEqual(result['status'], 'unavailable')
                self.assertNotIn('directions', result)

    def test_inputs_are_not_mutated(self):
        rows = history()
        original = copy.deepcopy(rows)
        build(rows)
        self.assertEqual(rows, original)

    def test_unsupported_window_rejected(self):
        with self.assertRaises(ValueError):
            build(last_n=7)


if __name__ == '__main__':
    unittest.main()
