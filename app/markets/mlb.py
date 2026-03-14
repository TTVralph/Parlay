from __future__ import annotations

from .base import MarketRegistryEntry

MLB_MARKET_REGISTRY: dict[str, MarketRegistryEntry] = {
    'hits': {
        'canonical_market_name': 'hits',
        'aliases': ['hits', 'hit'],
        'market_type': 'single_stat',
        'stat_components': ['H'],
        'display_name': 'Hits',
        'required_data_source': 'box_score',
    },
    'strikeouts': {
        'canonical_market_name': 'strikeouts',
        'aliases': ['strikeouts', 'strikeout', 'ks', 'k'],
        'market_type': 'single_stat',
        'stat_components': ['SO'],
        'display_name': 'Strikeouts',
        'required_data_source': 'box_score',
    },
    'total_bases': {
        'canonical_market_name': 'total_bases',
        'aliases': ['total bases', 'tb', 'bases'],
        'market_type': 'single_stat',
        'stat_components': ['TB'],
        'display_name': 'Total Bases',
        'required_data_source': 'box_score',
    },
}

MLB_CANONICAL_TO_PLAYER_MARKET: dict[str, str] = {
    'hits': 'player_hits',
    'strikeouts': 'player_strikeouts',
    'total_bases': 'player_total_bases',
}
