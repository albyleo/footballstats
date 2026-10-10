import copy
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from score_audit import audit_match, score_value
from csv_stats import load_rows


def fixture():
    return {"id": 1, "name": "Home vs Away", "starting_at": "2026-09-01 20:00:00",
        "participants": [{"id": 10,"meta":{"location":"home"}}, {"id":20,"meta":{"location":"away"}}],
        "periods": [{"id":100,"type_id":1},{"id":200,"type_id":2}],
        "scores": [{"participant_id":tid,"type_id":typ,"description":description,"score":{"goals":value}}
                   for tid,ht,ft in [(10,1,1),(20,0,1)]
                   for typ,description,value in [(1,"1ST_HALF",ht),(1525,"CURRENT",ft),(48996,"2ND_HALF_ONLY",ft-ht)]],
        "events": [
            {"id":1,"type_id":14,"period_id":100,"minute":45,"extra_minute":4,"sort_order":1,"result":"1-0"},
            {"id":2,"type_id":15,"period_id":200,"minute":46,"extra_minute":None,"sort_order":2,"result":"1-1"},
            {"id":3,"type_id":14,"period_id":100,"minute":20,"rescinded":True,"sort_order":0,"result":"9-9"}]}


class ScoreAuditTests(unittest.TestCase):
    def test_stoppage_time_own_goal_and_rescinded(self):
        audit=audit_match(fixture())
        self.assertEqual(audit["status"],"verified")
        self.assertEqual(audit["events_ht"],[1,0])
        self.assertEqual(audit["stoppage_goals"],1)

    def test_period_wins_over_clock_and_score_order(self):
        match=fixture()
        match["events"][0]["minute"]=49
        match["scores"].reverse()
        self.assertEqual(audit_match(match)["status"],"verified")
        self.assertEqual(score_value(match,10,1),1)
        self.assertEqual(score_value(match,20,1),0)

    def test_conflict_and_secondary_warning(self):
        match=fixture()
        match["scores"][0]["score"]["goals"]=0
        self.assertEqual(audit_match(match)["status"],"conflict")
        match=fixture()
        match["scores"][2]["score"]["goals"]=9
        self.assertEqual(audit_match(match)["status"],"verified_with_warning")

    def test_missing_duplicate_mislabeled_and_incomplete_events(self):
        match=fixture()
        match["scores"].append(copy.deepcopy(match["scores"][0]))
        self.assertIsNone(score_value(match,10,1))
        match=fixture()
        match["scores"][0]["description"]="CURRENT"
        self.assertIsNone(score_value(match,10,1))
        match=fixture()
        match["events"]=[]
        self.assertEqual(audit_match(match)["status"],"unverified")
        match=fixture()
        match.pop("periods")
        self.assertEqual(audit_match(match)["status"],"unverified")

    def test_csv_halftime_not_fulltime_and_missing_players(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"I1_2026-27.csv"
            path.write_text("Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG,HST,AST\n"
                            "I1,01/09/2026,Home,Away,4,2,1,0,7,3\n"
                            "I1,01/09/2026,Home,Away,4,2,1,0,7,3\n"
                            "I1,02/09/2026,Future,Away,,,,,,\n",encoding="utf-8")
            rows,warnings=load_rows([path])
            self.assertEqual(len(rows),2)
            self.assertEqual([r["stats"]["first-half-goals"] for r in rows],[1,0])
            self.assertEqual([r["stats"]["goals"] for r in rows],[4,2])
            self.assertEqual(rows[0]["halftime_audit"]["status"],"source_only")
            self.assertEqual(rows[0]["starters"],[])
            self.assertNotIn("assists",rows[0]["stats"])
            self.assertFalse(warnings)


if __name__ == "__main__":
    unittest.main()
