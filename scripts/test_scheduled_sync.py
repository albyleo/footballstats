import copy
from datetime import datetime, timezone
import sys
from pathlib import Path
import unittest
import tempfile
import os
import time
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sync_diff import changed_fixtures
from scheduled_sync import ALLOWED, Store, retry_delay, download
from urllib.error import HTTPError


class IncrementalTests(unittest.TestCase):
    def snapshot(self):
        return {'players':[{'provider':'p','fixture':1,'id':4,'fetched_at':'old','stats':{'goals':0}}],
                'teams':[{'provider':'p','fixture':1,'id':2,'fetched_at':'old','stats':{'goals':1}}]}

    def test_timestamp_and_order_are_not_changes(self):
        old=self.snapshot();new=copy.deepcopy(old)
        for row in new['players']+new['teams']: row['fetched_at']='new'
        self.assertEqual(changed_fixtures(new,old['players'],old['teams']),set())

    def test_correction_removal_and_new_fixture(self):
        old=self.snapshot();new=copy.deepcopy(old)
        new['players'][0]['stats']['goals']=1
        self.assertEqual(changed_fixtures(new,old['players'],old['teams']),{('p','1')})
        new['players']=[]
        self.assertEqual(changed_fixtures(new,old['players'],old['teams']),{('p','1')})
        new=copy.deepcopy(old);new['teams'][0]['fixture']=2
        self.assertIn(('p','2'),changed_fixtures(new,old['players'],old['teams']))

    def test_subset_does_not_delete_other_fixtures(self):
        old=self.snapshot();extra={**old['teams'][0],'fixture':99}
        self.assertEqual(changed_fixtures(old,old['players'],old['teams']+[extra]),set())

    def test_untrusted_cache_paths_rejected(self):
        for path in ['../../.env','data/providers/understat/../../.env','data/providers/sportmonks/cache/token.json']:
            self.assertIsNone(ALLOWED.fullmatch(path))
        self.assertIsNotNone(ALLOWED.fullmatch('data/providers/understat/match-123.json'))

    def test_retry_after_seconds_and_date(self):
        now=datetime(2026,10,11,tzinfo=timezone.utc)
        self.assertEqual(retry_delay('7200',now),7200)
        self.assertEqual(retry_delay('Sun, 11 Oct 2026 02:00:00 GMT',now),7200)
        self.assertEqual(retry_delay(None,now),21600)

    def test_rate_limit_stops_and_persists_cooldown(self):
        store=Store(Mock());store.reserve=Mock();store.set=Mock()
        error=HTTPError('https://example.com',429,'limited',{'Retry-After':'7200'},None)
        with patch('scheduled_sync.urlopen',side_effect=error) as call:
            with self.assertRaises(RuntimeError):store.fetch('understat','https://example.com')
        call.assert_called_once();store.reserve.assert_called_once_with('understat')
        self.assertEqual(store.set.call_args.args[0],'cooldown:understat')

    def test_exhausted_budget_never_calls_provider(self):
        store=Store(Mock());store.get=Mock(return_value=0)
        store.conn.execute.return_value.fetchone.return_value=None
        with patch('scheduled_sync.urlopen') as call:
            with self.assertRaises(RuntimeError):store.fetch('understat','https://example.com')
        call.assert_not_called()

    def test_persistent_block_never_calls_provider(self):
        store=Store(Mock());store.get=Mock(return_value=True)
        with patch('scheduled_sync.urlopen') as call:
            with self.assertRaisesRegex(RuntimeError,'manual review'):
                store.fetch('understat','https://example.com')
        call.assert_not_called();store.conn.execute.assert_not_called()

    def test_forbidden_sets_persistent_block(self):
        store=Store(Mock());store.reserve=Mock();store.set=Mock()
        error=HTTPError('https://example.com',403,'forbidden',{},None)
        with patch('scheduled_sync.urlopen',side_effect=error):
            with self.assertRaises(RuntimeError):store.fetch('understat','https://example.com')
        store.set.assert_any_call('blocked:understat',True)

    def test_html_challenge_never_replaces_cache(self):
        with tempfile.TemporaryDirectory() as directory, patch('scheduled_sync.ROOT',Path(directory)):
            store=Store(Mock());store.fetch=Mock(return_value=b'<html>Challenge</html>');store.set=Mock();store.persist=Mock()
            with self.assertRaisesRegex(RuntimeError,'manual review'):
                store.understat('getMatchData/1','match-1.json',True)
            store.set.assert_called_once_with('blocked:understat',True)
            store.persist.assert_not_called()

    def test_portugal_csv_normalizes_team_metrics(self):
        import csv_stats
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'P1_2026-27.csv'
            path.write_text('Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG,HS,AS\nP1,01/10/2026,Home,Away,2,1,1,0,12,8\n')
            self.assertEqual(csv_stats.files(Path(directory)),[path])
            rows,warnings=csv_stats.load_rows([path])
            self.assertEqual(warnings,[])
            self.assertEqual(rows[0]['league'],'Primeira Liga')
            self.assertEqual(rows[0]['stats']['shots-total'],12)
            self.assertIsNone(rows[0]['stats']['shots-on-target'])
            self.assertIsNotNone(ALLOWED.fullmatch('data/raw/P1_2026-27.csv'))

    def test_recent_checks_skip_unchanged_csv_and_sportmonks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data/raw').mkdir(parents=True)
            for code in ('I1','E0','SP1','D1','F1','P1'):
                path=root/f'data/raw/{code}_2026-27.csv'
                path.write_text('cached');os.utime(path,(1,1))
            store=Mock();store.get.return_value=time.time()
            with patch('scheduled_sync.ROOT',root),patch('scheduled_sync.LEAGUES',()),patch.dict(os.environ,{'SPORTMONKS_TOKEN':'test'}):
                download(store,2026)
            store.fetch.assert_not_called()


if __name__=='__main__':unittest.main()
