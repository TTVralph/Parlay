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
        self.player_result_calls = 0
        self.values = {
            'player_points': 20.0,
            'player_rebounds': 7.0,
            'player_assists': 5.0,
            'player_threes': 2.0,
            'player_steals': 1.0,
            'player_blocks': 2.0,
            'player_turnovers': 3.0,
            'player_double_double': 0.0,
            'player_triple_double': 0.0,
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
        self.player_result_calls += 1
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



@pytest.mark.parametrize(
    ('market_type', 'line', 'snapshot_stat_key', 'snapshot_value'),
    [
        ('player_points', 29.5, 'PTS', 30.0),
        ('player_rebounds', 9.5, 'REB', 10.0),
        ('player_assists', 8.5, 'AST', 9.0),
        ('player_threes', 2.5, '3PM', 3.0),
        ('player_steals', 1.5, 'STL', 2.0),
        ('player_blocks', 1.5, 'BLK', 2.0),
        ('player_turnovers', 2.5, 'TOV', 3.0),
    ],
)
def test_settle_leg_prefers_snapshot_for_migrated_single_stat_markets(
    market_type: str,
    line: float,
    snapshot_stat_key: str,
    snapshot_value: float,
) -> None:
    provider = RegistryProvider()
    leg = Leg(
        raw_text='Nikola Jokic single stat',
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
    snapshot = EventSnapshot(
        event_id='evt-1',
        home_team={'name': 'Denver Nuggets'},
        away_team={'name': 'Boston Celtics'},
        normalized_player_stats={
            'nikolajokic': {
                'player_id': '15',
                'display_name': 'Nikola Jokic',
                'stats': {snapshot_stat_key: snapshot_value},
            }
        },
    )

    graded = settle_leg(leg, provider, event_snapshot=snapshot)

    assert graded.settlement == 'win'
    assert provider.player_result_calls == 0
    assert graded.settlement_explanation is not None
    assert graded.settlement_diagnostics.get('stat_source') == 'snapshot'
    snapshot_diag = graded.settlement_diagnostics.get('snapshot_stat_diagnostics') or {}
    assert snapshot_diag.get('used_snapshot') is True
    assert snapshot_diag.get('provider_fallback_used') is False
    assert snapshot_diag.get('requested_stat_key') == snapshot_stat_key


@pytest.mark.parametrize(
    ('market_type', 'line', 'missing_stat_key'),
    [
        ('player_threes', 1.5, 'PTS'),
        ('player_steals', 0.5, 'REB'),
        ('player_blocks', 1.5, 'AST'),
        ('player_turnovers', 2.5, 'PTS'),
    ],
)
def test_settle_leg_snapshot_falls_back_to_provider_when_single_stat_missing(
    market_type: str,
    line: float,
    missing_stat_key: str,
) -> None:
    provider = RegistryProvider()
    leg = Leg(
        raw_text='Nikola Jokic fallback stat',
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
    snapshot = EventSnapshot(
        event_id='evt-1',
        home_team={'name': 'Denver Nuggets'},
        away_team={'name': 'Boston Celtics'},
        normalized_player_stats={
            'nikolajokic': {
                'player_id': '15',
                'display_name': 'Nikola Jokic',
                'stats': {missing_stat_key: 99.0},
            }
        },
    )

    graded = settle_leg(leg, provider, event_snapshot=snapshot)

    assert graded.settlement == 'win'
    assert provider.player_result_calls > 0
    assert graded.settlement_explanation is not None
    assert graded.settlement_diagnostics.get('stat_source') == 'provider'
    snapshot_diag = graded.settlement_diagnostics.get('snapshot_stat_diagnostics') or {}
    assert snapshot_diag.get('used_snapshot') is False
    assert snapshot_diag.get('provider_fallback_used') is True
    assert snapshot_diag.get('missing_snapshot_stat_key') is not None


def test_settle_leg_snapshot_prefers_double_double_derived_market() -> None:
    provider = RegistryProvider()
    leg = Leg(
        raw_text='Nikola Jokic double double',
        sport='NBA',
        market_type='player_double_double',
        player='Nikola Jokic',
        direction='yes',
        line=1.0,
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
                'stats': {'PTS': 31.0, 'REB': 12.0, 'AST': 9.0, 'STL': 2.0, 'BLK': 2.0},
            }
        },
    )

    graded = settle_leg(leg, provider, event_snapshot=snapshot)

    assert graded.settlement == 'win'
    assert graded.actual_value == 2.0
    assert provider.player_result_calls == 0
    snapshot_diag = graded.settlement_diagnostics.get('snapshot_stat_diagnostics') or {}
    assert snapshot_diag.get('used_snapshot') is True
    assert snapshot_diag.get('provider_fallback_used') is False
    assert snapshot_diag.get('required_component_stat_keys') == ['PTS', 'REB', 'AST', 'STL', 'BLK']
    assert snapshot_diag.get('player_match_result') == 'normalized_match'


def test_settle_leg_snapshot_fallback_for_triple_double_when_component_missing() -> None:
    provider = RegistryProvider()
    provider.values['player_triple_double'] = 1.0
    leg = Leg(
        raw_text='Nikola Jokic triple double',
        sport='NBA',
        market_type='player_triple_double',
        player='Nikola Jokic',
        direction='yes',
        line=1.0,
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
                'stats': {'PTS': 31.0, 'REB': 12.0, 'AST': 10.0, 'STL': 2.0},
            }
        },
    )

    graded = settle_leg(leg, provider, event_snapshot=snapshot)

    assert graded.settlement == 'win'
    assert provider.player_result_calls > 0
    snapshot_diag = graded.settlement_diagnostics.get('snapshot_stat_diagnostics') or {}
    assert snapshot_diag.get('used_snapshot') is False
    assert snapshot_diag.get('provider_fallback_used') is True
    assert snapshot_diag.get('missing_snapshot_stat_keys') == ['BLK']


