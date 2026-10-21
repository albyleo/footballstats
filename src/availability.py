"""Fixture-specific reported absences. Missing reports never mean a healthy squad."""
from datetime import datetime, timezone
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'data/providers/sportmonks/availability.json'
MAX_AGE_HOURS = 48


def load():
    if not PATH.exists():
        return {}
    try:
        value = json.loads(PATH.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) and isinstance(value.get('fixtures'), list) else {}
    except (ValueError, OSError):
        return {}


def normalize(matches, fetched_at):
    """Keep only scheduled fixtures and the provider's explicit absence records."""
    fixtures = []
    for match in matches:
        if (match.get('state') or {}).get('state') != 'NS' or match.get('placeholder'):
            continue
        day = datetime.strptime(match['starting_at'][:10], '%Y-%m-%d').date().isoformat()
        participants = match.get('participants') or []
        sides = {(p.get('meta') or {}).get('location'): p for p in participants}
        if len(participants) != 2 or set(sides) != {'home', 'away'}:
            raise ValueError('Invalid fixture participants')
        league, season = (match.get('league') or {}).get('name'), (match.get('season') or {}).get('name')
        if not league or not season:
            raise ValueError('Missing fixture competition')
        ids = {p['id'] for p in participants}
        absent, seen = [], set()
        supplied = isinstance(match.get('sidelined'), list)
        for item in match.get('sidelined') or []:
            detail, player, kind = item.get('sideline') or {}, item.get('player') or {}, item.get('type') or {}
            pid = item.get('player_id') or detail.get('player_id')
            tid = item.get('participant_id')
            if type(pid) is not int or pid <= 0 or tid not in ids:
                raise ValueError('Invalid absence identity')
            if detail.get('completed') is True or (tid, pid) in seen:
                continue
            seen.add((tid, pid))
            category = detail.get('category')
            if category not in ('injury', 'suspension'):
                code = str(kind.get('code') or '').lower()
                category = ('suspension' if 'suspend' in code or 'suspension' in code else
                            'injury' if 'injury' in code else 'unavailable')
            absent.append(dict(provider='sportmonks', id=pid, team_id=tid,
                               name=player.get('display_name') or player.get('name') or f'Giocatore {pid}',
                               category=category, reason=kind.get('name') or 'Motivo non specificato',
                               start=detail.get('start_date'), expected_end=detail.get('end_date')))
        fixtures.append(dict(id=str(match['id']), league=league, season=season, date=day,
                             home=sides['home']['name'], away=sides['away']['name'],
                             home_id=sides['home']['id'], away_id=sides['away']['id'],
                             fetched_at=fetched_at, absences_supplied=supplied, absences=absent))
    return dict(provider='sportmonks', fetched_at=fetched_at, fixtures=fixtures)


def for_fixture(archive, league, season, team, opponent, day, reference=(), *, now=None):
    result = dict(status='missing', source=None, checked_at=None, absences=[],
                  reference_absent=None, reference_size=len(reference), max_age_hours=MAX_AGE_HOURS,
                  message='Assenze non disponibili per questa partita. La disponibilità della rosa è sconosciuta.')
    candidates = [f for f in archive.get('fixtures', [])
                  if (f['league'], f['season'], f['date']) == (league, season, day)
                  and {f['home'], f['away']} == {team, opponent}]
    if not candidates:
        return result
    fixture = max(candidates, key=lambda f: f.get('fetched_at', ''))
    result.update(source='Sportmonks', checked_at=fixture.get('fetched_at'))
    if not fixture.get('absences_supplied'):
        return result
    try:
        checked = datetime.fromisoformat(fixture['fetched_at'])
        if checked.tzinfo is None:
            return result
        age = ((now or datetime.now(timezone.utc)) - checked).total_seconds() / 3600
        if age < 0:
            return result
    except (TypeError, ValueError, KeyError):
        return result
    tid = fixture['home_id'] if fixture['home'] == team else fixture['away_id']
    absent = [a for a in fixture['absences'] if a['team_id'] == tid]
    reference_ids = {(p.get('provider'), str(p['id'])) for p in reference}
    result['absences'] = [{**a, 'in_reference': (a['provider'], str(a['id'])) in reference_ids} for a in absent]
    if age > MAX_AGE_HOURS:
        return {**result, 'status':'stale', 'message':'Ultima segnalazione oltre 48 ore fa: elenco da riconfermare, non disponibilità attuale.'}
    result.update(status='reported' if absent else 'none_reported',
                  reference_absent=sum(a['in_reference'] for a in result['absences']) if len(reference) == 11 else None,
                  message='Indisponibili segnalati dal feed per questo incontro.' if absent else
                          'Nessun indisponibile segnalato dal feed. Non conferma che tutta la rosa sia disponibile.')
    return result
