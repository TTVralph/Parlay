from __future__ import annotations

import re
import unicodedata
from typing import Any

_SUFFIX_PATTERN = re.compile(r'\b(jr|sr|ii|iii|iv|v)\b')
_INITIALS_DOTTED_PATTERN = re.compile(r'\b([a-z])\.(?=[a-z]\.)')


def _ascii_fold(text: str) -> str:
    decomposed = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def normalize_person_name(text: str) -> str:
    folded = _ascii_fold(text or '').lower()
    folded = folded.replace('&', ' and ')
    folded = folded.replace('’', "'").replace('`', "'").replace('´', "'")
    folded = folded.replace('-', ' ')
    folded = _INITIALS_DOTTED_PATTERN.sub(r'\1', folded)
    folded = re.sub(r"[.']", '', folded)
    folded = _SUFFIX_PATTERN.sub(' ', folded)
    folded = re.sub(r'[^a-z0-9\s]', ' ', folded)
    return _normalize_whitespace(folded)


def normalize_team_name(text: str) -> str:
    folded = _ascii_fold(text or '').lower()
    folded = folded.replace('&', ' and ')
    folded = folded.replace('-', ' ')
    folded = re.sub(r"[.'’`´]", '', folded)
    folded = re.sub(r'[^a-z0-9\s]', ' ', folded)
    return _normalize_whitespace(folded)


def generate_player_aliases(player_record: dict[str, Any]) -> set[str]:
    canonical_name = str(player_record.get('full_name') or player_record.get('canonical_name') or '').strip()
    if not canonical_name:
        return set()
    parts = [part for part in re.split(r'\s+', canonical_name) if part]

    aliases: set[str] = {canonical_name}
    aliases.update(str(alias).strip() for alias in player_record.get('aliases', []) or [] if str(alias).strip())
    aliases.update(str(alias).strip() for alias in player_record.get('alias_keys', []) or [] if str(alias).strip())

    if len(parts) >= 2:
        first = parts[0]
        last = parts[-1]
        aliases.add(last)
        aliases.add(f'{first[0]}. {last}')
        aliases.add(f'{first[0]} {last}')
        compact_initials = ''.join(token[0] for token in parts[:-1] if token and token[0].isalpha())
        if compact_initials:
            aliases.add(f'{compact_initials} {last}')
            dotted = '.'.join(ch for ch in compact_initials)
            aliases.add(f'{dotted}. {last}')

    normalized_aliases = {normalize_person_name(alias) for alias in aliases if alias}
    aliases.update({alias for alias in normalized_aliases if alias})
    return {alias for alias in aliases if alias}
