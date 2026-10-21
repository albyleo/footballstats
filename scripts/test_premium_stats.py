import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import premium_stats as stats
import webapp
from report_cache import ReportCache
from starlette.testclient import TestClient


def snapshot():
    teams, players = [], []
    for i in range(1,13):
        for tid, name in ((1,'Alpha'),(2,'Beta')):
            row = dict(provider='sportmonks',fixture=i,league='League',league_id=1,season='2026/2027',
                       id=tid,name=name,team=name,opponent='Beta' if tid==1 else 'Alpha',
                       date=f'2026-09-{i:02}',fetched_at='now',venue='home' if (i+tid)%2==0 else 'away',
                       stats={'goals':tid,'xg':float(i),'xga':1.0,'shots-total':i*2,'shots-on-target':i})
            teams.append(row)
            if tid == 1:
                players.append({**row,'id':3,'name':'Player','minutes':45 if i%2 else 90})
    return dict(players=players,teams=teams,warnings=[],catalog={},sync=None)


class PremiumTests(unittest.TestCase):
    def test_additional_conceded_metrics_are_paired_before_filters(self):
        data=snapshot()
        for r in data['teams']:
            r['stats'].update({'corners':r['id']*3,'first-half-goals':r['id']-1})
        teams=stats.observations(data)[1]
        alpha=next(r for r in teams if r['team']=='Alpha')
        self.assertEqual(alpha['stats']['corners-conceded'],6)
        self.assertEqual(alpha['stats']['first-half-goals-conceded'],1)
        data['teams']=data['teams'][:1]
        alone=stats.observations(data)[1][0]
        self.assertIsNone(alone['stats']['corners-conceded'])

    def test_upcoming_comparison_http_uses_saved_opponent_stats(self):
        saved = {**snapshot(), 'revision': 124, 'upcoming': [dict(id='next', league='League',
                 season='2026/2027', home='Alpha', away='Beta', date='2099-10-25')]}
        with (patch.object(webapp.cloud_store, 'enabled', return_value=True),
              patch.object(webapp.cloud_store.SNAPSHOTS, 'get', return_value=saved),
              patch.object(webapp, 'PREMIUM_CACHE', ReportCache()),
              patch('urllib.request.urlopen', side_effect=AssertionError('No feed downloads')),
              patch.dict('os.environ', {'FOOTBALL_PREMIUM_MODE':'open'}), TestClient(webapp.app) as client):
            response = client.get('/api/premium/report?last_n=5&venue=away&metric=goals')
            self.assertEqual(response.status_code, 200)
            report = response.json()
            matchup = report['matchup']
            self.assertEqual((matchup['home']['name'], matchup['away']['name']), ('Alpha', 'Beta'))
            self.assertEqual(matchup['home']['matches'], 5)
            # Alpha home fixtures 3,5,7,9,11: both produced and opposing conceded average 7.
            metric = matchup['directions'][0]['metrics'][0]
            self.assertEqual((metric['attack']['mean'], metric['conceded']['mean']), (7, 7))
            # Profile filter is away but matchup always follows the scheduled venue.
            self.assertTrue(all(r['venue'] == 'away' for r in report['primary']['series']))
            self.assertIsNone(client.get('/api/premium/report?kind=players').json()['matchup'])
            self.assertEqual(client.get('/api/premium/report?last_n=5&venue=away&metric=goals').headers['x-report-cache'], 'HIT')

    def test_explorer_profile_ids_open_matching_premium_with_filters(self):
        data = {**snapshot(), 'revision': 123}
        with (patch.object(webapp.cloud_store, 'enabled', return_value=True),
              patch.object(webapp.cloud_store.SNAPSHOTS, 'get', return_value=data),
              patch.object(webapp, 'REPORT_CACHE', ReportCache()),
              patch.object(webapp, 'PREMIUM_CACHE', ReportCache()),
              patch('urllib.request.urlopen', side_effect=AssertionError('No feed downloads')),
              patch.dict('os.environ', {'FOOTBALL_PREMIUM_MODE':'open'}), TestClient(webapp.app) as client):
            for kind in ('teams', 'players'):
                params = dict(kind=kind, metric='shots-on-target', last_n=5)
                rows = client.get('/api/providers/report', params=params).json()['rows']
                for row in rows:
                    response = client.get('/api/premium/report', params={**params,
                        'league':row['league'], 'season':row['season'], 'entity':row['entity_id'],
                        'basis':'per90' if kind == 'players' else 'match'})
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    self.assertEqual(result['primary']['name'], row['name'])
                    self.assertEqual(result['primary']['team'], row['team'])
                    self.assertEqual(result['primary']['summary']['total'], row['total'])
                    self.assertEqual(result['filters']['metric'], 'shots-on-target')
                    self.assertEqual(result['filters']['last_n'], 5)

    def test_profile_links_distinguish_homonyms_transfers_and_seasons(self):
        data = snapshot()
        original = data['players'][0]
        data['players'] += [{**original, 'id':4, 'stats':{'goals':4}},
                            {**original, 'team':'Beta', 'stats':{'goals':5}},
                            {**original, 'season':'2025/2026', 'stats':{'goals':6}}]
        rows = stats.provider_stats.report(kind='players', metric='goals', snapshot=data)['rows']
        self.assertEqual(len({r['entity_id'] for r in rows}), 4)
        for row in rows:
            profile = stats.report(kind='players', league=row['league'], season=row['season'],
                                   entity=row['entity_id'], metric='goals', snapshot=data)['primary']
            self.assertEqual(profile['team'], row['team'])
            self.assertEqual(profile['season'], row['season'])
            self.assertEqual(profile['summary']['total'], row['total'])

    def test_splits_window_and_season_baseline(self):
        data=snapshot();original=copy.deepcopy(data)
        report=stats.report(league='League',metric='xg',last_n=5,snapshot=data)
        p=report['primary']
        self.assertEqual(p['summary']['mean'],10)
        self.assertEqual(p['season_summary']['mean'],6.5)
        self.assertEqual(p['splits']['home']['mean'],6)
        self.assertEqual(p['splits']['away']['mean'],7)
        self.assertEqual(p['series'][-1]['ma5'],10)
        self.assertEqual(p['series'][-1]['ma10'],7.5)
        self.assertEqual(data,original)

    def test_venue_filter_before_last_n_and_missing_windows(self):
        data=snapshot();data['teams'][0]['stats']['xg']=None
        p=stats.report(league='League',venue='home',last_n=5,snapshot=data)['primary']
        self.assertEqual([r['date'] for r in p['series']],['2026-09-03','2026-09-05','2026-09-07','2026-09-09','2026-09-11'])
        self.assertIsNone(p['series'][-2]['ma5'])
        self.assertEqual(p['series'][-1]['ma5'],7)
        self.assertIsNone(p['series'][-1]['ma10'])

    def test_ratio_uses_paired_sums_not_mean_of_ratios(self):
        rows=[{'stats':{'xg':1,'shots-total':1}}, {'stats':{'xg':1,'shots-total':9}}, {'stats':{'xg':None,'shots-total':100}}]
        self.assertEqual(stats.aggregate(rows,'xg-per-shot','match'),.2)
        self.assertIsNone(stats.value({'stats':{'xg':0,'shots-total':0}},'xg-per-shot','match'))

    def test_frequency_denominator_excludes_missing_and_includes_zero(self):
        rows=[{'stats':{'goals':v}} for v in (None,0,1,2)]
        s=stats.summary(rows,'goals','match',1)
        self.assertEqual((s['matches'],s['covered'],s['successes']),(4,3,2))
        self.assertAlmostEqual(s['frequency'],2/3)
        self.assertEqual(s['median'],1)

    def test_per90_uses_paired_minutes(self):
        rows=[{'stats':{'goals':1},'minutes':30},{'stats':{'goals':1},'minutes':90},{'stats':{'goals':None},'minutes':90}]
        self.assertEqual(stats.aggregate(rows,'goals','per90'),1.5)

    def test_unknown_venue_not_guessed(self):
        data=snapshot();data['teams'][0].pop('venue')
        p=stats.report(snapshot=data)['primary']
        self.assertEqual(p['unknown_venue'],1)
        self.assertEqual(p['splits']['home']['matches'],5)

    def test_comparison_uses_same_filters_and_correct_opponent_shots(self):
        data=snapshot();initial=stats.report(snapshot=data)
        report=stats.report(compare=initial['entities'][1]['id'],last_n=5,venue='home',snapshot=data)
        self.assertEqual(report['comparison']['summary']['matches'],5)
        self.assertNotEqual(report['primary']['name'],report['comparison']['name'])
        rows=stats.observations(data)[1]
        self.assertEqual(rows[0]['stats']['shots-conceded'],2)

    def test_cross_season_or_unknown_entities_rejected(self):
        with self.assertRaises(ValueError):stats.report(entity='unknown',snapshot=snapshot())
        with self.assertRaises(ValueError):stats.report(basis='per90',snapshot=snapshot())
        with self.assertRaises(ValueError):stats.report(threshold=float('nan'),snapshot=snapshot())

    def test_empty_archive(self):
        result=stats.report(snapshot={'players':[],'teams':[],'warnings':[]})
        self.assertIsNone(result['primary']);self.assertEqual(result['entities'],[])

    def test_http_cache_no_provider_calls_and_access_boundary(self):
        with (patch.object(webapp.cloud_store,'enabled',return_value=True),
              patch.object(webapp.cloud_store.SNAPSHOTS,'get',return_value={**snapshot(),'revision':999}),
              patch.object(webapp,'PREMIUM_CACHE',ReportCache()),
              patch('urllib.request.urlopen',side_effect=AssertionError('No downloads')),
              patch.dict('os.environ',{'FOOTBALL_PREMIUM_MODE':'open'}),TestClient(webapp.app) as client):
            self.assertEqual(client.get('/premium').status_code,200)
            response=client.get('/api/premium/report')
            self.assertEqual(response.status_code,200)
            self.assertEqual(client.get('/api/premium/report').headers['x-report-cache'],'HIT')
            self.assertEqual(client.get('/api/premium/report',headers={'If-None-Match':response.headers['etag']}).status_code,304)
            self.assertEqual(client.get('/api/premium/report?threshold=nan').status_code,400)
            with patch.dict('os.environ',{'FOOTBALL_PREMIUM_MODE':'disabled'}):
                self.assertEqual(client.get('/api/premium/report').status_code,403)


if __name__=='__main__':unittest.main()
