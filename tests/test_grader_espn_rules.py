from __future__ import annotations

from datetime import datetime, timezone

from app.grader import grade_text
from app.providers.base import EventInfo, TeamResult


class FakeEspnLikeProvider:
    def __init__(self, *, points: float | None, status: str = 'final', appeared: bool | None = None) -> None:
        self._event = EventInfo(
            event_id='evt-1',
            sport='NBA',
            home_team='Denver Nuggets',
            away_team='Boston Celtics',
            start_time=datetime.now(timezone.utc),
        )
        self._points = points
        self._status = status
        self._appeared = appeared

    def resolve_team_event(self, team: str, as_of: datetime | None):
        return self._event if team in {self._event.home_team, self._event.away_team} else None

    def resolve_player_event(self, player: str, as_of: datetime | None):
        return self._event if player == 'Nikola Jokic' else None

    def get_team_result(self, team: str, event_id: str | None = None):
        if event_id != self._event.event_id:
            return None
        return TeamResult(event=self._event, moneyline_win=(team == self._event.home_team), home_score=110, away_score=100)

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        if event_id != self._event.event_id or player != 'Nikola Jokic':
            return None
        if market_type != 'player_points':
            return None
        return self._points

    def get_event_status(self, event_id: str):
        if event_id != self._event.event_id:
            return None
        return self._status

    def did_player_appear(self, player: str, event_id: str | None = None):
        if event_id != self._event.event_id or player != 'Nikola Jokic':
            return None
        return self._appeared


def test_final_game_winning_leg_is_win_and_cashed() -> None:
    provider = FakeEspnLikeProvider(points=32.0, status='final')
    result = grade_text('Jokic over 28.5 points', provider=provider)
    assert result.legs[0].settlement == 'win'
    assert result.overall == 'cashed'


def test_final_game_losing_leg_sets_overall_lost() -> None:
    provider = FakeEspnLikeProvider(points=24.0, status='final')
    result = grade_text('Jokic over 28.5 points', provider=provider)
    assert result.legs[0].settlement == 'loss'
    assert result.overall == 'lost'


def test_live_game_unresolved_leg_stays_pending() -> None:
    provider = FakeEspnLikeProvider(points=None, status='live')
    result = grade_text('Jokic over 28.5 points', provider=provider)
    assert result.legs[0].settlement == 'pending'
    assert result.overall == 'pending'


def test_unsupported_nba_bet_type_is_needs_review() -> None:
    provider = FakeEspnLikeProvider(points=300.0, status='final')
    result = grade_text('Jokic over 250.5 passing yards', provider=provider)
    assert result.legs[0].settlement == 'unmatched'
    assert result.overall == 'needs_review'


def test_final_game_dnp_leg_is_void_not_review() -> None:
    provider = FakeEspnLikeProvider(points=None, status='final', appeared=False)
    result = grade_text('Jokic over 28.5 points', provider=provider)
    assert result.legs[0].settlement == 'void'
    assert result.overall == 'needs_review'
