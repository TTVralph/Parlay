from __future__ import annotations

from .base import MarketRegistryEntry

MLB_MARKET_REGISTRY: dict[str, MarketRegistryEntry] = {}
MLB_CANONICAL_TO_PLAYER_MARKET: dict[str, str] = {}
