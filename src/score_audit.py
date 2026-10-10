"""Validate explicit half-time scores against period-tagged goal events.

This is an internal consistency check of one provider, not independent match
verification. Never infer halves from minute <= 45: stoppage time belongs to
its period, even when the clock exceeds 45.
"""
import re

SCORE_TYPES = {1: "1ST_HALF", 1525: "CURRENT", 48996: "2ND_HALF_ONLY"}


def goal_count(value):
    if isinstance(value, bool):
        return None
    try:
        count = int(str(value))
        return count if count >= 0 else None
    except (ValueError, TypeError):
        return None


def score_value(match, team_id, type_id):
    scores = [s for s in match.get("scores", []) if s.get("participant_id") == team_id
              and s.get("type_id") == type_id]
    if len(scores) != 1 or scores[0].get("description") != SCORE_TYPES[type_id]:
        return None
    return goal_count((scores[0].get("score") or {}).get("goals"))


def audit_match(match):
    participants = {p.get("meta", {}).get("location"): p for p in match.get("participants", [])}
    result = {"fixture": match["id"], "date": match.get("starting_at", "")[:10],
              "match": match.get("name", ""), "provider": "sportmonks", "status": "unverified",
              "ht": None, "ft": None, "events_ht": None, "issues": [], "stoppage_goals": 0}
    if "home" not in participants or "away" not in participants:
        result["issues"].append("Squadre casa/trasferta non identificate")
        return result
    ids = [participants[side]["id"] for side in ("home", "away")]
    result["ht"] = [score_value(match, tid, 1) for tid in ids]
    result["ft"] = [score_value(match, tid, 1525) for tid in ids]
    second = [score_value(match, tid, 48996) for tid in ids]
    for i in range(2):
        a, b, c = result["ht"][i], second[i], result["ft"][i]
        if a is None or c is None:
            result["issues"].append("Punteggio HT/FT assente, duplicato o non valido")
        elif a > c:
            result["status"] = "conflict"
            result["issues"].append("Gol primo tempo superiori al risultato finale")
        if a is not None and b is not None and c is not None and a + b != c:
            result["issues"].append("1ST_HALF + 2ND_HALF_ONLY diverso da CURRENT")
    periods = {p["id"]: p["type_id"] for p in match.get("periods", [])}
    if "events" not in match or not {1, 2}.issubset(set(periods.values())):
        result["issues"].append("Eventi o periodi assenti: verifica incrociata non disponibile")
        return result
    events = [e for e in match["events"] if e.get("type_id") in (14, 15, 16) and not e.get("rescinded")]
    if len({e.get("id") for e in events}) != len(events):
        result["issues"].append("Eventi gol duplicati")
        return result
    running, halftime = [0, 0], [0, 0]
    for event in sorted(events, key=lambda e: e.get("sort_order") or 0):
        period = periods.get(event.get("period_id"))
        score = re.fullmatch(r"(\d+)\s*-\s*(\d+)", event.get("result") or "")
        if period not in (1, 2) or not score:
            result["issues"].append("Periodo o punteggio progressivo evento non verificabile")
            return result
        following = [int(v) for v in score.groups()]
        delta = [following[i] - running[i] for i in range(2)]
        if delta not in ([1, 0], [0, 1]):
            result["issues"].append("Sequenza dei punteggi evento incompleta o incoerente")
            return result
        # Score deltas assign own goals to the beneficiary, not the scorer's club.
        if period == 1:
            halftime = [halftime[i] + delta[i] for i in range(2)]
            if (event.get("extra_minute") or 0) > 0:
                result["stoppage_goals"] += 1
        running = following
    result["events_ht"] = halftime
    if None in result["ht"] or None in result["ft"]:
        return result
    if running != result["ft"]:
        result["issues"].append("Totale eventi diverso dal risultato finale")
        return result
    if halftime != result["ht"]:
        result["status"] = "conflict"
        result["issues"].append("Gol del periodo 1 diversi dal punteggio 1ST_HALF")
    else:
        result["status"] = "verified_with_warning" if result["issues"] else "verified"
    return result
