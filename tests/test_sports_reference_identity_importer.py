from __future__ import annotations

from datetime import datetime

from app.identity_resolution import resolve_player_identity
from app.models import Leg
from app.providers.base import EventInfo
from app.resolver import resolve_leg_events
from app.sports_reference_identity import build_alias_keys


class _Provider:
    def __init__(self) -> None:
        self.event = EventInfo(
            event_id='nba-evt-den-test',
            sport='NBA',
            home_team='Denver Nuggets',
            away_team='Miami Heat',
            start_time=datetime.fromisoformat('2026-03-08T01:00:00+00:00'),
        )

    def resolve_team_event(self, team, as_of, *, include_historical=False):
        return None

    def resolve_player_event(self, player, as_of, *, include_historical=False):
        return None

    def resolve_team_event_candidates(self, team, as_of, *, include_historical=False):
        return [self.event] if team == 'Denver Nuggets' else []

    def resolve_player_event_candidates(self, player, as_of, *, include_historical=False):
        return [self.event]

    def get_team_result(self, team, event_id=None):
        return None

    def get_player_result(self, player, market_type, event_id=None):
        return None


def test_alias_key_generation_handles_suffixes_accents_and_apostrophes() -> None:
    keys = build_alias_keys("Nikola Topić")
    assert 'nikola topic' in keys
    keys = build_alias_keys("Kel'el Ware")
    assert 'kelel ware' in keys
    keys = build_alias_keys('Michael Porter Jr.')
    assert 'michael porter jr' in keys
    assert 'michael porter' in keys


def test_resolution_exposes_basketball_reference_metadata() -> None:
    result = resolve_player_identity('Nikola Jokic', sport='NBA')
    assert result.identity_source == 'basketball-reference'
    assert result.identity_last_refreshed_at


def test_resolver_sets_identity_diagnostics_fields() -> None:
    leg = Leg(
        raw_text='Nikola Jokic over 24.5 points',
        sport='NBA',
        market_type='player_points',
        player='Nikola Jokic',
        direction='over',
        line=24.5,
        confidence=0.95,
    )
    resolved = resolve_leg_events([leg], _Provider(), posted_at=None)
    assert resolved[0].identity_source == 'basketball-reference'
    assert resolved[0].resolved_player_name == 'Nikola Jokic'
    assert resolved[0].resolved_team_hint == 'Denver Nuggets'
