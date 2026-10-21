"""Stable profile identifiers shared by the explorer and Premium analytics."""
import hashlib


def identity(row, kind):
    parts = [kind, row['league'], row['season'], row['team']]
    if kind == 'players':
        parts += [row['provider'], str(row['id'])]
    return hashlib.sha256('\0'.join(parts).encode()).hexdigest()[:24]
