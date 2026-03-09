from __future__ import annotations

import re

MARKET_MAP = {
    'pts': 'points', 'point': 'points', 'points': 'points',
    'reb': 'rebounds', 'rebs': 'rebounds', 'rebounds': 'rebounds',
    'ast': 'assists', 'asts': 'assists', 'assists': 'assists',
    '3pt': 'threes', '3pts': 'threes', '3pm': 'threes', 'threes': 'threes',
}


def normalize_market(market: str | None) -> str | None:
    if not market:
        return None
    m = re.sub(r'\s+', ' ', market.strip().lower())
    return MARKET_MAP.get(m, m)


def normalize_selection(selection: str | None) -> str | None:
    if not selection:
        return None
    s = selection.strip().lower()
    if s in {'o', 'over'}:
        return 'over'
    if s in {'u', 'under'}:
        return 'under'
    return s
