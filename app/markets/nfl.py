from __future__ import annotations

from .base import MarketRegistryEntry

NFL_MARKET_REGISTRY: dict[str, MarketRegistryEntry] = {}
NFL_CANONICAL_TO_PLAYER_MARKET: dict[str, str] = {}
