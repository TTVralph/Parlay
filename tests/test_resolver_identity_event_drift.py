from __future__ import annotations

from datetime import date, datetime

from app.identity_resolution import resolve_player_identity
from app.models import Leg
from app.providers.base import EventInfo
from app.resolver import resolve_leg_events


class DriftProvider:
    def __init__(self) -> None:
        self._events_by_player = {
            'Jalen': [
                EventInfo(event_id='evt-jal-1', sport='NBA', home_team='Boston Celtics', away_team='Miami Heat', start_time=datetime.fromisoformat('2026-03-06T20:00:00')),
                EventInfo(event_id='evt-jal-2', sport='NBA', home_team='Denver Nuggets', away_team='Phoenix Suns', start_time=datetime.fromisoformat('2026-03-06T22:30:00')),
            ],
            'Jamal Murray': [
                EventInfo(event_id='evt-den-day', sport='NBA', home_team='Denver Nuggets', away_team='Utah Jazz', start_time=datetime.fromisoformat('2026-03-06T20:00:00')),
                EventInfo(event_id='evt-den-nearby', sport='NBA', home_team='Denver Nuggets', away_team='Dallas Mavericks', start_time=datetime.fromisoformat('2026-03-07T00:30:00+00:00')),
                EventInfo(event_id='evt-den-boundary', sport='NBA', home_team='Denver Nuggets', away_team='Sacramento Kings', start_time=datetime.fromisoformat('2026-03-07T02:00:00+00:00')),
            ],
            "D'Angelo Russell": [
                EventInfo(event_id='evt-dlo', sport='NBA', home_team='Los Angeles Lakers', away_team='Phoenix Suns', start_time=datetime.fromisoformat('2026-03-06T21:00:00')),
            ],
            'Gary Payton II': [
                EventInfo(event_id='evt-gp2', sport='NBA', home_team='Golden State Warriors', away_team='Houston Rockets', start_time=datetime.fromisoformat('2026-03-06T21:00:00')),
            ],
            'Scotty Pippen Jr.': [
                EventInfo(event_id='evt-spj', sport='NBA', home_team='Memphis Grizzlies', away_team='Utah Jazz', start_time=datetime.fromisoformat('2026-03-06T21:00:00')),
            ],
            'Shai Gilgeous-Alexander': [
                EventInfo(event_id='evt-sga', sport='NBA', home_team='Oklahoma City Thunder', away_team='Minnesota Timberwolves', start_time=datetime.fromisoformat('2026-03-06T21:00:00')),
            ],
            'Cam Thomas': [
                EventInfo(event_id='evt-bkn', sport='NBA', home_team='Brooklyn Nets', away_team='Atlanta Hawks', start_time=datetime.fromisoformat('2026-03-06T20:00:00')),
                EventInfo(event_id='evt-phx', sport='NBA', home_team='Phoenix Suns', away_team='Dallas Mavericks', start_time=datetime.fromisoformat('2026-03-06T22:00:00')),
            ],
            'Stephen Curry': [
                EventInfo(event_id='evt-curry', sport='NBA', home_team='Golden State Warriors', away_team='Los Angeles Lakers', start_time=datetime.fromisoformat('2026-03-06T22:00:00')),
            ],
        }

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        if team == 'Phoenix Suns':
            return [
                EventInfo(event_id='evt-phx', sport='NBA', home_team='Phoenix Suns', away_team='Dallas Mavericks', start_time=datetime.fromisoformat('2026-03-06T22:00:00')),
            ]
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return list(self._events_by_player.get(player, []))

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Cam Thomas':
            # Intentionally stale team hint to simulate traded-player drift.
            return 'Phoenix Suns'
        return None

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_ambiguous_player_name_without_bet_date_stays_in_review() -> None:
    leg = Leg(raw_text='Jalen over 15.5 points', sport='NBA', market_type='player_points', player='Jalen', direction='over', line=15.5, confidence=0.9)
    resolved = resolve_leg_events([leg], DriftProvider(), posted_at=None, include_historical=True)

    assert resolved[0].event_id is None
    assert resolved[0].event_review_reason_code in {'ambiguous_player', 'multiple_plausible_events'}
    assert 'fast_review_guardrail' in resolved[0].event_resolution_warnings


