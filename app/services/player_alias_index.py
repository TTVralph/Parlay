from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Iterable

_SUFFIX_TOKENS = {
    'jr', 'sr', 'ii', 'iii', 'iv', 'v', 'vi',
}


@dataclass(frozen=True)
class SnapshotPlayerMatch:
    entry: dict[str, object] | None
    strategy: str


def normalize_player_name(value: str | None) -> str:
    text = str(value or '').strip().lower()
    if not text:
        return ''
    text = re.sub(r"[^a-z0-9\s]", ' ', text)
    tokens = [token for token in text.split() if token]
    if tokens and tokens[-1] in _SUFFIX_TOKENS:
        tokens = tokens[:-1]
    return ' '.join(tokens)


def player_aliases_from_name(player_name: str | None) -> set[str]:
    normalized = normalize_player_name(player_name)
    if not normalized:
        return set()
    tokens = normalized.split()
    aliases = {normalized}
    if len(tokens) >= 2:
        aliases.add(f'{tokens[0][0]} {tokens[-1]}')
    if tokens:
        aliases.add(tokens[0])
    return {alias for alias in aliases if alias}


def build_player_alias_index(player_entries: Iterable[dict[str, object]]) -> dict[str, str]:
    alias_candidates: dict[str, set[str]] = {}
    for entry in player_entries:
        player_id = str(entry.get('player_id') or '').strip()
        if not player_id:
            continue
        for alias in player_aliases_from_name(str(entry.get('display_name') or '')):
            alias_candidates.setdefault(alias, set()).add(player_id)
        for explicit in entry.get('aliases') or []:
            normalized_alias = normalize_player_name(str(explicit))
            if normalized_alias:
                alias_candidates.setdefault(normalized_alias, set()).add(player_id)

    resolved: dict[str, str] = {}
    for alias, ids in alias_candidates.items():
        if len(ids) == 1:
            resolved[alias] = next(iter(ids))
    return resolved


def resolve_snapshot_player(
    *,
    player_entries: Iterable[dict[str, object]],
    player_id: str | None,
    player_name: str | None,
    enable_fuzzy: bool = False,
    fuzzy_threshold: float = 0.94,
) -> SnapshotPlayerMatch:
    entries = list(player_entries)
    normalized_target = normalize_player_name(player_name)

    if player_id:
        wanted = str(player_id).strip()
        for entry in entries:
            if str(entry.get('player_id') or '').strip() == wanted:
                return SnapshotPlayerMatch(entry=entry, strategy='direct_match')

    if normalized_target:
        for entry in entries:
            if normalize_player_name(str(entry.get('display_name') or '')) == normalized_target:
                return SnapshotPlayerMatch(entry=entry, strategy='normalized_match')

    if normalized_target:
        alias_index = build_player_alias_index(entries)
        matched_id = alias_index.get(normalized_target)
        if matched_id:
            for entry in entries:
                if str(entry.get('player_id') or '').strip() == matched_id:
                    return SnapshotPlayerMatch(entry=entry, strategy='alias_match')

    if enable_fuzzy and normalized_target:
        best_ratio = 0.0
        best_entry: dict[str, object] | None = None
        for entry in entries:
            candidate = normalize_player_name(str(entry.get('display_name') or ''))
            if not candidate:
                continue
            ratio = SequenceMatcher(None, normalized_target, candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_entry = entry
        if best_entry is not None and best_ratio >= fuzzy_threshold:
            return SnapshotPlayerMatch(entry=best_entry, strategy='fuzzy_match')

    return SnapshotPlayerMatch(entry=None, strategy='match_failed')
