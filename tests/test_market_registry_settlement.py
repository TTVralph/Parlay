from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.grader import settle_leg
from app.models import Leg
from app.services.event_snapshot import EventSnapshot
from app.providers.base import EventInfo


class RegistryProvider:
    def __init__(self) -> None:
        self._event = EventInfo(
            event_id='evt-1',
            sport='NBA',
            home_team='Denver Nuggets',
            away_team='Boston Celtics',
            start_time=datetime.now(timezone.utc),
        )
        self.values = {
            'player_points': 20.0,
            'player_rebounds': 7.0,
            'player_assists': 5.0,
            'player_threes': 2.0,
            'player_steals': 1.0,
            'player_blocks': 2.0,
            'player_turnovers': 3.0,
        }

    def get_event_info(self, event_id: str):
        return self._event

    def is_player_on_event_roster(self, player: str, event_id: str | None = None):
        return True

    def get_event_status(self, event_id: str):
        return 'final'

    def did_player_appear(self, player: str, event_id: str | None = None):
        return True

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return self.values.get(market_type)


@pytest.mark.parametrize(
    ('market_type', 'line', 'expected_win', 'direction'),
    [
        ('player_points', 19.5, 'win', 'over'),
        ('player_points', 20.5, 'loss', 'over'),
        ('player_rebounds', 6.5, 'win', 'over'),
        ('player_rebounds', 7.5, 'loss', 'over'),
        ('player_assists', 4.5, 'win', 'over'),
        ('player_assists', 5.5, 'loss', 'over'),
        ('player_threes', 1.5, 'win', 'over'),
        ('player_threes', 2.5, 'loss', 'over'),
        ('player_steals', 0.5, 'win', 'over'),
        ('player_steals', 1.5, 'loss', 'over'),
        ('player_blocks', 1.5, 'win', 'over'),
        ('player_blocks', 2.5, 'loss', 'over'),
        ('player_turnovers', 2.5, 'win', 'over'),
        ('player_turnovers', 3.5, 'loss', 'over'),
    ],
)
def test_single_stat_markets_settle(market_type: str, line: float, expected_win: str, direction: str) -> None:
    provider = RegistryProvider()
    leg = Leg(
        raw_text='Nikola Jokic test',
        sport='NBA',
        market_type=market_type,
        player='Nikola Jokic',
        direction=direction,
        line=line,
        confidence=0.95,
        event_id='evt-1',
        event_label='Boston Celtics @ Denver Nuggets',
        resolved_team='Denver Nuggets',
    )
    graded = settle_leg(leg, provider)
    assert graded.settlement == expected_win


@pytest.mark.parametrize(
    ('market_type', 'line', 'expected'),
    [
        ('player_pra', 28.5, 'win'),
        ('player_pra', 40.5, 'loss'),
        ('player_pr', 26.5, 'win'),
        ('player_pr', 30.5, 'loss'),
        ('player_pa', 24.5, 'win'),
        ('player_pa', 28.5, 'loss'),
        ('player_ra', 11.5, 'win'),
        ('player_ra', 13.5, 'loss'),
    ],
)
def test_combo_markets_settle_with_breakdown(market_type: str, line: float, expected: str) -> None:
    provider = RegistryProvider()
    leg = Leg(
        raw_text='Nikola Jokic combo',
        sport='NBA',
        market_type=market_type,
        player='Nikola Jokic',
        direction='over',
        line=line,
        confidence=0.95,
        event_id='evt-1',
        event_label='Boston Celtics @ Denver Nuggets',
        resolved_team='Denver Nuggets',
    )
    graded = settle_leg(leg, provider)
    assert graded.settlement == expected
    assert graded.settlement_explanation is not None
    assert graded.settlement_explanation.stat_components
    assert graded.settlement_explanation.component_values
    assert graded.settlement_explanation.computed_total is not None


def test_settle_leg_prefers_snapshot_for_migrated_single_stat_markets() -> None:
    provider = RegistryProvider()
    leg = Leg(
        raw_text='Nikola Jokic points',
        sport='NBA',
        market_type='player_points',
        player='Nikola Jokic',
        direction='over',
        line=29.5,
        confidence=0.95,
        event_id='evt-1',
        event_label='Boston Celtics @ Denver Nuggets',
        resolved_team='Denver Nuggets',
    )
    snapshot = EventSnapshot(
        event_id='evt-1',
        home_team={'name': 'Denver Nuggets'},
        away_team={'name': 'Boston Celtics'},
        normalized_player_stats={
            'nikolajokic': {
                'player_id': '15',
                'display_name': 'Nikola Jokic',
                'stats': {'PTS': 30.0, 'REB': 7.0, 'AST': 5.0, 'PR': 37.0, 'PA': 35.0, 'RA': 12.0, 'PRA': 42.0},
            }
        },
    )

    def _boom(*args, **kwargs):
        raise AssertionError('provider stat lookup should not be called when snapshot stat exists')

    provider.get_player_result = _boom  # type: ignore[method-assign]
    graded = settle_leg(leg, provider, event_snapshot=snapshot)
    assert graded.settlement == 'win'


def test_settle_leg_snapshot_combo_matches_provider_result() -> None:
    provider = RegistryProvider()
    leg = Leg(
        raw_text='Nikola Jokic pra',
        sport='NBA',
        market_type='player_pra',
        player='Nikola Jokic',
        direction='over',
        line=41.5,
        confidence=0.95,
        event_id='evt-1',
        event_label='Boston Celtics @ Denver Nuggets',
        resolved_team='Denver Nuggets',
    )
    snapshot = EventSnapshot(
        event_id='evt-1',
        home_team={'name': 'Denver Nuggets'},
        away_team={'name': 'Boston Celtics'},
        normalized_player_stats={
            'nikolajokic': {
                'player_id': '15',
                'display_name': 'Nikola Jokic',
                'stats': {'PTS': 20.0, 'REB': 7.0, 'AST': 5.0, 'PRA': 32.0},
            }
        },
    )

    from_snapshot = settle_leg(leg, provider, event_snapshot=snapshot)
    from_provider = settle_leg(leg, provider)

    assert from_snapshot.actual_value == from_provider.actual_value
    assert from_snapshot.settlement == from_provider.settlement

