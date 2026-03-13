from __future__ import annotations

from .base import MarketRegistryEntry, normalize_market_text
from .mlb import MLB_CANONICAL_TO_PLAYER_MARKET, MLB_MARKET_REGISTRY
from .nba import NBA_CANONICAL_TO_PLAYER_MARKET, NBA_MARKET_REGISTRY
from .nfl import NFL_CANONICAL_TO_PLAYER_MARKET, NFL_MARKET_REGISTRY
from .wnba import WNBA_CANONICAL_TO_PLAYER_MARKET, WNBA_MARKET_REGISTRY

SPORT_MARKET_REGISTRIES: dict[str, dict[str, MarketRegistryEntry]] = {
    'NBA': NBA_MARKET_REGISTRY,
    'MLB': MLB_MARKET_REGISTRY,
    'NFL': NFL_MARKET_REGISTRY,
    'WNBA': WNBA_MARKET_REGISTRY,
}

SPORT_CANONICAL_TO_PLAYER_MARKET: dict[str, dict[str, str]] = {
    'NBA': NBA_CANONICAL_TO_PLAYER_MARKET,
    'MLB': MLB_CANONICAL_TO_PLAYER_MARKET,
    'NFL': NFL_CANONICAL_TO_PLAYER_MARKET,
    'WNBA': WNBA_CANONICAL_TO_PLAYER_MARKET,
}


def _norm_sport(sport: str | None) -> str:
    return (sport or 'NBA').upper()


def get_market_registry(sport: str | None = None) -> dict[str, MarketRegistryEntry]:
    return SPORT_MARKET_REGISTRIES.get(_norm_sport(sport), {})


def normalize_market(raw_market_text: str, sport: str | None = None) -> str | None:
    registry = get_market_registry(sport)
    return normalize_market_text(raw_market_text, registry)


def canonical_to_player_market(canonical_market: str, sport: str | None = None) -> str | None:
    return SPORT_CANONICAL_TO_PLAYER_MARKET.get(_norm_sport(sport), {}).get(canonical_market)


def player_market_to_canonical(market_type: str, sport: str | None = None) -> str | None:
    normalized = normalize_market(market_type, sport=sport)
    if normalized:
        return normalized
    player_map = SPORT_CANONICAL_TO_PLAYER_MARKET.get(_norm_sport(sport), {})
    inverse: dict[str, str] = {}
    for canonical, market in player_map.items():
        inverse.setdefault(market, canonical)
    return inverse.get(market_type)
