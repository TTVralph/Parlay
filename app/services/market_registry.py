from __future__ import annotations

import re
from typing import Literal, TypedDict


MarketType = Literal['single_stat', 'combo_stat', 'derived_stat']


class MarketRegistryEntry(TypedDict):
    canonical_market_name: str
    aliases: list[str]
    market_type: MarketType
    stat_components: list[str]
    display_name: str


MARKET_REGISTRY: dict[str, MarketRegistryEntry] = {
    'points': {
        'canonical_market_name': 'points',
        'aliases': ['points', 'point', 'pts'],
        'market_type': 'single_stat',
        'stat_components': ['PTS'],
        'display_name': 'Points',
    },
    'rebounds': {
        'canonical_market_name': 'rebounds',
        'aliases': ['rebounds', 'reb', 'rebs', 'boards'],
        'market_type': 'single_stat',
        'stat_components': ['REB'],
        'display_name': 'Rebounds',
    },
    'assists': {
        'canonical_market_name': 'assists',
        'aliases': ['assists', 'assist', 'ast', 'asts'],
        'market_type': 'single_stat',
        'stat_components': ['AST'],
        'display_name': 'Assists',
    },
    'threes': {
        'canonical_market_name': 'threes',
        'aliases': ['threes', '3s', '3pm', '3 ptm', '3pt made', '3ptm', 'made threes', 'three pointers', 'three-pointers', 'three pointers made', 'three-pointers made'],
        'market_type': 'single_stat',
        'stat_components': ['3PM'],
        'display_name': 'Threes Made',
    },
    'steals': {
        'canonical_market_name': 'steals',
        'aliases': ['steals', 'stl', 'steal'],
        'market_type': 'single_stat',
        'stat_components': ['STL'],
        'display_name': 'Steals',
    },
    'blocks': {
        'canonical_market_name': 'blocks',
        'aliases': ['blocks', 'blk', 'block'],
        'market_type': 'single_stat',
        'stat_components': ['BLK'],
        'display_name': 'Blocks',
    },
    'turnovers': {
        'canonical_market_name': 'turnovers',
        'aliases': ['turnovers', 'turnover', 'tov'],
        'market_type': 'single_stat',
        'stat_components': ['TOV'],
        'display_name': 'Turnovers',
    },
    'pra': {
        'canonical_market_name': 'pra',
        'aliases': ['pra', 'p+r+a', 'pts+reb+ast', 'points rebounds assists', 'pts reb ast', 'points + rebounds + assists'],
        'market_type': 'combo_stat',
        'stat_components': ['PTS', 'REB', 'AST'],
        'display_name': 'PRA',
    },
    'pr': {
        'canonical_market_name': 'pr',
        'aliases': ['pr', 'p+r', 'pts+reb', 'points rebounds', 'points + rebounds'],
        'market_type': 'combo_stat',
        'stat_components': ['PTS', 'REB'],
        'display_name': 'PR',
    },
    'pa': {
        'canonical_market_name': 'pa',
        'aliases': ['pa', 'p+a', 'pts+ast', 'points assists', 'points + assists'],
        'market_type': 'combo_stat',
        'stat_components': ['PTS', 'AST'],
        'display_name': 'PA',
    },
    'ra': {
        'canonical_market_name': 'ra',
        'aliases': ['ra', 'r+a', 'reb+ast', 'rebounds assists', 'rebounds + assists'],
        'market_type': 'combo_stat',
        'stat_components': ['REB', 'AST'],
        'display_name': 'RA',
    },
    # Scaffolding for future derived markets
    'double_double': {
        'canonical_market_name': 'double_double',
        'aliases': ['double double', 'double-double'],
        'market_type': 'derived_stat',
        'stat_components': [],
        'display_name': 'Double Double',
    },
    'triple_double': {
        'canonical_market_name': 'triple_double',
        'aliases': ['triple double', 'triple-double'],
        'market_type': 'derived_stat',
        'stat_components': [],
        'display_name': 'Triple Double',
    },
    'fantasy_points': {
        'canonical_market_name': 'fantasy_points',
        'aliases': ['fantasy points', 'fantasy score'],
        'market_type': 'derived_stat',
        'stat_components': [],
        'display_name': 'Fantasy Points',
    },
}

CANONICAL_TO_PLAYER_MARKET = {
    'points': 'player_points',
    'rebounds': 'player_rebounds',
    'assists': 'player_assists',
    'threes': 'player_threes',
    'steals': 'player_steals',
    'blocks': 'player_blocks',
    'turnovers': 'player_turnovers',
    'pra': 'player_pra',
    'pr': 'player_pr',
    'pa': 'player_pa',
    'ra': 'player_ra',
    'double_double': 'player_double_double',
    'triple_double': 'player_triple_double',
}

PLAYER_MARKET_TO_CANONICAL = {value: key for key, value in CANONICAL_TO_PLAYER_MARKET.items()}


def _normalize_key(text: str) -> str:
    cleaned = re.sub(r'[^a-z0-9+]+', ' ', text.lower()).strip()
    return re.sub(r'\s+', ' ', cleaned)


def normalize_market(raw_market_text: str) -> str | None:
    normalized = _normalize_key(raw_market_text)
    compact = normalized.replace(' ', '')
    for canonical, entry in MARKET_REGISTRY.items():
        if normalized == canonical or compact == canonical.replace('_', ''):
            return canonical
        for alias in entry['aliases']:
            alias_normalized = _normalize_key(alias)
            if normalized == alias_normalized or compact == alias_normalized.replace(' ', ''):
                return canonical
    return None


def canonical_to_player_market(canonical_market: str) -> str | None:
    return CANONICAL_TO_PLAYER_MARKET.get(canonical_market)


def player_market_to_canonical(market_type: str) -> str | None:
    normalized = normalize_market(market_type)
    if normalized:
        return normalized
    return PLAYER_MARKET_TO_CANONICAL.get(market_type)
