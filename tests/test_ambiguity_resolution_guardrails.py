from __future__ import annotations

from time import sleep

from app.models import Leg
from app.resolver import resolve_leg_events


class SlowProvider:
    def __init__(self) -> None:
        self.player_candidate_calls = 0
        self.team_candidate_calls = 0

    def resolve_player_event_candidates(self, player: str, as_of, *, include_historical: bool = False):
        self.player_candidate_calls += 1
        sleep(0.3)
        return []

    def resolve_team_event_candidates(self, team: str, as_of, *, include_historical: bool = False):
        self.team_candidate_calls += 1
        sleep(0.3)
        return []

    def resolve_player_team(self, player: str, as_of, *, include_historical: bool = False):
        sleep(0.3)
        return None



def test_ambiguous_names_downgrade_fast_without_provider_resolution_calls() -> None:
    provider = SlowProvider()
    legs = [
        Leg(raw_text='J Williams Over 15 Points', sport='NBA', market_type='player_points', player='J Williams', direction='over', line=15.0, confidence=0.95),
        Leg(raw_text='Porter Jr Over 4 Rebounds', sport='NBA', market_type='player_rebounds', player='Porter Jr', direction='over', line=4.0, confidence=0.95),
        Leg(raw_text='Brown 5+ Assists', sport='NBA', market_type='player_assists', player='Brown', direction='over', line=4.5, confidence=0.95),
    ]

    resolved = resolve_leg_events(legs, provider, posted_at=None, include_historical=True)
    assert provider.player_candidate_calls == 0
    assert provider.team_candidate_calls == 0

    for leg in resolved:
        assert leg.event_resolution_status == 'review'
        assert leg.event_review_reason_code == 'ambiguous_player'
        assert leg.resolution_path_taken == 'identity_guardrail_ambiguous_player'
        assert (leg.identity_resolution_time_ms or 0) <= 200
        assert leg.candidate_player_count and leg.candidate_player_count > 1
