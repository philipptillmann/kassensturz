"""Human-readable interface messages only; API identities and stored data stay untouched."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def english_catalog():
    return json.loads((Path(__file__).parent / 'static/locales/en.json').read_text(encoding='utf-8'))


def translate_message(message, language='de'):
    if language != 'en' or not isinstance(message, str):
        return message
    catalog = english_catalog()
    if message in catalog:
        return catalog[message]
    # Only a known developer prefix may be translated. The remaining text can
    # contain a private category, merchant or account name and must stay intact.
    for source in sorted(catalog, key=len, reverse=True):
        if source.rstrip().endswith(':') and message.startswith(source):
            return catalog[source] + message[len(source):]
    return message
