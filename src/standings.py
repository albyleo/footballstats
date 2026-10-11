"""Provider standings only: never infer official positions from match samples."""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'data/providers/sportmonks'
ORG_ROOT = ROOT.parent / 'football-data-org'
# Explicit names verified against the provider response; no fuzzy matching.
ORG_NAMES = {
    'Serie A': {'Como': 'Como 1907', 'Venezia': 'Venezia FC'},
    'Premier League': {'Brighton': 'Brighton Hove', 'Leeds': 'Leeds United',
        'Hull': 'Hull City', 'Ipswich': 'Ipswich Town', "Nott'm Forest": 'Nottingham', 'Coventry': 'Coventry City'},
    'La Liga': {'Barcelona': 'FC Barcelona', 'Ath Madrid': 'Atleti', 'Betis': 'Real Betis',
        'Sevilla': 'Sevilla FC', 'Sociedad': 'Real Sociedad', 'Alaves': 'Alavés', 'La Coruna': 'Deportivo',
        'Ath Bilbao': 'Athletic', 'Espanol': 'Espanyol', 'Vallecano': 'Rayo Vallecano', 'Malaga': 'Málaga'},
    'Bundesliga': {'Bayern Munich': 'Bayern', 'Werder Bremen': 'Bremen', 'FC Koln': '1. FC Köln',
        'Hamburg': 'HSV', 'Schalke 04': 'Schalke', 'Ein Frankfurt': 'Frankfurt', 'Paderborn': 'SC Paderborn'},
    'Ligue 1': {'Rennes': 'Stade Rennais', 'Lyon': 'Olympique Lyon', 'Paris SG': 'PSG',
        'Lens': 'RC Lens', 'Angers': 'Angers SCO'},
    'Primeira Liga': {'Benfica': 'SL Benfica', 'Sp Lisbon': 'Sporting CP', 'Academico Viseu': 'Acad. Viseu',
        'Sp Braga': 'Braga', 'Estrela': 'Amadora', 'Maritimo': 'Marítimo', 'Famalicao': 'Famalicão',
        'Guimaraes': 'Vitória SC', 'Nacional': 'CD Nacional', 'Estoril': 'Estoril Praia'},
}


def files():
    return sorted(ORG_ROOT.glob('standings-*.json'))


def load(root=ROOT):
    result = {}
    for path in sorted(root.glob('standings-*.json')) + (files() if root == ROOT else []):
        envelope = json.loads(path.read_text(encoding='utf-8'))
        rows = envelope.get('data')
        if not isinstance(rows, list):
            raise ValueError('Invalid standings cache')
        result[path.stem] = envelope
    return result


def index(envelopes):
    candidates = defaultdict(list)
    for envelope in envelopes.values():
        for row in envelope.get('data', []):
            if envelope.get('provider') == 'football-data.org':
                for name in set(row['names']):
                    key = ('football-data.org', row['league'], row['season'], name.casefold())
                    candidates[key].append(dict(position=row['position'], points=row.get('points'),
                        stage='Classifica generale', group=None,
                        fetched_at=envelope.get('fetched_at'), source='football-data.org'))
                continue
            season = (row.get('season') or {}).get('name')
            position = row.get('position')
            if not season or type(position) is not int or position < 1:
                continue
            key = ('sportmonks', str(row.get('league_id')), season, str(row.get('participant_id')))
            candidates[key].append(dict(position=position, points=row.get('points'),
                stage=(row.get('stage') or {}).get('name'),
                group=(row.get('group') or {}).get('name'),
                fetched_at=envelope.get('fetched_at'), source='Sportmonks'))
    # Multiple phases/groups require an explicit selection, never pick an arbitrary row.
    return {key: rows[0] for key, rows in candidates.items() if len(rows) == 1}


def lookup(values, row):
    key = (row['provider'], str(row.get('league_id')), row['season'], str(row['id']))
    if key in values:
        return values[key]
    name = ORG_NAMES.get(row['league'], {}).get(row['team'], row['team'])
    return values.get(('football-data.org', row['league'], row['season'], name.casefold()))