def test_settle_leg_snapshot_fallback_for_derived_market_when_player_match_fails() -> None:
    provider = RegistryProvider()
    provider.values['player_double_double'] = 1.0
    leg = Leg(
        raw_text='Nikola Jokic double double',
        sport='NBA',
        market_type='player_double_double',
        player='Nikola Jokic',
        direction='yes',
        line=1.0,
        confidence=0.95,
        event_id='evt-1',
        event_label='Boston Celtics @ Denver Nuggets',
        resolved_team='Denver Nuggets',
        resolved_player_id='15',
    )
    snapshot = EventSnapshot(
        event_id='evt-1',
        home_team={'name': 'Denver Nuggets'},
        away_team={'name': 'Boston Celtics'},
        normalized_player_stats={
            'somebodyelse': {
                'player_id': '42',
                'display_name': 'Someone Else',
                'stats': {'PTS': 31.0, 'REB': 12.0, 'AST': 10.0, 'STL': 2.0, 'BLK': 1.0},
            }
        },
    )

    graded = settle_leg(leg, provider, event_snapshot=snapshot)

    assert graded.settlement == 'win'
    assert provider.player_result_calls > 0
    snapshot_diag = graded.settlement_diagnostics.get('snapshot_stat_diagnostics') or {}
    assert snapshot_diag.get('player_match_result') == 'match_failed'
    assert snapshot_diag.get('provider_fallback_used') is True

def test_settle_leg_snapshot_direct_id_match_keeps_existing_behavior() -> None:
    provider = RegistryProvider()
    leg = Leg(
        raw_text='Lebron points',
        sport='NBA',
        market_type='player_points',
        player='LeBron James',
        resolved_player_name='L. James',
        resolved_player_id='23',
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
            'lebronjames': {
                'player_id': '23',
                'display_name': 'LeBron James',
                'stats': {'PTS': 31.0},
            }
        },
    )

    graded = settle_leg(leg, provider, event_snapshot=snapshot)

    assert graded.settlement == 'win'
    assert provider.player_result_calls == 0
    snapshot_diag = graded.settlement_diagnostics.get('snapshot_stat_diagnostics') or {}
    assert snapshot_diag.get('used_snapshot') is True
    assert snapshot_diag.get('player_match_result') == 'direct_match'


