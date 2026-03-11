from __future__ import annotations

import re
from typing import Literal, TypedDict


MarketType = Literal['single_stat', 'combo_stat', 'milestone_prop', 'alternate_line_prop', 'derived_stat']


class MarketRegistryEntry(TypedDict):
    canonical_market_name: str
    aliases: list[str]
    market_type: MarketType
    stat_components: list[str]
    display_name: str


MARKET_REGISTRY: dict[str, MarketRegistryEntry] = {
    'points': {
        'canonical_market_name': 'points',
        'aliases': ['points', 'point', 'pts', 'PTS'],
        'market_type': 'single_stat',
        'stat_components': ['PTS'],
        'display_name': 'Points',
    },
    'rebounds': {
        'canonical_market_name': 'rebounds',
        'aliases': ['rebounds', 'reb', 'rebs', 'boards', 'REB'],
        'market_type': 'single_stat',
        'stat_components': ['REB'],
        'display_name': 'Rebounds',
    },
    'assists': {
        'canonical_market_name': 'assists',
        'aliases': ['assists', 'assist', 'ast', 'asts', 'AST'],
        'market_type': 'single_stat',
        'stat_components': ['AST'],
        'display_name': 'Assists',
    },
    'steals': {
        'canonical_market_name': 'steals',
        'aliases': ['steals', 'stl', 'steal', 'STL'],
        'market_type': 'single_stat',
        'stat_components': ['STL'],
        'display_name': 'Steals',
    },
    'blocks': {
        'canonical_market_name': 'blocks',
        'aliases': ['blocks', 'blk', 'block', 'BLK'],
        'market_type': 'single_stat',
        'stat_components': ['BLK'],
        'display_name': 'Blocks',
    },
    'turnovers': {
        'canonical_market_name': 'turnovers',
        'aliases': ['turnovers', 'turnover', 'to', 'tov', 'TO', 'TOV'],
        'market_type': 'single_stat',
        'stat_components': ['TOV'],
        'display_name': 'Turnovers',
    },
    'three_pointers_made': {
        'canonical_market_name': 'three_pointers_made',
        'aliases': [
            'threes', '3s', '3pm', '3 ptm', '3pt made', '3ptm', '3PTM', '3PM',
            'made threes', 'three pointers', 'three-pointers', 'three pointers made', 'three-pointers made',
            'three point field goals made', 'three-point field goals made',
        ],
        'market_type': 'single_stat',
        'stat_components': ['3PM'],
        'display_name': 'Three Pointers Made',
    },
    'field_goals_made': {
        'canonical_market_name': 'field_goals_made',
        'aliases': ['field goals made', 'fgm', 'FGM', 'made field goals'],
        'market_type': 'single_stat',
        'stat_components': ['FGM'],
        'display_name': 'Field Goals Made',
    },
    'free_throws_made': {
        'canonical_market_name': 'free_throws_made',
        'aliases': ['free throws made', 'ftm', 'FTM', 'made free throws'],
        'market_type': 'single_stat',
        'stat_components': ['FTM'],
        'display_name': 'Free Throws Made',
    },
    'offensive_rebounds': {
        'canonical_market_name': 'offensive_rebounds',
        'aliases': ['offensive rebounds', 'oreb', 'OREB'],
        'market_type': 'single_stat',
        'stat_components': ['OREB'],
        'display_name': 'Offensive Rebounds',
    },
    'defensive_rebounds': {
        'canonical_market_name': 'defensive_rebounds',
        'aliases': ['defensive rebounds', 'dreb', 'DREB'],
        'market_type': 'single_stat',
        'stat_components': ['DREB'],
        'display_name': 'Defensive Rebounds',
    },
    'minutes_played': {
        'canonical_market_name': 'minutes_played',
        'aliases': ['minutes played', 'minutes', 'mins', 'min'],
        'market_type': 'single_stat',
        'stat_components': ['MIN'],
        'display_name': 'Minutes Played',
    },
    'points_rebounds': {
        'canonical_market_name': 'points_rebounds',
        'aliases': ['pr', 'p+r', 'pts+reb', 'pts + reb', 'points rebounds', 'points + rebounds', 'pts+rebs'],
        'market_type': 'combo_stat',
        'stat_components': ['PTS', 'REB'],
        'display_name': 'Points + Rebounds',
    },
    'points_assists': {
        'canonical_market_name': 'points_assists',
        'aliases': ['pa', 'p+a', 'pts+ast', 'pts + ast', 'points assists', 'points + assists'],
        'market_type': 'combo_stat',
        'stat_components': ['PTS', 'AST'],
        'display_name': 'Points + Assists',
    },
    'rebounds_assists': {
        'canonical_market_name': 'rebounds_assists',
        'aliases': ['ra', 'r+a', 'reb+ast', 'reb + ast', 'rebounds assists', 'rebounds + assists'],
        'market_type': 'combo_stat',
        'stat_components': ['REB', 'AST'],
        'display_name': 'Rebounds + Assists',
    },
    'points_rebounds_assists': {
        'canonical_market_name': 'points_rebounds_assists',
        'aliases': ['pra', 'p+r+a', 'pts+reb+ast', 'pts + reb + ast', 'pts reb ast', 'points rebounds assists', 'points + rebounds + assists', 'pts+rebs+asts'],
        'market_type': 'combo_stat',
        'stat_components': ['PTS', 'REB', 'AST'],
        'display_name': 'Points + Rebounds + Assists',
    },
    'steals_blocks': {
        'canonical_market_name': 'steals_blocks',
        'aliases': ['stocks', 'stl+blk', 'stl + blk', 'steals+blocks', 'steals + blocks', 'steals blocks'],
        'market_type': 'combo_stat',
        'stat_components': ['STL', 'BLK'],
        'display_name': 'Steals + Blocks',
    },
    'points_threes': {
        'canonical_market_name': 'points_threes',
        'aliases': ['points+threes', 'points + threes', 'pts+3pm', 'pts + 3pm', 'points three pointers made'],
        'market_type': 'combo_stat',
        'stat_components': ['PTS', '3PM'],
        'display_name': 'Points + Three Pointers Made',
    },
    'rebounds_blocks': {
        'canonical_market_name': 'rebounds_blocks',
        'aliases': ['rebounds+blocks', 'rebounds + blocks', 'reb+blk', 'reb + blk'],
        'market_type': 'combo_stat',
        'stat_components': ['REB', 'BLK'],
        'display_name': 'Rebounds + Blocks',
    },
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
}