def test_suffix_name_variants_resolve_identity() -> None:
    assert resolve_player_identity('Scotty Pippen Jr', sport='NBA').resolved_player_name == 'Scotty Pippen Jr.'
    assert resolve_player_identity('Gary Payton II', sport='NBA').resolved_player_name == 'Gary Payton II'
    assert resolve_player_identity('Robert Williams III', sport='NBA').resolved_player_name == 'Robert Williams III'


def test_hyphenated_and_apostrophe_names_resolve_identity() -> None:
    assert resolve_player_identity('Shai Gilgeous Alexander', sport='NBA').resolved_player_name == 'Shai Gilgeous-Alexander'
    assert resolve_player_identity('DAngelo Russell', sport='NBA').resolved_player_name == "D'Angelo Russell"


def test_multiple_nearby_candidates_stay_in_review_without_explicit_bet_date() -> None:
    leg = Leg(raw_text='Jamal Murray over 23.5 points', sport='NBA', market_type='player_points', player='Jamal Murray', direction='over', line=23.5, confidence=0.9)
    resolved = resolve_leg_events([leg], DriftProvider(), posted_at=date(2026, 3, 6), include_historical=True)

    assert resolved[0].event_id is None
    assert resolved[0].event_resolution_status == 'review'
    assert 'multiple_candidate_events' in resolved[0].event_resolution_warnings


def test_midnight_date_boundary_ambiguity_stays_in_review() -> None:
    class MidnightProvider(DriftProvider):
        def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
            if player == 'Nikola Jokic':
                return [
                    EventInfo(event_id='evt-den-exact', sport='NBA', home_team='Denver Nuggets', away_team='Utah Jazz', start_time=datetime.fromisoformat('2026-03-06T23:30:00+00:00')),
                    EventInfo(event_id='evt-den-boundary', sport='NBA', home_team='Denver Nuggets', away_team='Sacramento Kings', start_time=datetime.fromisoformat('2026-03-07T01:30:00+00:00')),
                ]
            return super().resolve_player_event_candidates(player, as_of, include_historical=include_historical)

    leg = Leg(raw_text='Nikola Jokic over 23.5 points', sport='NBA', market_type='player_points', player='Nikola Jokic', direction='over', line=23.5, confidence=0.9)
    resolved = resolve_leg_events([leg], MidnightProvider(), posted_at=date(2026, 3, 6), include_historical=True)

    assert resolved[0].event_id is None
    assert resolved[0].event_review_reason_code in {'single_candidate_after_narrowing', 'multiple_plausible_events'}


def test_stale_team_hint_and_traded_player_returns_review_candidates() -> None:
    class StaleHintProvider(DriftProvider):
        def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
            if player == 'Cam Thomas':
                return 'Phoenix Suns'
            return None

        def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
            if player == 'Cam Thomas':
                return [
                    EventInfo(event_id='evt-bkn', sport='NBA', home_team='Brooklyn Nets', away_team='Atlanta Hawks', start_time=datetime.fromisoformat('2026-03-06T20:00:00')),
                ]
            return super().resolve_player_event_candidates(player, as_of, include_historical=include_historical)

        def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
            if team == 'Phoenix Suns':
                return [
                    EventInfo(event_id='evt-phx-old', sport='NBA', home_team='Phoenix Suns', away_team='Dallas Mavericks', start_time=datetime.fromisoformat('2026-03-06T22:00:00')),
                ]
            return []

    leg = Leg(raw_text='Cam Thomas over 22.5 points', sport='NBA', market_type='player_points', player='Cam Thomas', direction='over', line=22.5, confidence=0.9)
    resolved = resolve_leg_events([leg], StaleHintProvider(), posted_at=None, include_historical=True)

    assert resolved[0].event_id is None
    assert resolved[0].event_resolution_status == 'review'
    assert 'multiple_candidate_events' in resolved[0].event_resolution_warnings


def test_manual_event_selection_remains_leg_scoped() -> None:
    provider = DriftProvider()
    legs = [
        Leg(raw_text='Cam Thomas over 22.5 points', sport='NBA', market_type='player_points', player='Cam Thomas', direction='over', line=22.5, confidence=0.9),
        Leg(raw_text='Stephen Curry over 4.5 threes', sport='NBA', market_type='player_threes', player='Stephen Curry', direction='over', line=4.5, confidence=0.9),
    ]

    resolved = resolve_leg_events(
        legs,
        provider,
        posted_at=date(2026, 3, 6),
        include_historical=True,
        selected_event_by_leg_id={'0': 'evt-phx'},
    )

    assert resolved[0].event_id == 'evt-phx'
    assert resolved[1].event_id == 'evt-curry'
