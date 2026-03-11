from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .market_registry import MARKET_REGISTRY, player_market_to_canonical


@dataclass
class ProviderRoute:
    data_source: str
    provider: Any


class ProviderRouter:
    """Routes markets to the provider required by market registry metadata."""

    def __init__(
        self,
        *,
        box_score_provider: Any,
        play_by_play_provider: Any | None = None,
        scoreboard_provider: Any | None = None,
        gamecast_provider: Any | None = None,
    ) -> None:
        self._box_score_provider = box_score_provider
        self._play_by_play_provider = play_by_play_provider
        self._scoreboard_provider = scoreboard_provider
        self._gamecast_provider = gamecast_provider

    def route(self, market_type: str) -> ProviderRoute:
        canonical_market = player_market_to_canonical(market_type)
        entry = MARKET_REGISTRY.get(canonical_market or '')
        required_data_source = (entry or {}).get('required_data_source', 'box_score')
        if required_data_source == 'play_by_play':
            return ProviderRoute(data_source='play_by_play', provider=self._play_by_play_provider)
        return ProviderRoute(data_source='box_score', provider=self._box_score_provider)

    @property
    def scoreboard_provider(self) -> Any | None:
        return self._scoreboard_provider

    @property
    def gamecast_provider(self) -> Any | None:
        return self._gamecast_provider
