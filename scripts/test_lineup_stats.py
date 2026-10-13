import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lineup_stats import season_lineups
import provider_stats


class LineupTests(unittest.TestCase):
    def test_team_row_combines_reconciled_sources_and_keeps_lineup_coverage(self):
        rows=[self.fixture(1,list(range(11))),
              {**self.fixture(2,[]),'provider':'csv','id':'csv-team'}]
        snapshot=dict(players=[],teams=rows,catalog={},sync=None,warnings=[])
        report=provider_stats.report('teams','goals',snapshot=snapshot)
        self.assertEqual(len(report['rows']),1)
        row=report['rows'][0]
        self.assertEqual((row['matches'],row['total']),(2,2))
        self.assertEqual((row['season_lineup']['sample'],row['season_lineup']['season_matches']),(1,2))
        self.assertIsNone(row['season_lineup']['latest_common'])

    def test_combined_lineups_do_not_collide_player_ids_across_sources(self):
        rows=[self.fixture(1,list(range(11))),
              {**self.fixture(2,list(range(11))),'provider':'other'}]
        result=season_lineups([],rows,combine_sources=True)[('League','2026','Team')]
        self.assertTrue(result['tie'])
        self.assertTrue(all(p['starts']==1 for p in result['reference']))

    def fixture(self, fixture, starters, season='2026'):
        return dict(provider='test', league='League', season=season, team='Team', name='Team',
                    id=1, fixture=fixture, date=f'2026-09-{fixture:02}', fetched_at='2026-10-01',
                    starters=starters, stats={'goals':1})

    def test_complete_only_and_season_isolation(self):
        rows=[self.fixture(1,list(range(11))),self.fixture(2,list(range(11))),
              self.fixture(3,list(range(1,12))),self.fixture(4,[1,2]),
              self.fixture(5,list(range(20,31)),'2025')]
        result=season_lineups([],rows)[('test','League','2026','Team')]
        self.assertEqual(result['sample'],3)
        self.assertEqual({p['id'] for p in result['reference']},set(range(11)))
        self.assertIsNone(result['latest_common'])
        self.assertIsNone(result['next_common'])

    def test_last_n_does_not_change_reference(self):
        rows=[self.fixture(1,list(range(11))),self.fixture(2,list(range(11))),self.fixture(3,list(range(1,12)))]
        snapshot=dict(players=[],teams=rows,catalog={},sync=None,warnings=[])
        report=provider_stats.report('teams','goals',last_n=1,snapshot=snapshot)
        row=report['rows'][0]
        self.assertEqual(row['matches'],1)
        self.assertEqual(row['season_lineup']['sample'],3)
        self.assertEqual(row['season_lineup']['latest_common'],10)

    def test_drawn_not_derived_from_committed(self):
        row=dict(provider='test',league='League',season='2026',team='Team',name='P',id=1,
                 fixture=1,date='2026-09-01',fetched_at='2026-10-01',minutes=90,stats={'fouls':3},starter=True)
        snapshot=dict(players=[row],teams=[],catalog={},sync=None,warnings=[])
        report=provider_stats.report('players','fouls-drawn',snapshot=snapshot)
        self.assertIsNone(report['rows'][0]['total'])
        row['stats']['fouls-drawn']=0
        report=provider_stats.report('players','fouls-drawn',snapshot=snapshot)
        self.assertEqual(report['rows'][0]['total'],0)


if __name__=='__main__': unittest.main()
