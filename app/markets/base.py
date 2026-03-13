from __future__ import annotations

import re
from typing import Literal, TypedDict

MarketType = Literal['single_stat', 'combo_stat', 'milestone_prop', 'alternate_line_prop', 'derived_stat', 'event_sequence_prop']
DataSource = Literal['box_score', 'play_by_play']


class MarketRegistryEntry(TypedDict):
    canonical_market_name: str
    aliases: list[str]
    market_type: MarketType
    stat_components: list[str]
    display_name: str
    required_data_source: DataSource


def with_generated_variants(registry: dict[str, MarketRegistryEntry], milestone_bases: list[str]) -> dict[str, MarketRegistryEntry]:
    expanded = dict(registry)
    for base in milestone_bases:
        base_entry = expanded[base]
        expanded[f'{base}_milestone'] = {
            'canonical_market_name': f'{base}_milestone',
            'aliases': [f'{base} milestone', f'{base} ladder', f'{base} alt milestone'],
            'market_type': 'milestone_prop',
            'stat_components': base_entry['stat_components'],
            'display_name': f"{base_entry['display_name']} Milestone",
            'required_data_source': 'box_score',
        }
        expanded[f'{base}_alternate_line'] = {
            'canonical_market_name': f'{base}_alternate_line',
            'aliases': [f'alt {base}', f'{base} alt line', f'alternate {base}', f'alternate line {base}'],
            'market_type': 'alternate_line_prop',
            'stat_components': base_entry['stat_components'],
            'display_name': f"{base_entry['display_name']} Alternate Line",
            'required_data_source': 'box_score',
        }
    return expanded


def _normalize_key(text: str) -> str:
    cleaned = re.sub(r'[^a-z0-9+]+', ' ', text.lower()).strip()
    return re.sub(r'\s+', ' ', cleaned)


def _strip_market_noise(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r'\b(over|under|o|u)\b', ' ', lowered)
    lowered = re.sub(r'\b(alt|alternate|line|ladder|milestone|at least|or more|more than)\b', ' ', lowered)
    lowered = re.sub(r'\b\d+(?:\.\d+)?\+?\b', ' ', lowered)
    lowered = lowered.replace('>=', ' ').replace('=>', ' ').replace('+', ' ')
    return _normalize_key(lowered)


def normalize_market_text(raw_market_text: str, registry: dict[str, MarketRegistryEntry]) -> str | None:
    normalized = _normalize_key(raw_market_text)
    compact = normalized.replace(' ', '')
    denoised = _strip_market_noise(raw_market_text)
    denoised_compact = denoised.replace(' ', '')
    lowered = raw_market_text.lower()
    is_alternate = bool(re.search(r'\b(alt|alternate)\b', lowered))
    is_milestone = bool(re.search(r'\b\d+(?:\.\d+)?\+', lowered) or re.search(r'\b(at least|or more)\b', lowered))

    for canonical, entry in registry.items():
        canonical_compact = canonical.replace('_', '')
        if normalized == canonical or compact == canonical_compact or denoised == canonical or denoised_compact == canonical_compact:
            if is_alternate:
                alt_key = f'{canonical}_alternate_line'
                if alt_key in registry:
                    return alt_key
            if is_milestone:
                milestone_key = f'{canonical}_milestone'
                if milestone_key in registry:
                    return milestone_key
            return canonical
        for alias in entry['aliases']:
            alias_normalized = _normalize_key(alias)
            alias_compact = alias_normalized.replace(' ', '')
            if normalized == alias_normalized or compact == alias_compact:
                return canonical
            if denoised == alias_normalized or denoised_compact == alias_compact:
                if is_alternate:
                    alt_key = f'{canonical}_alternate_line'
                    if alt_key in registry:
                        return alt_key
                if is_milestone:
                    milestone_key = f'{canonical}_milestone'
                    if milestone_key in registry:
                        return milestone_key
                return canonical
    return None