_MILESTONE_BASE_MARKETS = [
    'points', 'rebounds', 'assists', 'steals', 'blocks', 'turnovers', 'three_pointers_made',
    'field_goals_made', 'free_throws_made', 'offensive_rebounds', 'defensive_rebounds', 'minutes_played',
    'points_rebounds', 'points_assists', 'rebounds_assists', 'points_rebounds_assists',
    'steals_blocks', 'points_threes', 'rebounds_blocks',
]

for base in _MILESTONE_BASE_MARKETS:
    base_entry = MARKET_REGISTRY[base]
    MARKET_REGISTRY[f'{base}_milestone'] = {
        'canonical_market_name': f'{base}_milestone',
        'aliases': [f'{base} milestone', f'{base} ladder', f'{base} alt milestone'],
        'market_type': 'milestone_prop',
        'stat_components': base_entry['stat_components'],
        'display_name': f"{base_entry['display_name']} Milestone",
    }
    MARKET_REGISTRY[f'{base}_alternate_line'] = {
        'canonical_market_name': f'{base}_alternate_line',
        'aliases': [f'alt {base}', f'{base} alt line', f'alternate {base}', f'alternate line {base}'],
        'market_type': 'alternate_line_prop',
        'stat_components': base_entry['stat_components'],
        'display_name': f"{base_entry['display_name']} Alternate Line",
    }


CANONICAL_TO_PLAYER_MARKET = {
    'points': 'player_points',
    'rebounds': 'player_rebounds',
    'assists': 'player_assists',
    'steals': 'player_steals',
    'blocks': 'player_blocks',
    'turnovers': 'player_turnovers',
    'three_pointers_made': 'player_threes',
    'field_goals_made': 'player_field_goals_made',
    'free_throws_made': 'player_free_throws_made',
    'offensive_rebounds': 'player_offensive_rebounds',
    'defensive_rebounds': 'player_defensive_rebounds',
    'minutes_played': 'player_minutes_played',
    'points_rebounds': 'player_pr',
    'points_assists': 'player_pa',
    'rebounds_assists': 'player_ra',
    'points_rebounds_assists': 'player_pra',
    'steals_blocks': 'player_stocks',
    'points_threes': 'player_points_threes',
    'rebounds_blocks': 'player_rebounds_blocks',
    'double_double': 'player_double_double',
    'triple_double': 'player_triple_double',
}

for key, mapped in list(CANONICAL_TO_PLAYER_MARKET.items()):
    CANONICAL_TO_PLAYER_MARKET[f'{key}_milestone'] = mapped
    CANONICAL_TO_PLAYER_MARKET[f'{key}_alternate_line'] = mapped

PLAYER_MARKET_TO_CANONICAL = {value: key for key, value in CANONICAL_TO_PLAYER_MARKET.items()}


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


def normalize_market(raw_market_text: str) -> str | None:
    normalized = _normalize_key(raw_market_text)
    compact = normalized.replace(' ', '')
    denoised = _strip_market_noise(raw_market_text)
    denoised_compact = denoised.replace(' ', '')
    lowered = raw_market_text.lower()
    is_alternate = bool(re.search(r'\b(alt|alternate)\b', lowered))
    is_milestone = bool(re.search(r'\b\d+(?:\.\d+)?\+', lowered) or re.search(r'\b(at least|or more)\b', lowered))

    for canonical, entry in MARKET_REGISTRY.items():
        canonical_compact = canonical.replace('_', '')
        if normalized == canonical or compact == canonical_compact or denoised == canonical or denoised_compact == canonical_compact:
            if is_alternate:
                alt_key = f'{canonical}_alternate_line'
                if alt_key in MARKET_REGISTRY:
                    return alt_key
            if is_milestone:
                milestone_key = f'{canonical}_milestone'
                if milestone_key in MARKET_REGISTRY:
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
                    if alt_key in MARKET_REGISTRY:
                        return alt_key
                if is_milestone:
                    milestone_key = f'{canonical}_milestone'
                    if milestone_key in MARKET_REGISTRY:
                        return milestone_key
                return canonical
    return None


def canonical_to_player_market(canonical_market: str) -> str | None:
    return CANONICAL_TO_PLAYER_MARKET.get(canonical_market)


def player_market_to_canonical(market_type: str) -> str | None:
    normalized = normalize_market(market_type)
    if normalized:
        return normalized
    return PLAYER_MARKET_TO_CANONICAL.get(market_type)
