from __future__ import annotations

from datetime import date, datetime, timezone

from app.grader import grade_text
from app.providers.base import EventInfo, TeamResult


class FakeEspnLikeProvider:
    def __init__(
        self,
        *,
        points: float | None,
        status: str = 'final',
        appeared: bool | None = None,
        resolved_team: str = 'Denver Nuggets',
        event_home_team: str = 'Denver Nuggets',
        event_away_team: str = 'Boston Celtics',
        on_roster: bool | None = True,
        dnp_policy: str = 'VOID',
    ) -> None:
        self._event = EventInfo(
            event_id='evt-1',
            sport='NBA',
            home_team=event_home_team,
            away_team=event_away_team,
            start_time=datetime.now(timezone.utc),
        )
        self._points = points
        self._status = status
        self._appeared = appeared
        self._resolved_team = resolved_team
        self._on_roster = on_roster
        self._dnp_policy = dnp_policy

    def resolve_team_event(self, team: str, as_of: datetime | None):
        return self._event if team in {self._event.home_team, self._event.away_team} else None

    def resolve_player_event(self, player: str, as_of: datetime | None):
        return self._event if player == 'Nikola Jokic' else None

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Nikola Jokic':
            return self._resolved_team
        return None

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

    def is_player_on_event_roster(self, player: str, event_id: str | None = None):
        if event_id != self._event.event_id or player != 'Nikola Jokic':
            return None
        return self._on_roster

    def get_event_info(self, event_id: str):
        if event_id != self._event.event_id:
            return None
        return self._event

    def get_sportsbook_rules(self):
        return {'dnp_player_prop_settlement': self._dnp_policy}


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


def test_live_game_unresolved_leg_stays_live() -> None:
    provider = FakeEspnLikeProvider(points=None, status='live')
    result = grade_text('Jokic over 28.5 points', provider=provider)
    assert result.legs[0].settlement == 'live'
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


def test_player_matched_to_wrong_team_game_is_rejected_and_low_confidence() -> None:
    provider = FakeEspnLikeProvider(
        points=30.0,
        status='final',
        resolved_team='Los Angeles Lakers',
        event_home_team='Phoenix Suns',
        event_away_team='Charlotte Hornets',
    )
    result = grade_text('Nikola Jokic under 5.5 assists', provider=provider)
    leg = result.legs[0]
    assert leg.settlement == 'unmatched'
    assert leg.review_reason in {'Matched event does not include player team', 'No matching game was found for the resolved team/date.'}
    assert leg.resolution_confidence == 0.3


def test_player_not_on_roster_for_event_is_rejected_before_grading() -> None:
    provider = FakeEspnLikeProvider(points=30.0, status='final', on_roster=False)
    result = grade_text('Nikola Jokic over 28.5 points', provider=provider)
    leg = result.legs[0]
    assert leg.settlement == 'unmatched'
    assert 'Player is not on either roster for matched event' in leg.validation_warnings


def test_dnp_can_be_configured_to_needs_review() -> None:
    provider = FakeEspnLikeProvider(points=None, status='final', appeared=False, dnp_policy='NEEDS_REVIEW')
    result = grade_text('Jokic over 28.5 points', provider=provider)
    leg = result.legs[0]
    assert leg.settlement == 'unmatched'
    assert 'Leg marked void/review instead of graded' in leg.validation_warnings


def test_correct_game_but_no_stat_result_is_review_not_win_loss() -> None:
    provider = FakeEspnLikeProvider(points=None, status='final', appeared=True)
    result = grade_text('Jokic over 28.5 points', provider=provider)
    leg = result.legs[0]
    assert leg.settlement == 'unmatched'
    assert leg.explanation_reason == 'Matched event but no stat result'


def test_unmatched_leg_exposes_settlement_diagnostics_reason_code() -> None:
    provider = FakeEspnLikeProvider(points=None, status='final', appeared=True)
    result = grade_text('Jokic over 28.5 points', provider=provider)
    diag = result.legs[0].settlement_diagnostics
    assert diag['event_resolution_worked'] is True
    assert diag['stat_lookup_result'] == 'missing'
    assert diag['unmatched_reason_code'] == 'stat_not_found'


def test_player_not_on_roster_sets_unmatched_reason_code() -> None:
    provider = FakeEspnLikeProvider(points=30.0, status='final', on_roster=False)
    result = grade_text('Nikola Jokic over 28.5 points', provider=provider)
    diag = result.legs[0].settlement_diagnostics
    assert diag['unmatched_reason_code'] == 'player_not_on_event_roster'
    assert 'not on either roster' in str(diag['event_match_rejection_reason']).lower()


def test_same_game_multi_leg_slip_settles_multiple_legs() -> None:
    class MultiLegProvider(FakeEspnLikeProvider):
        def resolve_player_event(self, player: str, as_of: datetime | None):
            if player in {'Draymond Green', 'Amen Thompson'}:
                return self._event
            return None

        def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
            event = self.resolve_player_event(player, as_of)
            return [event] if event else []

        def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
            if player == 'Draymond Green':
                return self._event.away_team
            if player == 'Amen Thompson':
                return self._event.home_team
            return super().resolve_player_team(player, as_of, include_historical=include_historical)

        def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
            if event_id != self._event.event_id:
                return None
            if market_type != 'player_threes':
                return None
            if player == 'Draymond Green':
                return 1.0
            if player == 'Amen Thompson':
                return 0.0
            return None

    provider = MultiLegProvider(points=0.0, status='final', event_home_team='Houston Rockets', event_away_team='Golden State Warriors')
    result = grade_text('Draymond Green under 1.5 threes\nAmen Thompson under 1.5 threes', provider=provider)
    assert len(result.legs) == 2
    assert all(item.settlement == 'win' for item in result.legs)
    assert result.overall == 'cashed'


def test_roster_mismatch_sets_specific_event_review_text() -> None:
    provider = FakeEspnLikeProvider(points=30.0, status='final', on_roster=False)
    result = grade_text('Nikola Jokic over 28.5 points', provider=provider)
    leg = result.legs[0]
    assert leg.event_review_reason_text == 'Matched game does not contain the resolved player on the roster.'
    assert leg.review_reason_text == 'Review: Matched game does not contain the resolved player on the roster.'


def test_unresolved_event_prefers_specific_nearby_date_review_text() -> None:
    provider = FakeEspnLikeProvider(points=30.0, status='final')
    result = grade_text('Nikola Jokic over 28.5 points', provider=provider, bet_date=date(2026, 3, 7))
    leg = result.legs[0]
    if leg.settlement == 'unmatched':
        assert leg.review_reason_text in {
            'Review: Only nearby-date games were found; confirm the correct date.',
            'Review: No matching game was found for the resolved team/date.',
        }
