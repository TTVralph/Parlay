from __future__ import annotations

from datetime import date, datetime

from app.models import Leg
from app.providers.base import EventInfo
from app.resolver import resolve_leg_events


class TeamScopedPlayerProvider:
    def __init__(self) -> None:
        self._warriors_at_jazz_day5 = EventInfo(
            event_id='evt-gsw-uta',
            sport='NBA',
            home_team='Utah Jazz',
            away_team='Golden State Warriors',
            start_time=datetime.fromisoformat('2026-10-05T20:00:00'),
        )
        self._warriors_at_jazz_day6 = EventInfo(
            event_id='evt-gsw-uta',
            sport='NBA',
            home_team='Utah Jazz',
            away_team='Golden State Warriors',
            start_time=datetime.fromisoformat('2026-10-06T20:00:00'),
        )
        self._warriors_at_suns_day6 = EventInfo(
            event_id='evt-gsw-phx',
            sport='NBA',
            home_team='Phoenix Suns',
            away_team='Golden State Warriors',
            start_time=datetime.fromisoformat('2026-10-06T23:00:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        if team != 'Golden State Warriors':
            return []
        if as_of and as_of.date() == date(2026, 10, 5):
            return [self._warriors_at_jazz_day5]
        if as_of and as_of.date() == date(2026, 10, 6):
            return [self._warriors_at_jazz_day6, self._warriors_at_suns_day6]
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        # Intentionally noisy: returns games that don't involve the Warriors.
        return [
            EventInfo(
                event_id='evt-bos-nyk',
                sport='NBA',
                home_team='Boston Celtics',
                away_team='New York Knicks',
                start_time=datetime.fromisoformat('2026-10-05T19:00:00'),
            ),
            self._warriors_at_jazz_day5,
            EventInfo(
                event_id='evt-lal-den',
                sport='NBA',
                home_team='Los Angeles Lakers',
                away_team='Denver Nuggets',
                start_time=datetime.fromisoformat('2026-10-05T22:00:00'),
            ),
        ]

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Draymond Green':
            return 'Golden State Warriors'
        return None

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_player_props_auto_select_single_team_game_on_date() -> None:
    provider = TeamScopedPlayerProvider()
    leg = Leg(
        raw_text='Draymond Green over 5.5 assists',
        sport='NBA',
        market_type='player_assists',
        player='Draymond Green',
        direction='over',
        line=5.5,
        confidence=0.9,
    )

    resolved = resolve_leg_events([leg], provider, posted_at=date(2026, 10, 5), include_historical=True)

    assert resolved[0].event_id == 'evt-gsw-uta'
    assert resolved[0].event_candidates == []


def test_player_props_keep_dropdown_when_team_has_multiple_games_on_date() -> None:
    provider = TeamScopedPlayerProvider()
    leg = Leg(
        raw_text='Draymond Green over 5.5 assists',
        sport='NBA',
        market_type='player_assists',
        player='Draymond Green',
        direction='over',
        line=5.5,
        confidence=0.9,
    )

    resolved = resolve_leg_events([leg], provider, posted_at=date(2026, 10, 6), include_historical=True)

    assert resolved[0].event_id is None
    assert {item['event_id'] for item in resolved[0].event_candidates} == {'evt-gsw-uta', 'evt-gsw-phx'}
