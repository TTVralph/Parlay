from __future__ import annotations

from datetime import datetime

from app.providers.base import EventInfo
from app.services.nba_game_resolver import resolve_player_game


class _AbbrOnlyTeamProvider:
    def resolve_team_event(self, team, as_of, *, include_historical=False):
        return None

    def resolve_player_event(self, player, as_of, *, include_historical=False):
        return None

    def resolve_player_event_candidates(self, player, as_of, *, include_historical=False):
        return []

    def resolve_team_event_candidates(self, team, as_of, *, include_historical=False):
        if team != 'BOS':
            return []
        return [
            EventInfo(
                event_id='evt-bos-nyk',
                sport='NBA',
                home_team='Boston Celtics',
                away_team='New York Knicks',
                start_time=datetime.fromisoformat('2026-03-06T00:30:00+00:00'),
            )
        ]

    def get_team_result(self, team, event_id=None):
        return None

    def get_player_result(self, player, market_type, event_id=None):
        return None


def test_resolve_player_game_uses_identity_cache_team_aliases() -> None:
    provider = _AbbrOnlyTeamProvider()
    game = resolve_player_game('Jaylen Brown', '2026-03-06', provider=provider)
    assert game is not None
    assert game.event_id == 'evt-bos-nyk'