def test_settle_leg_pra_uses_box_score_component_sum_for_win() -> None:
    provider = RegistryProvider()
    leg = Leg(
        raw_text='Nikola Jokic Over 39.5 PRA',
        sport='NBA',
        market_type='player_pra',
        player='Nikola Jokic',
        direction='over',
        line=39.5,
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
                'stats': {'PTS': 28.0, 'REB': 11.0, 'AST': 9.0},
            }
        },
    )

    graded = settle_leg(leg, provider, event_snapshot=snapshot)

    assert graded.actual_value == 48.0
    assert graded.settlement == 'win'
    assert graded.leg.market_type == 'player_pra'


def test_wnba_points_over_under_and_final_settlement_with_snapshot() -> None:
    provider = RegistryProvider()
    leg_over = Leg(
        raw_text='Breanna Stewart over 24.5 points',
        sport='WNBA',
        market_type='player_points',
        player='Breanna Stewart',
        direction='over',
        line=24.5,
        confidence=0.95,
        event_id='evt-1',
        event_label='Las Vegas Aces @ New York Liberty',
        resolved_team='New York Liberty',
    )
    leg_under = Leg(
        raw_text='Breanna Stewart under 25.5 points',
        sport='WNBA',
        market_type='player_points',
        player='Breanna Stewart',
        direction='under',
        line=25.5,
        confidence=0.95,
        event_id='evt-1',
        event_label='Las Vegas Aces @ New York Liberty',
        resolved_team='New York Liberty',
    )
    snapshot = EventSnapshot(
        event_id='evt-1',
        sport='WNBA',
        event_status='final',
        home_team={'name': 'New York Liberty'},
        away_team={'name': 'Las Vegas Aces'},
        normalized_player_stats={
            'breannastewart': {
                'player_id': 'p1',
                'display_name': 'Breanna Stewart',
                'stats': {'PTS': 25.0},
            }
        },
    )

    graded_over = settle_leg(leg_over, provider, event_snapshot=snapshot)
    graded_under = settle_leg(leg_under, provider, event_snapshot=snapshot)

    assert graded_over.settlement == 'win'
    assert graded_under.settlement == 'win'
    assert graded_over.actual_value == 25.0
    assert graded_over.settlement_diagnostics.get('stat_source') == 'snapshot'


def test_wnba_combo_and_live_progress_from_rule_engine() -> None:
    from app.grader import _build_live_progress_payload

    provider = RegistryProvider()
    leg = Leg(
        raw_text='Aja Wilson over 33.5 pra',
        sport='WNBA',
        market_type='player_pra',
        player='Aja Wilson',
        direction='over',
        line=33.5,
        confidence=0.95,
        event_id='evt-1',
        event_label='Las Vegas Aces @ New York Liberty',
        resolved_team='Las Vegas Aces',
    )
    snapshot = EventSnapshot(
        event_id='evt-1',
        sport='WNBA',
        event_status='live',
        normalized_player_stats={
            'ajawilson': {
                'player_id': 'p2',
                'display_name': 'Aja Wilson',
                'stats': {'PTS': 20.0, 'REB': 9.0, 'AST': 5.0},
            }
        },
    )

    graded = settle_leg(leg, provider, event_snapshot=snapshot)
    payload = _build_live_progress_payload(leg, actual_value=34.0, line=33.5, component_values={'PTS': 20.0, 'REB': 9.0, 'AST': 5.0})

    assert graded.actual_value == 34.0
    assert graded.settlement == 'live'
    assert payload is not None
    assert payload['live_status_text'] == 'Line hit'
    assert payload['component_breakdown'] == {'PTS': 20.0, 'REB': 9.0, 'AST': 5.0}
