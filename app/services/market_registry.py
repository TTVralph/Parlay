from __future__ import annotations

from app.markets import (
    canonical_to_player_market as _canonical_to_player_market,
    get_market_registry,
    normalize_market as _normalize_market,
    player_market_to_canonical as _player_market_to_canonical,
)

MARKET_REGISTRY = get_market_registry('NBA')


def normalize_market(raw_market_text: str, sport: str | None = None) -> str | None:
    return _normalize_market(raw_market_text, sport=sport)


def canonical_to_player_market(canonical_market: str, sport: str | None = None) -> str | None:
    return _canonical_to_player_market(canonical_market, sport=sport)


def player_market_to_canonical(market_type: str, sport: str | None = None) -> str | None:
    return _player_market_to_canonical(market_type, sport=sport)
