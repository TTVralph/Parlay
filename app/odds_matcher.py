from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import Leg, OddsMatchLegResponse, OddsMatchResponse
from .parser import parse_text
from .providers.factory import get_results_provider
from .resolver import resolve_leg_events


SAMPLE_BOOKMAKER_ODDS: dict[str, dict[str, list[dict]]] = {
    'draftkings': {
        'nba-2026-03-07-den-lal': [
            {'market_type': 'moneyline', 'selection': 'Denver Nuggets', 'american_odds': -145},
            {'market_type': 'spread', 'selection': 'Denver Nuggets', 'line': -3.5, 'american_odds': -110},
            {'market_type': 'game_total', 'selection': 'over', 'line': 226.5, 'american_odds': -110},
            {'market_type': 'player_points', 'selection': 'Nikola Jokic', 'line': 24.5, 'american_odds': -120},
        ],
        'nfl-2026-03-07-kc-buf': [
            {'market_type': 'moneyline', 'selection': 'Kansas City Chiefs', 'american_odds': -135},
            {'market_type': 'spread', 'selection': 'Kansas City Chiefs', 'line': -3.5, 'american_odds': -108},
            {'market_type': 'game_total', 'selection': 'over', 'line': 48.5, 'american_odds': -110},
            {'market_type': 'player_passing_yards', 'selection': 'Patrick Mahomes', 'line': 274.5, 'american_odds': -115},
        ],
        'mlb-2026-03-07-nyy-bos': [
            {'market_type': 'moneyline', 'selection': 'New York Yankees', 'american_odds': -125},
            {'market_type': 'spread', 'selection': 'New York Yankees', 'line': -1.5, 'american_odds': +140},
            {'market_type': 'game_total', 'selection': 'over', 'line': 8.5, 'american_odds': -105},
            {'market_type': 'player_hits', 'selection': 'Aaron Judge', 'line': 1.5, 'american_odds': +135},
        ],
    },
    'fanduel': {
        'nba-2026-03-07-den-lal': [
            {'market_type': 'moneyline', 'selection': 'Denver Nuggets', 'american_odds': -148},
            {'market_type': 'spread', 'selection': 'Denver Nuggets', 'line': -4.0, 'american_odds': -110},
            {'market_type': 'game_total', 'selection': 'under', 'line': 227.5, 'american_odds': -110},
        ]
    },
    'bet365': {
        'nba-2026-03-07-den-lal': [
            {'market_type': 'moneyline', 'selection': 'Denver Nuggets', 'american_odds': -150},
            {'market_type': 'spread', 'selection': 'Denver Nuggets', 'line': -3.5, 'american_odds': -112},
            {'market_type': 'game_total', 'selection': 'over', 'line': 227.5, 'american_odds': -110},
        ]
    },
}


def _selection_for_leg(leg: Leg) -> str | None:
    if leg.market_type in {'moneyline', 'spread'}:
        return leg.team
    if leg.market_type == 'game_total':
        return leg.direction
    return leg.player


def match_ticket_odds(text: str, bookmaker: str, posted_at: datetime | None = None) -> OddsMatchResponse:
    provider = get_results_provider()
    legs = resolve_leg_events(parse_text(text), provider, posted_at)
    book = bookmaker.lower().strip()
    matched: list[OddsMatchLegResponse] = []
    for leg in legs:
        if not leg.event_id:
            matched.append(OddsMatchLegResponse(raw_text=leg.raw_text, bookmaker=book, matched=False, reason='No resolved event to compare against'))
            continue
        candidates = SAMPLE_BOOKMAKER_ODDS.get(book, {}).get(leg.event_id, [])
        selection = _selection_for_leg(leg)
        found = None
        for item in candidates:
            if item['market_type'] != leg.market_type:
                continue
            if selection and item.get('selection') != selection:
                continue
            if leg.line is not None and item.get('line') is not None and abs(float(item['line']) - float(leg.line)) > 0.001:
                continue
            found = item
            break
        if found:
            matched.append(OddsMatchLegResponse(raw_text=leg.raw_text, bookmaker=book, matched=True, event_id=leg.event_id, market_type=leg.market_type, selection=selection, line=found.get('line'), offered_american_odds=found.get('american_odds'), reason='Matched exact sportsbook offering in sample snapshot'))
        else:
            matched.append(OddsMatchLegResponse(raw_text=leg.raw_text, bookmaker=book, matched=False, event_id=leg.event_id, market_type=leg.market_type, selection=selection, line=leg.line, reason='No exact market/line match found in sportsbook snapshot'))
    return OddsMatchResponse(bookmaker=book, matched_legs=matched, matched_count=sum(1 for item in matched if item.matched), total_count=len(matched))
