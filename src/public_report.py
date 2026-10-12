"""Public presentation labels; original source provenance stays in storage."""
import re


def public_report(value):
    if isinstance(value, dict):
        return {key: public_report(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public_report(item) for item in value]
    if isinstance(value, str):
        return re.sub('understat', 'Archivio integrativo', value, flags=re.I)
    return value
