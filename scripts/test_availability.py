import copy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import availability
from fetch_availability import acquire
from scheduled_sync import ALLOWED, download_availability
from supabase_data import import_snapshot

STAMP = '2026-10-21T08:00:00+00:00'
NOW = datetime.fromisoformat(STAMP)


def fixture():
    return dict(id=1, starting_at='2026-10-25 15:00:00', state={'state':'NS'},
                league={'name':'Superliga'}, season={'name':'2026/2027'},
                participants=[dict(id=1,name='Alpha',meta={'location':'home'}),
                              dict(id=2,name='Beta',meta={'location':'away'})],
                sidelined=[dict(player_id=10,participant_id=1,player={'display_name':'Player A'},
                              type={'name':'Knee Injury','code':'knee-injury'},
                              sideline={'completed':False,'category':'injury','end_date':'2026-11-01'}),
                          dict(player_id=20,participant_id=2,player={'name':'Player B'},
                              type={'name':'Suspended','code':'suspended'},sideline=None)])


def report(archive, now=NOW, reference=()):
    return availability.for_fixture(archive, 'Superliga', '2026/2027', 'Alpha', 'Beta',
                                    '2026-10-25', reference, now=now)


class AvailabilityTests(unittest.TestCase):
    def test_fixture_specific_absences_and_exact_reference_identity(self):
        reference = [dict(provider='sportmonks',id=i) for i in range(10,21)]
        data = availability.normalize([fixture()], STAMP)
        result = report(data, reference=reference)
        self.assertEqual(result['status'], 'reported')
        self.assertEqual([a['name'] for a in result['absences']], ['Player A'])
        self.assertEqual(result['reference_absent'], 1)
        self.assertEqual(result['absences'][0]['category'], 'injury')
        other_source = [{**p,'provider':'other'} for p in reference]
        self.assertEqual(report(data, reference=other_source)['reference_absent'], 0)
        self.assertIsNone(report(data, reference=reference[:5])['reference_absent'])
        self.assertEqual(data['fixtures'][0]['absences'][1]['category'], 'suspension')

    def test_missing_empty_stale_and_future_check_are_distinct(self):
        match = fixture();match['sidelined'] = []
        data = availability.normalize([match], STAMP)
        self.assertEqual(report(data)['status'], 'none_reported')
        self.assertIn('Non conferma', report(data)['message'])
        match.pop('sidelined')
        self.assertEqual(report(availability.normalize([match], STAMP))['status'], 'missing')
        data = availability.normalize([fixture()], STAMP)
        stale = report(data, now=NOW+timedelta(hours=49))
        self.assertEqual(stale['status'], 'stale')
        self.assertEqual(len(stale['absences']), 1)
        self.assertIsNone(stale['reference_absent'])
        self.assertEqual(report(data, now=NOW-timedelta(seconds=1))['status'], 'missing')
        self.assertEqual(report({})['status'], 'missing')

    def test_wrong_opponent_date_season_do_not_leak_absences(self):
        for key,value in [('away','Other'),('date','2026-10-26'),('season','2025/2026')]:
            data = availability.normalize([fixture()], STAMP)
            data['fixtures'][0][key] = value
            self.assertEqual(report(data)['status'], 'missing')

    def test_completed_and_duplicate_absences_removed_not_inferred_from_lineups(self):
        match=fixture()
        match['sidelined'] += [copy.deepcopy(match['sidelined'][0]),
                              dict(player_id=30,participant_id=1,sideline={'completed':True})]
        original=copy.deepcopy(match)
        data=availability.normalize([match],STAMP)
        self.assertEqual(len(data['fixtures'][0]['absences']),2)
        self.assertEqual(match, original)
        match['state']['state']='FT'
        self.assertEqual(availability.normalize([match],STAMP)['fixtures'],[])

    def test_invalid_identity_aborts_batch(self):
        match=fixture();match['sidelined'][0]['participant_id']=99
        with self.assertRaises(ValueError):availability.normalize([match],STAMP)

    def test_bounded_pagination_keeps_oldest_timestamp_and_rejects_truncation(self):
        client=Mock();client.last_fetched_at=STAMP
        client.get.return_value={'data':[fixture()], 'pagination':{'has_more':False}}
        data=acquire(client,date(2026,10,21))
        self.assertEqual(len(data['fixtures']),1)
        self.assertEqual(client.get.call_count,1)
        second=fixture();second['id']=2
        def page(*args,**kwargs):
            client.last_fetched_at=STAMP if kwargs['page']==1 else '2026-10-21T10:00:00+00:00'
            return {'data':[fixture() if kwargs['page']==1 else second], 'pagination':{'has_more':kwargs['page']==1}}
        client.get.side_effect=page
        self.assertEqual(acquire(client,date(2026,10,21))['fetched_at'],STAMP)
        client.get.side_effect=None;client.get.return_value={'data':[fixture()], 'pagination':{'has_more':True}}
        with self.assertRaises(ValueError):acquire(client,date(2026,10,21),max_pages=1)

    def test_scheduled_acquisition_uses_budgeted_store_and_safe_cache_path(self):
        self.assertIsNotNone(ALLOWED.fullmatch('data/providers/sportmonks/availability.json'))
        with tempfile.TemporaryDirectory() as directory, patch('scheduled_sync.ROOT',Path(directory)), \
             patch('scheduled_sync.utcnow',return_value=NOW), \
             patch.dict('os.environ',{'SPORTMONKS_TOKEN':'test-token'}):
            store=Mock();store.get.return_value=0
            store.fetch.return_value=json.dumps({'data':[fixture()], 'pagination':{'has_more':False}}).encode()
            result=download_availability(store)
            self.assertEqual(result['status'],'updated')
            store.fetch.assert_called_once()
            self.assertEqual(store.fetch.call_args.args[0],'sportmonks')
            self.assertNotIn('test-token',store.fetch.call_args.args[1])
            store.persist.assert_called_once()
            store.fetch.reset_mock()
            self.assertEqual(download_availability(store)['status'],'cached')
            store.fetch.assert_not_called()

    def test_optional_failure_preserves_archive_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as directory, patch('scheduled_sync.ROOT',Path(directory)), \
             patch('scheduled_sync.utcnow',return_value=NOW), \
             patch.dict('os.environ',{'SPORTMONKS_TOKEN':'test-token'}):
            path=Path(directory)/'data/providers/sportmonks/availability.json'
            path.parent.mkdir(parents=True)
            old=json.dumps(availability.normalize([fixture()], '2026-10-18T08:00:00+00:00'))
            path.write_text(old,encoding='utf-8')
            store=Mock();store.get.return_value=0;store.fetch.side_effect=RuntimeError('budget exhausted')
            self.assertEqual(download_availability(store)['status'],'unavailable')
            self.assertEqual(path.read_text(encoding='utf-8'),old)
            store.persist.assert_not_called()

    def test_metadata_only_import_updates_availability_without_replacing_fixtures(self):
        saved=dict(players=[],teams=[dict(provider='p',fixture=1,id=1,name='A',team='A',date='2026-10-01',league='L',season='S')],
                   warnings=[],catalog={},sync=None,availability=availability.normalize([fixture()],STAMP))
        conn=MagicMock();conn.execute.return_value.fetchone.return_value=({},)
        with patch('supabase_data.changed_fixtures',return_value=set()):
            result=import_snapshot(conn,saved)
        self.assertTrue(result['updated'])
        self.assertEqual(result['changed_fixtures'],0)
        updates=[c for c in conn.execute.call_args_list if c.args[0].startswith('UPDATE football.dataset_state')]
        self.assertEqual(updates[0].args[1][0].obj['availability'],saved['availability'])


if __name__=='__main__':unittest.main()
