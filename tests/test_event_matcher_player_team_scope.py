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
        self._rockets_at_spurs_day6 = EventInfo(
            event_id='evt-hou-sas',
            sport='NBA',
            home_team='San Antonio Spurs',
            away_team='Houston Rockets',
            start_time=datetime.fromisoformat('2026-10-06T20:30:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        if team == 'Golden State Warriors':
            if as_of and as_of.date() == date(2026, 10, 5):
                return [self._warriors_at_jazz_day5]
            if as_of and as_of.date() == date(2026, 10, 6):
                return [self._warriors_at_jazz_day6, self._warriors_at_suns_day6]
        if team == 'Houston Rockets' and as_of and as_of.date() == date(2026, 10, 6):
            return [self._rockets_at_spurs_day6]
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
            EventInfo(
                event_id='evt-cha-bos',
                sport='NBA',
                home_team='Boston Celtics',
                away_team='Charlotte Hornets',
                start_time=datetime.fromisoformat('2026-10-06T19:00:00'),
            ),
        ]

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Draymond Green':
            return 'Golden State Warriors'
        if player == 'Amen Thompson':
            return 'Houston Rockets'
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


def test_amen_thompson_team_filtering_excludes_unrelated_games() -> None:
    provider = TeamScopedPlayerProvider()
    leg = Leg(
        raw_text='Amen Thompson over 6.5 rebounds',
        sport='NBA',
        market_type='player_rebounds',
        player='Amen Thompson',
        direction='over',
        line=6.5,
        confidence=0.9,
    )

    resolved = resolve_leg_events([leg], provider, posted_at=date(2026, 10, 6), include_historical=True)

    assert resolved[0].event_id == 'evt-hou-sas'
    assert resolved[0].event_candidates == []


def test_unresolved_player_team_goes_to_review_without_random_games() -> None:
    provider = TeamScopedPlayerProvider()
    leg = Leg(
        raw_text='Cade Cunningham over 24.5 points',
        sport='NBA',
        market_type='player_points',
        player='Cade Cunningham',
        direction='over',
        line=24.5,
        confidence=0.9,
    )

    resolved = resolve_leg_events([leg], provider, posted_at=date(2026, 10, 6), include_historical=True)

    assert resolved[0].event_id is None
    assert resolved[0].event_candidates == []
    assert 'Player team could not be resolved' in resolved[0].notes


def test_zero_team_games_on_selected_date_returns_specific_reason() -> None:
    provider = TeamScopedPlayerProvider()
    leg = Leg(
        raw_text='Amen Thompson over 6.5 rebounds',
        sport='NBA',
        market_type='player_rebounds',
        player='Amen Thompson',
        direction='over',
        line=6.5,
        confidence=0.9,
    )
    resolved = resolve_leg_events([leg], provider, posted_at=date(2026, 10, 5), include_historical=True, bet_date=date(2026, 10, 5))
    assert resolved[0].event_id is None
    assert resolved[0].event_candidates == []
    assert "No game found for player's team on selected date" in resolved[0].notes
