"""Compare normalized observations without acquisition timestamps or row ordering."""
import json

SYNC_LOCK = 740182630


def canonical(value):
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items() if k != 'fetched_at'}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def changed_fixtures(snapshot, old_players, old_teams):
    def groups(players, teams):
        result = {}
        for kind, rows in [('players', players), ('teams', teams)]:
            for row in rows:
                key = (row['provider'], str(row['fixture']))
                result.setdefault(key, {'players': [], 'teams': []})[kind].append(
                    json.dumps(canonical(row), sort_keys=True, ensure_ascii=False))
        for group in result.values():
            for values in group.values():
                values.sort()
        return result
    old = groups(old_players, old_teams)
    new = groups(snapshot['players'], snapshot['teams'])
    return {k for k, v in new.items() if old.get(k) != v}
