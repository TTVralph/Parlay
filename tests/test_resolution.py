from datetime import datetime, timezone

from app.grader import grade_text
from app.models import Leg
from app.providers.base import EventInfo
from app.providers.sample_provider import SampleResultsProvider
from app.resolver import resolve_leg_events


def test_date_resolution_uses_posted_time_for_denver_game() -> None:
    provider = SampleResultsProvider()
    result = grade_text(
        'Jokic 25+ pts\nDenver ML',
        provider=provider,
        posted_at=datetime.fromisoformat('2026-03-07T18:15:00'),
    )
    assert result.legs[0].leg.event_id == 'nba-2026-03-07-den-lal'
    assert result.legs[1].leg.event_id == 'nba-2026-03-07-den-lal'
    assert result.legs[0].settlement == 'win'
    assert result.legs[1].settlement == 'win'


def test_date_resolution_switches_to_later_jokic_game() -> None:
    provider = SampleResultsProvider()
    result = grade_text(
        'Jokic 25+ pts',
        provider=provider,
        posted_at=datetime.fromisoformat('2026-03-09T18:00:00'),
    )
    assert result.legs[0].leg.event_id == 'nba-2026-03-09-okc-den'
    assert result.legs[0].settlement == 'loss'


class OpponentFilterProvider:
    def resolve_team_event(self, team: str, as_of: datetime | None):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None):
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None):
        if player != 'Draymond':
            return []
        return [
            EventInfo(event_id='evt-bos-gsw', sport='NBA', home_team='Boston Celtics', away_team='Golden State Warriors', start_time=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            EventInfo(event_id='evt-okc-gsw', sport='NBA', home_team='Oklahoma City Thunder', away_team='Golden State Warriors', start_time=datetime(2026, 1, 2, tzinfo=timezone.utc)),
        ]

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_opponent_context_filters_ambiguous_player_event_candidates() -> None:
    provider = OpponentFilterProvider()
    leg = Leg(raw_text='Draymond 5+ Assists Vs Thunder', sport='NBA', market_type='player_assists', player='Draymond', direction='over', line=4.5, confidence=0.82, notes=['Opponent context: Oklahoma City Thunder'])
    resolved = resolve_leg_events([leg], provider, posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert resolved[0].event_id == 'evt-okc-gsw'
