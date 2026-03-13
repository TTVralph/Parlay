from __future__ import annotations

from datetime import datetime

from app.identity_resolution import resolve_player_identity
from app.models import Leg
from app.providers.base import EventInfo
from app.resolver import resolve_leg_events
from app.services.confidence_scoring import score_leg_confidence


class MultiTeamNameProvider:
    def __init__(self) -> None:
        self.okc_den = EventInfo(
            event_id='evt-okc-den',
            sport='NBA',
            home_team='Oklahoma City Thunder',
            away_team='Denver Nuggets',
            start_time=datetime.fromisoformat('2026-03-10T01:00:00+00:00'),
        )
        self.okc_dal = EventInfo(
            event_id='evt-okc-dal',
            sport='NBA',
            home_team='Oklahoma City Thunder',
            away_team='Dallas Mavericks',
            start_time=datetime.fromisoformat('2026-03-12T01:00:00+00:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        if team in {'Oklahoma City Thunder', 'Denver Nuggets'}:
            return [self.okc_den]
        if team == 'Dallas Mavericks':
            return [self.okc_dal]
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Jalen Williams':
            return [self.okc_den, self.okc_dal]
        return []

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        if player == 'Jalen Williams':
            return 'Oklahoma City Thunder'
        return None

    def did_player_appear(self, player: str, event_id: str | None = None) -> bool | None:
        return None

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_same_name_different_team_rejected_when_event_team_mismatch() -> None:
    provider = MultiTeamNameProvider()
    leg = Leg(
        raw_text='Jalen Williams over 19.5 points',
        sport='NBA',
        market_type='player_points',
        player='Jalen Williams',
        direction='over',
        line=19.5,
        confidence=0.9,
        game_matchup='Dallas Mavericks @ Oklahoma City Thunder',
    )

    resolved = resolve_leg_events([leg], provider, posted_at=datetime.fromisoformat('2026-03-10T12:00:00+00:00'), include_historical=True)
    assert resolved[0].event_id == 'evt-okc-den'
    assert resolved[0].player_team_mismatch_detected is False


def test_player_team_mismatch_is_heavily_penalized_in_confidence() -> None:
    leg = Leg(
        raw_text='Jalen Williams over 20.5 points',
        sport='NBA',
        market_type='player_points',
        player='Jalen Williams',
        direction='over',
        line=20.5,
        confidence=0.95,
        parse_confidence=0.95,
        identity_match_confidence='HIGH',
        event_resolution_confidence='high',
        player_team_mismatch_detected=True,
    )
    scored = score_leg_confidence(leg, input_source_path='manual_text')
    assert scored.confidence_score < 0.4


def test_midseason_trade_identity_prefers_legacy_team_mapping() -> None:
    resolution = resolve_player_identity('Khris Middleton', sport='NBA')
    assert resolution.resolved_team == 'Washington Wizards'


def test_wnba_player_resolution_works_with_team_context() -> None:
    resolution = resolve_player_identity('Breanna Stewart', sport='WNBA')
    assert resolution.resolved_player_id == 'wnba-breanna-stewart'
    assert resolution.resolved_team == 'New York Liberty'


def test_mlb_pitcher_batter_identity_resolves_with_teams() -> None:
    ohtani = resolve_player_identity('Shohei Ohtani', sport='MLB')
    judge = resolve_player_identity('Aaron Judge', sport='MLB')
    assert ohtani.resolved_team == 'Los Angeles Dodgers'
    assert judge.resolved_team == 'New York Yankees'


def test_nfl_player_role_stats_identity_support() -> None:
    qb = resolve_player_identity('Patrick Mahomes', sport='NFL')
    rb = resolve_player_identity('Josh Allen', sport='NFL')
    assert qb.resolved_player_id == 'nfl-patrick-mahomes'
    assert rb.resolved_player_id == 'nfl-josh-allen'
